"""Champion Behaviour Model (A3): per-champion metadata describing HOW a
champion plays, so the scaling engine can value items without hardcoding.

Eight metrics, each a 1-5 star rating (stored 0-1). Most are game knowledge a
tooltip can't give (how often you fight, roam, contest objectives), so they come
from a bounded LLM questionnaire, labelled source="llm-knowledge". The engine
also derives spell-cast-rate and fight-length from the kit as a cross-check.

This is what makes "Manamune is good on Hecarim" emergent: Hecarim's high spell
cast rate makes mana/cast-scaling items score higher, with no per-champion rule.

Output: adds a "behavior" block per champion to data/ability_formulas.json.

Run:
    DEEPSEEK_API_KEY=... python -m scripts.extract_behavior --only "Hecarim,Graves"
    DEEPSEEK_API_KEY=... python -m scripts.extract_behavior
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import requests

from web.fight_engine import behavior_derived

ROOT = Path(__file__).resolve().parent.parent
FORMULAS = ROOT / "data" / "ability_formulas.json"
CHAMPS = ROOT / "data" / "champions_wr.json"
SITE = ROOT / "web-next" / "src" / "data" / "site.json"

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-v4-flash"

# The eight behaviour metrics, each 1 (very low) .. 5 (very high).
METRICS = ["spellCastRate", "fightFrequency", "tradeFrequency", "objectiveDamage",
           "waveclear", "jungleClear", "roamFrequency", "avgFightLength"]

BEHAVIOR_SYSTEM = (
    "You are a Wild Rift (mobile) expert. Rate ONE champion's PLAYSTYLE on a 1-5 "
    "scale (1 very low, 5 very high) from your knowledge of the actual game. "
    "Wild Rift differs from PC League: answer for WILD RIFT.\n"
    'Return ONLY JSON with integer 1-5 for each key:\n'
    '{"spellCastRate": how often it casts abilities in a fight (Hecarim/Kata 5, '
    'Nasus/Garen 2), "fightFrequency": how often it seeks fights/skirmishes '
    '(assassins, junglers 5; scaling carries 2), "tradeFrequency": how often it '
    'trades in lane, "objectiveDamage": damage to dragon/baron/turret (%HP, '
    'on-hit, sustained DPS = high), "waveclear": wave-clear speed, "jungleClear": '
    'jungle-clear speed (2 if it never junglers), "roamFrequency": how often it '
    'roams, "avgFightLength": how long its fights last (1 = instant burst, 5 = '
    'long drawn-out), "confidence": "high"|"medium"|"low"}'
)


def llm_call(key: str, champ: dict) -> dict:
    abils = "\n".join(f"[{a['slot']}] {a['name']}: {(a.get('text') or '')[:180]}"
                      for a in champ.get("abilities", []))
    user = (f"CHAMPION: {champ['name']} (class {champ.get('_class', '?')}, "
            f"role {champ.get('_role', '?')})\n{abils}")
    body = {"model": MODEL,
            "messages": [{"role": "system", "content": BEHAVIOR_SYSTEM},
                         {"role": "user", "content": user}],
            "response_format": {"type": "json_object"},
            "temperature": 0.1, "max_tokens": 8000, "stream": False}
    headers = {"Authorization": f"Bearer {key}"}
    for attempt in range(4):
        r = requests.post(DEEPSEEK_URL, json=body, headers=headers, timeout=180)
        if r.status_code in (429, 500, 502, 503, 504) and attempt < 3:
            time.sleep(3 * (attempt + 1))
            continue
        if not r.ok:
            raise RuntimeError(f"deepseek {r.status_code}")
        return json.loads(r.json()["choices"][0]["message"]["content"])
    return {}


def _behavior(name: str, champ: dict, key: str) -> dict:
    raw = llm_call(key, champ)
    out: dict = {"source": "llm-knowledge"}
    for m in METRICS:
        v = raw.get(m)
        if isinstance(v, (int, float)):
            out[m] = round(max(1, min(5, int(round(v)))) / 5.0, 2)  # 1-5 star -> 0-1
    if raw.get("confidence") in ("high", "medium", "low"):
        out["confidence"] = raw["confidence"]
    # engine-derived cross-check (grounded); flags where the LLM disagrees sharply
    der = behavior_derived(name)
    out["derived"] = der
    for m in ("spellCastRate", "avgFightLength"):
        if m in out and m in der and abs(out[m] - der[m]) > 0.45:
            out.setdefault("flags", []).append(m)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise SystemExit("set DEEPSEEK_API_KEY")

    formulas = json.loads(FORMULAS.read_text(encoding="utf-8"))
    champs = {c["name"]: c for c in json.loads(CHAMPS.read_text(encoding="utf-8"))}
    site = json.loads(SITE.read_text(encoding="utf-8"))
    meta = {c["name"]: c for c in site.get("champions", [])}

    only = {n.strip() for n in args.only.split(",") if n.strip()}
    names = [n for n in formulas if (not only or n in only) and n in champs]
    print(f"{len(names)} champions to profile")

    for i, name in enumerate(names, 1):
        c = dict(champs[name])
        c["_class"] = meta.get(name, {}).get("class", "")
        c["_role"] = meta.get(name, {}).get("role", "")
        try:
            b = _behavior(name, c, key)
            formulas[name]["behavior"] = b
            stars = " ".join(f"{m[:4]}{int(b.get(m,0)*5)}" for m in METRICS if m in b)
            flag = f"  FLAG:{b['flags']}" if b.get("flags") else ""
            print(f"  [{i}/{len(names)}] {name:14} {stars}{flag}")
        except Exception as e:  # noqa: BLE001
            print(f"  [{i}/{len(names)}] {name:14} ERROR {e}")
        FORMULAS.write_text(json.dumps(formulas, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\nbehaviour profiling complete")


if __name__ == "__main__":
    main()
