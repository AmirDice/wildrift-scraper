"""Extract engine-usable numeric effects from item passives (LLM, grounded).

Converts each item's passive text (data/items.json) into the fight engine's
effect vocabulary (procs, penetration, conversions, amps, sustain). Numbers are
grounding-checked against the source text: the model transcribes, never invents.

Output: data/item_engine.json  { slug: {effect: value, ...} }

Run:
    python -m scripts.extract_item_effects
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
ITEMS = ROOT / "data" / "items.json"
OUT = ROOT / "data" / "item_engine.json"

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-v4-flash"
BATCH = 10

# effect -> short doc. All percents are given as plain numbers (12 = 12%).
VOCAB = {
    "spellbladeBaseAdPct": "next auto after ability: bonus physical = X% BASE AD",
    "spellbladePctMaxHp": "next auto after ability: bonus = X% target max HP",
    "onHitFlatPhys": "every auto: +X flat physical",
    "onHitFlatMagic": "every auto: +X flat magic",
    "onHitPctCurrentHp": "every auto: X% target CURRENT HP",
    "onHitPctMaxHp": "every auto: X% target MAX HP",
    "procMaxHpPct": "once per combo/target: X% target max HP damage",
    "firstHit": "one-time flat bonus on first hit vs champion",
    "burstProcFlat": "one-time proc damage, flat",
    "burstProcApPct": "one-time proc damage, X% AP ratio",
    "dotDps": "burn aura/passive: flat damage per second",
    "executePct": "finishes targets below X% HP",
    "giantSlayerPct": "up to X% bonus damage vs high-HP targets",
    "flatPen": "flat armor penetration (lethality)",
    "pctPen": "X% armor penetration",
    "armorShredPct": "X% armor REDUCTION (stacks debuff)",
    "critMult": "sets crit damage multiplier to X (e.g. 2.0)",
    "abilityAmpPct": "abilities deal +X% damage (assume max stacks)",
    "damageAmpPct": "ALL damage dealt +X% (assume max stacks/condition met)",
    "adFromManaPct": "gain AD = X% max mana",
    "apFromBonusHpPct": "gain AP = X% bonus HP",
    "msFlat": "flat move speed from passive (average uptime)",
    "msPct": "X% move speed from passive (average uptime)",
    "adFlatPassive": "flat AD from passive (assume max stacks)",
    "apFlatPassive": "flat AP from passive (assume max stacks)",
    "hasteFlatPassive": "flat ability haste from passive",
    "physVampPct": "X% physical vamp",
    "omnivampPct": "X% omnivamp",
    "lifestealPct": "X% lifesteal",
    "healOnHitFlat": "flat heal per auto",
    "shieldPctMaxHp": "lifeline-style shield = X% max HP (count once)",
    "shieldFlat": "lifeline-style flat shield (count once)",
    "hpFlatPassive": "flat max HP from passive stacking (assume max)",
}

SYSTEM = (
    "You transcribe Wild Rift ITEM PASSIVES into a fixed numeric vocabulary for a damage "
    "engine. TRANSCRIBE ONLY: every number must appear in the passive text. Percents are "
    "plain numbers (12 means 12%). Use ONLY these keys:\n"
    + "\n".join(f"  {k}: {v}" for k, v in VOCAB.items())
    + "\nRules:\n"
    "- Take the MAX-STACKS / condition-met value when a passive stacks or ramps.\n"
    "- If a value has melee/ranged variants, use the MELEE value.\n"
    "- Skip actives, slows, CC, vision, gold passives: put a 3-6 word note in \"skip\".\n"
    "- Champion-level scaling values (e.g. '10-180 based on level'): use the level-13 "
    "value if computable from the two endpoints ((lo+hi*12/14) rounded) is NOT allowed — "
    "instead output {\"lvlRange\": [lo, hi]} for that key, e.g. \"firstHit\": {\"lvlRange\": [30, 180]}.\n"
    '- Return ONLY JSON: {"<slug>": {"<effectKey>": number | {"lvlRange":[lo,hi]}, ..., '
    '"skip": "optional note"}, ...} with one entry per given item.'
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


def _norm(x: float) -> str:
    return str(int(x)) if float(x) == int(x) else str(x).rstrip("0").rstrip(".")


def call_llm(key: str, batch: list[dict]) -> dict:
    lines = [f"{it['slug']}: {' '.join(it['passives']) or '(no passive)'}" for it in batch]
    prompt = "ITEMS:\n" + "\n".join(lines)
    body = {"model": MODEL,
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": prompt}],
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true")
    args = ap.parse_args()
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        raise SystemExit("DEEPSEEK_API_KEY is not set")

    items = json.loads(ITEMS.read_text(encoding="utf-8"))
    cache: dict = {}
    if OUT.exists() and not args.fresh:
        cache = json.loads(OUT.read_text(encoding="utf-8"))
    todo = [it for it in items if it["slug"] not in cache]
    print(f"{len(items)} items | {len(todo)} to extract")

    by_slug = {it["slug"]: it for it in items}
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        try:
            raw = call_llm(key, batch)
        except Exception as e:  # noqa: BLE001
            print(f"  ! batch {i//BATCH}: {e}")
            continue
        for slug, fx in raw.items():
            it = by_slug.get(slug)
            if not it or not isinstance(fx, dict):
                continue
            allowed = _numbers_in(" ".join(it["passives"]))
            clean = {}
            for k, v in fx.items():
                if k == "skip":
                    continue
                if k not in VOCAB:
                    continue
                if isinstance(v, dict) and "lvlRange" in v:
                    if all(_norm(float(x)) in allowed for x in v["lvlRange"]):
                        clean[k] = v
                elif isinstance(v, (int, float)) and _norm(float(v)) in allowed:
                    clean[k] = v
            cache[slug] = clean
        OUT.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  batch {i//BATCH + 1}: {min(i+BATCH, len(todo))}/{len(todo)} done")

    n_fx = sum(1 for v in cache.values() if v)
    print(f"\nwrote {OUT.relative_to(ROOT)} ({len(cache)} items, {n_fx} with engine effects)")


if __name__ == "__main__":
    main()
