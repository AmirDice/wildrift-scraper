"""Assign each champion a mechanical ARCHETYPE that steers itemization.

The optimizer kept mis-itemizing champions because "how does this kit deliver
damage" was never a first-class fact: it was re-derived per run from stat
probes, and probes can't see rhythm. The taxonomy (user-specified):

  spellcaster  - abilities carry the damage; autos are filler.
                 Wants haste / pen / raw AD-AP (Shojin, Luden's class).
  autoattacker - damage rides continuous basic attacks.
                 Wants AS / crit / on-hit (BotRK, Terminus, IE class).
  weaver       - ability -> auto -> ability rhythm; kit naturally spaces casts
                 to the 1.5s Spellblade cooldown. Spellblade items are CORE
                 (Trinity, Divine Sunderer, Lich Bane, Iceborn).
  onhitcaster  - the exception class: ABILITIES apply on-hit effects, so the
                 kit looks like a caster but wants on-hit items (Gwen's Q/R,
                 Yasuo's Q). Wants Nashor's / Kraken / BotRK class, in the
                 champion's scaling stat.

Assignment is LLM game-knowledge over the actual kit text, CROSS-CHECKED
against the engine's measured auto-share: an "autoattacker" whose measured
auto share is 30% gets flagged rather than silently trusted.

Writes data/champion_archetypes.json and injects "archetype" into BOTH
data/champion_builds.json (the source of truth) and web-next/src/data/
builds.json (the derived copy the frontend reads) so the tag shows on the
champion card immediately.

Run:
    python -m scripts.assign_archetypes
    python -m scripts.assign_archetypes --only "Hecarim,Gwen"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from web.fight_engine import attack_profile  # noqa: E402

CHAMPS = ROOT / "data" / "champions_wr.json"
BUILDS_SRC = ROOT / "data" / "champion_builds.json"
BUILDS_WEB = ROOT / "web-next" / "src" / "data" / "builds.json"
OUT = ROOT / "data" / "champion_archetypes.json"

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-v4-flash"
ARCHETYPES = ("spellcaster", "autoattacker", "weaver", "onhitcaster")

SYSTEM = (
    "You are a Wild Rift expert. Classify champions into EXACTLY ONE mechanical "
    "archetype describing how the kit DELIVERS damage:\n"
    "  spellcaster  - abilities carry the damage; autos are filler "
    "(Lux, Ziggs, Ahri).\n"
    "  autoattacker - damage rides continuous basic attacks; abilities are gap "
    "closers / steroids (Master Yi, Jinx, Tryndamere).\n"
    "  weaver       - the gameplay loop is cast -> auto -> cast -> auto; the kit "
    "naturally matches the 1.5s Spellblade cooldown, so Sheen items are core "
    "(Camille, Ezreal, Hecarim, Riven, Twisted Fate).\n"
    "  onhitcaster  - RARE: abilities explicitly APPLY on-hit effects, so the kit "
    "looks like a caster but wants on-hit items (Gwen: Q/R apply her passive; "
    "Yasuo/Yone: Q counts as a basic attack; Katarina: R applies on-hits).\n"
    "Judge from the ability text given plus your game knowledge. The measured "
    "autoShare (fraction of simulated damage from basic attacks) is evidence, "
    "not the answer: a weaver can sit anywhere in the middle.\n"
    'Return ONLY JSON: {"<name>": {"archetype": "...", '
    '"reason": "<one sentence naming the kit mechanic>"}, ...}'
)


def call_llm(key: str, batch: list[dict]) -> dict:
    lines = []
    for c in batch:
        abils = " | ".join(f"[{a['slot']}] {a['name']}: {(a.get('text') or '')[:130]}"
                           for a in c.get("abilities", []))
        lines.append(f"{c['name']} (measured autoShare {c['_autoShare']:.2f}): {abils}")
    body = {"model": MODEL,
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": "CHAMPIONS:\n" + "\n\n".join(lines)}],
            "response_format": {"type": "json_object"},
            "temperature": 0.1, "max_tokens": 8000, "stream": False}
    headers = {"Authorization": f"Bearer {key}"}
    for attempt in range(4):
        r = requests.post(DEEPSEEK_URL, json=body, headers=headers, timeout=240)
        if r.status_code in (429, 500, 502, 503, 504) and attempt < 3:
            time.sleep(3 * (attempt + 1))
            continue
        if not r.ok:
            raise RuntimeError(f"deepseek {r.status_code}: {r.text[:200]}")
        return json.loads(r.json()["choices"][0]["message"]["content"])
    raise RuntimeError("retries exhausted")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        raise SystemExit("DEEPSEEK_API_KEY is not set")

    champs = json.loads(CHAMPS.read_text(encoding="utf-8"))
    champs = list(champs.values()) if isinstance(champs, dict) else champs
    builds_src = json.loads(BUILDS_SRC.read_text(encoding="utf-8"))
    only = {n.strip() for n in args.only.split(",") if n.strip()} or set(builds_src)
    todo = [c for c in champs if c["name"] in only]
    print(f"{len(todo)} champions to classify")

    for c in todo:  # measured evidence for the cross-check
        try:
            c["_autoShare"] = attack_profile(c["name"], [])["autoShare"]
        except Exception:  # noqa: BLE001
            c["_autoShare"] = 0.5

    cache = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    for i in range(0, len(todo), 8):
        batch = todo[i:i + 8]
        raw = call_llm(key, batch)
        for c in batch:
            rec = raw.get(c["name"]) or {}
            arch = rec.get("archetype")
            if arch not in ARCHETYPES:
                print(f"  ! {c['name']}: bad archetype {arch!r} — skipped")
                continue
            flags = []
            # cross-check vs measurement: catch nonsense, keep judgment
            if arch == "autoattacker" and c["_autoShare"] < 0.40:
                flags.append(f"autoattacker but measured autoShare {c['_autoShare']:.2f}")
            if arch == "spellcaster" and c["_autoShare"] > 0.65:
                flags.append(f"spellcaster but measured autoShare {c['_autoShare']:.2f}")
            cache[c["name"]] = {"archetype": arch,
                                "reason": str(rec.get("reason", ""))[:200],
                                "autoShare": round(c["_autoShare"], 2),
                                **({"flags": flags} if flags else {})}
            mark = "  <-- FLAG: " + "; ".join(flags) if flags else ""
            print(f"  {c['name']:<10} {arch:<12} auto={c['_autoShare']:.2f}  "
                  f"{cache[c['name']]['reason'][:60]}{mark}")

    OUT.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    # inject into BOTH build files: champion_builds.json is the source search
    # runs read and rewrite from; builds.json is what the frontend shows now.
    for path in (BUILDS_SRC, BUILDS_WEB):
        b = json.loads(path.read_text(encoding="utf-8"))
        n = 0
        for name, rec in b.items():
            if name in cache:
                rec["archetype"] = {k: cache[name][k] for k in ("archetype", "reason")
                                    if k in cache[name]}
                n += 1
        path.write_text(json.dumps(b, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"injected archetype into {n} champions in {path.name}")


if __name__ == "__main__":
    main()
