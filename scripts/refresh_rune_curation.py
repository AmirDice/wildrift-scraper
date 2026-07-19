"""Refresh the hand-curated rune numbers to patch 7.2.

data/rune_effects.json is hand-curated and WINS over the LLM-extracted
data/rune_engine.json at engine load. That is correct in principle: it encodes
judgment the tooltip never states and the extractor cannot ground, e.g.

    Last Stand : "only when YOU are <60% HP"  (a raw ampPct would apply always)
    Phase Rush : msPctAvg 24                  (a fight-uptime estimate)

But its NUMBERS predate 7.2 and it silently overrode every refresh. The worst
case was Electrocute, the most-picked keystone in the game, carrying a 35%
bonus-AD ratio when 7.2 says 10%: 3.5x too strong.

So: keep the structure, correct the numbers. Each edit asserts its current
value, so a re-run or a shifted source fails loudly instead of no-oping.
Values are transcribed from data/wrmeta_runes.json (patch 7.2).

Run:
    python -m scripts.refresh_rune_curation           # dry run
    python -m scripts.refresh_rune_curation --write
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# (group, rune, dotted-path, old, new, why)
EDITS = [
    ("keystones", "Electrocute", "burstProc.adRatio", 0.35, 0.10,
     "7.2: 'Damage value: 40-210 + 10% extra [ad] + 5% [ap]'"),
    ("keystones", "Electrocute", "burstProc.apRatio", 0.2, 0.05,
     "7.2: '+ 5% [ap]'"),
    ("keystones", "Electrocute", "burstProc.baseRange", [40, 194], [40, 210],
     "7.2: '40-210 (based on level)'"),
    ("keystones", "Dark Harvest", "burstProc.flat", 40, 35,
     "7.2: 'Dark Harvest damage: 35 + 11 per soul'"),
    ("keystones", "Phase Rush", "hasteFlat", 25, 10,
     "7.2: rush grants 10 ability haste"),
    ("minors", "Brutal", "onHit.flat", 6, 5,
     "7.2: 'Attacks deal (5 + 6% bonus [ad] + 3% [ap])'"),
    ("minors", "Brutal", "onHit.adRatio", 0.08, 0.06,
     "7.2: '+ 6% bonus [ad]'"),
    ("minors", "Sudden Impact", "burstProc.baseRange", [10, 80], [15, 65],
     "7.2: 'a bonus 15-65 true damage'"),
    ("minors", "Eyeball Collector", "bonusAdAtStacks", 16, 12,
     "7.2: '1.5 [ad] ... stacking up to 8 times' = 12"),
    ("minors", "Gathering Storm", "bonusAdAtStacks", 16, 14,
     "7.2: adaptive 14 AD at full stacks"),
    ("minors", "Transcendence", "hasteFlat", 12, 10,
     "7.2: grants 10 ability haste"),
    ("minors", "Last Stand", "ampSelfLowPct", 0.09, 0.11,
     "7.2: 11% (structure kept: still gated on YOUR health)"),
]


def _get(d: dict, path: str):
    cur = d
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return KeyError
        cur = cur[part]
    return cur


def _set(d: dict, path: str, val) -> None:
    parts = path.split(".")
    cur = d
    for part in parts[:-1]:
        cur = cur[part]
    cur[parts[-1]] = val


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    fx = json.loads((DATA / "rune_effects.json").read_text(encoding="utf-8"))
    n = 0
    for group, rune, path, old, new, why in EDITS:
        entry = fx.get(group, {}).get(rune)
        if entry is None:
            raise SystemExit(f"rune {rune!r} not in {group}")
        cur = _get(entry, path)
        if cur is KeyError:
            raise SystemExit(f"{rune}: no path {path!r} (has {list(entry)})")
        if cur != old:
            raise SystemExit(f"{rune}.{path}: expected {old!r}, found {cur!r}")
        _set(entry, path, new)
        entry.setdefault("_patch", []).append(f"7.2 {path}: {old} -> {new}")
        n += 1
        print(f"  {rune:20} {path:22} {old} -> {new}")
        print(f"  {'':20} {why}")

    print(f"\n{n} curated rune values refreshed to 7.2")
    if args.write:
        (DATA / "rune_effects.json").write_text(
            json.dumps(fx, ensure_ascii=False, indent=2), encoding="utf-8")
        print("wrote data/rune_effects.json")
    else:
        print("(dry run: pass --write to apply)")


if __name__ == "__main__":
    main()
