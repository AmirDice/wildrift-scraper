"""Extract engine-usable numeric effects from ALL rune descriptions (grounded).

Same pattern as item extraction: DeepSeek transcribes each rune's description
(data/runes.json) into a fixed vocabulary; every number must appear in the
source text. Hand-curated models in data/rune_effects.json take precedence at
engine load (they encode uptime judgments the LLM can't ground).

Output: data/rune_engine.json  { runeName: {effectKey: value, ...} }

Run:
    python -m scripts.extract_rune_effects
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
RUNES = ROOT / "data" / "runes.json"
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
    "ampPct": "increases damage dealt by X% (assume condition met)",
    "hasteFlat": "flat ability haste",
    "hpFlat": "flat max HP (assume max stacks)",
    "armorFlat": "flat armor",
    "mrFlat": "flat magic resist",
    "healPct": "heals X% of damage dealt or missing HP (note which in skip)",
}

SYSTEM = (
    "You transcribe Wild Rift RUNE descriptions into a fixed numeric vocabulary for a "
    "damage engine. TRANSCRIBE ONLY: every number must appear in the description. "
    "Percents are plain numbers (12 means 12%). Level-scaled values ('10-180 based on "
    "level') -> {\"lvlRange\": [lo, hi]}. Use ONLY these keys:\n"
    + "\n".join(f"  {k}: {v}" for k, v in VOCAB.items())
    + "\nRules:\n"
    "- Assume max stacks / condition met; melee values when melee/ranged differ.\n"
    "- Movement-speed, cooldown-refund, gold, ward, CC and utility effects you cannot "
    "express: skip them with a 3-6 word note in \"skip\". Do NOT force them.\n"
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


def _norm(x: float) -> str:
    return str(int(x)) if float(x) == int(x) else str(x).rstrip("0").rstrip(".")


def call_llm(key: str, batch: list[dict]) -> dict:
    lines = [f"{r['name']} [{r.get('tree','')}/{r['type']}]: {r.get('description','')}"
             for r in batch]
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true")
    args = ap.parse_args()
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        raise SystemExit("DEEPSEEK_API_KEY is not set")

    runes = json.loads(RUNES.read_text(encoding="utf-8"))
    cache: dict = {}
    if OUT.exists() and not args.fresh:
        cache = json.loads(OUT.read_text(encoding="utf-8"))
    todo = [r for r in runes if r["name"] not in cache]
    print(f"{len(runes)} runes | {len(todo)} to extract")

    by_name = {r["name"]: r for r in runes}
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        try:
            raw = call_llm(key, batch)
        except Exception as e:  # noqa: BLE001
            print(f"  ! batch {i//BATCH}: {e}")
            continue
        for name, fx in raw.items():
            r = by_name.get(name)
            if not r or not isinstance(fx, dict):
                continue
            allowed = _numbers_in(r.get("description", ""))
            clean = {}
            for k, v in fx.items():
                if k not in VOCAB:
                    continue
                if k == "burstProcType":
                    if v in ("physical", "magic", "true"):
                        clean[k] = v
                elif isinstance(v, dict) and "lvlRange" in v:
                    if all(_norm(float(x)) in allowed for x in v["lvlRange"]):
                        clean[k] = v
                elif isinstance(v, (int, float)) and _norm(float(v)) in allowed:
                    clean[k] = v
            cache[name] = clean
        OUT.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  batch {i//BATCH + 1}: {min(i+BATCH, len(todo))}/{len(todo)} done")

    n_fx = sum(1 for v in cache.values() if v)
    print(f"\nwrote {OUT.relative_to(ROOT)} ({len(cache)} runes, {n_fx} with effects)")


if __name__ == "__main__":
    main()
