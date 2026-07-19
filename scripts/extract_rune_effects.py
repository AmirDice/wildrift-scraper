"""Extract engine-usable numeric effects from ALL rune descriptions (grounded).

Same pattern as item extraction: DeepSeek transcribes each rune's effect text
into a fixed vocabulary, and every number must be justified by the source.

Source is data/wrmeta_runes.json (patch 7.2). The older data/runes.json is
stale: 34 of 51 shared runes had different numbers, and the drift is not
cosmetic (Electrocute's AD ratio moved 35% -> 10%).

Output: data/rune_engine.json  { runeName: {effectKey: value, ...} }

NOTE on precedence: data/rune_effects.json is hand-curated and WINS over this
file at engine load. Several of its numbers predate 7.2, so refreshing this
file alone will not change what the engine sees for those runes.

Run:
    python -m scripts.extract_rune_effects --fresh --samples 3
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from collections import Counter
from pathlib import Path

import requests

from scripts.extract_item_effects import _grounded_num

ROOT = Path(__file__).resolve().parent.parent
RUNES = ROOT / "data" / "wrmeta_runes.json"   # 7.2-current; runes.json is stale
OUT = ROOT / "data" / "rune_engine.json"

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-v4-flash"
BATCH = 12

VOCAB = {
    "adaptiveAd": "gives X AD when taken as the AD option ('8 AD or 14 AP' style)",
    "adaptiveAp": "the AP option of the same adaptive bonus",
    "bonusAd": "flat AD (assume max stacks if stacking)",
    "bonusAp": "flat AP (assume max stacks if stacking)",
    "burstProcFlat": "one-time proc damage, flat or level-scaled",
    "burstProcAdRatio": "bonus-AD ratio of that proc (35 = 35%)",
    "burstProcApRatio": "AP ratio of that proc",
    "burstProcType": "physical | magic | true (string)",
    "onHitFlat": "per-basic-attack bonus damage",
    "onHitAdRatio": "bonus-AD ratio of that per-attack damage",
    "onHitApRatio": "AP ratio of that per-attack damage",
    "ampPct": "increases damage dealt by X% (assume condition met)",
    "hasteFlat": "flat ability haste",
    "hpFlat": "flat max HP (assume max stacks)",
    "manaFlat": "flat max MANA (assume max stacks; Manaflow Band caps at 300)",
    "armorFlat": "flat armor",
    "mrFlat": "flat magic resist",
    "armorPct": "X% bonus armor (assume max nearby enemies; Unshakeable)",
    "mrPct": "X% bonus magic resist (assume max nearby enemies)",
    "healPctMaxHp": "per proc, heals YOU for X% of your max HP (Font of Life)",
    "healApRatio": "...plus X% of your AP on that heal",
    "allyHealPctMaxHp": "per proc, heals an ALLY for X% of YOUR max HP (Font of Life)",
    "healPct": "heals X% of damage dealt or missing HP (note which in skip)",
    "healFlat": "flat heal per proc",
    "shieldFlat": "flat shield on yourself (assume it triggers once)",
    "shieldPctMaxHp": "shield ALSO adds X% of your MAX HP. Only for 'max Health'.",
    "shieldPctBonusHp": "shield ALSO adds X% of your BONUS HP. Use this for "
                        "'bonus Health' -- it is NOT the same as max HP.",
    "shieldApRatio": "shield ALSO adds X% of your AP",
    "allyShieldFlat": "shields an ALLY for X (Guardian)",
    "ultAmpPct": "your ULTIMATE deals X% more damage (Axiom Arcanist)",
    "abilityAmpPct": "your basic ABILITIES deal X% more damage (Battle Zeal)",
    "itemHasteFlat": "flat ITEM ability haste (Ingenious Hunter)",
    "msPct": "X% move speed (average uptime)",
}

SYSTEM = (
    "You transcribe Wild Rift RUNE descriptions into a fixed numeric vocabulary for a "
    "damage engine. NEVER INVENT: every number must appear in the description, or be "
    "computed from numbers in it exactly as these rules direct (a max-stack total like "
    "1.5 x 8 = 12, or a percent written as a multiplier). Percents are otherwise plain "
    "numbers (12 means 12%). Level-scaled values ('40-210 based on level') -> "
    "{\"lvlRange\": [lo, hi]}. Tokens like [ad] / [ap] / [hp] mark which STAT a ratio "
    "scales with: '10% extra [ad]' is a 10% bonus-AD ratio. Use ONLY these keys:\n"
    + "\n".join(f"  {k}: {v}" for k, v in VOCAB.items())
    + "\nRules:\n"
    "- Assume max stacks / condition met; melee values when melee/ranged differ.\n"
    "- Gold, ward, vision, CC and utility effects you cannot express: skip them with a "
    "3-6 word note in \"skip\". Do NOT force them into a damage key.\n"
    '- Return ONLY JSON: {"<rune name>": {"<key>": number | {"lvlRange":[lo,hi]} | '
    '"physical|magic|true", ..., "skip": "note"}, ...} one entry per rune given.'
)


def _numbers_in(text: str) -> set[str]:
    toks = set()
    for m in re.findall(r"\d+(?:\.\d+)?", text):
        toks.add(m)
        try:
            f = float(m)
            if f == int(f):
                toks.add(str(int(f)))
        except ValueError:
            pass
    return toks


def _text(r: dict) -> str:
    """wr-meta keys the effect as "text"; the old runes.json used "description"."""
    return r.get("text") or r.get("description") or ""


def _clean_fx(rune: dict, fx: dict) -> dict:
    """Keep vocabulary keys whose numbers the rune text justifies."""
    allowed = _numbers_in(_text(rune))
    clean = {}
    for k, v in fx.items():
        if k == "skip" or k not in VOCAB:
            continue
        if k == "burstProcType":
            if v in ("physical", "magic", "true"):
                clean[k] = v
        elif isinstance(v, dict) and "lvlRange" in v:
            if all(_grounded_num(float(x), allowed) for x in v["lvlRange"]):
                clean[k] = v
        elif isinstance(v, (int, float)) and _grounded_num(float(v), allowed):
            clean[k] = v
    return clean


def call_llm(key: str, batch: list[dict]) -> dict:
    lines = [f"{r['name']} [{r.get('tree','')}/{r['type']}]: {_text(r)}" for r in batch]
    body = {"model": MODEL,
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": "RUNES:\n" + "\n".join(lines)}],
            "response_format": {"type": "json_object"},
            "temperature": 0.1, "max_tokens": 16000, "stream": False}
    headers = {"Authorization": f"Bearer {key}"}
    for attempt in range(5):
        r = requests.post(DEEPSEEK_URL, json=body, headers=headers, timeout=300)
        if r.status_code in (429, 500, 502, 503, 504) and attempt < 4:
            time.sleep(3 * (attempt + 1))
            continue
        if not r.ok:
            raise RuntimeError(f"deepseek {r.status_code}: {r.text[:200]}")
        return json.loads(r.json()["choices"][0]["message"]["content"])
    raise RuntimeError("retries exhausted")


def extract_batch(key: str, batch: list[dict], samples: int = 3) -> dict:
    """Sample several times and UNION the grounded results.

    The rune extractor shipped the same two bugs the item one did: a single pass
    is not reproducible, and verbatim-only grounding silently deleted correctly
    derived values. Every value is grounded independently, so a union can add
    real effects but never invent one.
    """
    by_name = {r["name"]: r for r in batch}
    votes: dict[str, dict[str, list]] = {}
    for _ in range(samples):
        try:
            raw = call_llm(key, batch)
        except Exception as e:  # noqa: BLE001
            print(f"    ! sample failed: {e}")
            continue
        for name, fx in raw.items():
            r = by_name.get(name)
            if not r or not isinstance(fx, dict):
                continue
            for k, v in _clean_fx(r, fx).items():
                votes.setdefault(name, {}).setdefault(k, []).append(v)

    out = {}
    for r in batch:
        picked = {}
        for k, vals in (votes.get(r["name"]) or {}).items():
            common = Counter(json.dumps(v, sort_keys=True) for v in vals).most_common(1)
            picked[k] = json.loads(common[0][0])
        out[r["name"]] = picked
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--samples", type=int, default=3,
                    help="LLM samples per batch, unioned (1 pass is not reproducible)")
    ap.add_argument("--only", default="", help="comma-separated rune names")
    args = ap.parse_args()
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        raise SystemExit("DEEPSEEK_API_KEY is not set")

    runes = json.loads(RUNES.read_text(encoding="utf-8"))
    cache: dict = {}
    if OUT.exists() and not args.fresh:
        cache = json.loads(OUT.read_text(encoding="utf-8"))
    only = {s.strip() for s in args.only.split(",") if s.strip()}
    if only:
        todo = [r for r in runes if r["name"] in only]
    else:
        todo = [r for r in runes if r["name"] not in cache]
    print(f"{len(runes)} runes | {len(todo)} to extract")

    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        try:
            got = extract_batch(key, batch, samples=args.samples)
        except Exception as e:  # noqa: BLE001
            print(f"  ! batch {i//BATCH}: {e}")
            continue
        for name, clean in got.items():
            cache[name] = clean
        OUT.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  batch {i//BATCH + 1}: {min(i+BATCH, len(todo))}/{len(todo)} done")

    n_fx = sum(1 for v in cache.values() if v)
    print(f"\nwrote {OUT.relative_to(ROOT)} ({len(cache)} runes, {n_fx} with effects)")


if __name__ == "__main__":
    main()
