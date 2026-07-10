"""Attach the full simulator readout to every generated build.

For each champion's each variant, runs the deterministic multi-dimensional
analysis (damage by type, TTK vs five target profiles, gold efficiency, healing
/ shields / damage prevented, cooldown utilisation, damage lost) plus the
class-routed composite Win Score, and stores a compact summary on the build so
the frontend can show it. Monte Carlo stays out of here — it's interactive/
on-demand, not precomputed.

ZERO LLM calls: pure engine compute.

Run:
    python -m scripts.analyze_builds --only "Graves"
    python -m scripts.analyze_builds
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from web.fight_engine import FORMULAS, _build_lists, analyze_build, win_score

ROOT = Path(__file__).resolve().parent.parent
BUILDS = ROOT / "data" / "champion_builds.json"
WEB_OUT = ROOT / "web-next" / "src" / "data" / "builds.json"


def _compact(a: dict, win: dict) -> dict:
    """Trim the full analysis to what the build card renders (keeps JSON small)."""
    return {
        "winScore": win["score"], "preset": win["preset"],
        "burst": a["burst"], "dps": a["dps"],
        "ttk": a["ttk"], "byTypePct": a["byTypePct"], "bySource": a["bySource"],
        "byAbility": a["byAbility"],
        "items": a["items"], "runes": a["runes"],
        "ehp": a["ehp"], "ehpSplit": a["ehpSplit"],
        "survivalTime": a["survivalTime"], "goldEff": a["goldEff"],
        "healing": a["healing"], "shields": a["shields"],
        "damagePrevented": a["damagePrevented"],
        "cooldownUtil": {"efficiency": a["cooldownUtil"]["efficiency"]},
        "damageLost": a["damageLost"],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--level", type=int, default=15)
    args = ap.parse_args()
    builds = json.loads(BUILDS.read_text(encoding="utf-8"))
    only = {n.strip() for n in args.only.split(",") if n.strip()}
    names = [n for n in builds if (not only or n in only) and n in FORMULAS]
    print(f"{len(names)} champions to analyze")

    for name in names:
        rec = builds[name]
        cls = rec.get("class", "")
        done = []
        for variant, bd in (rec.get("builds") or {}).items():
            items, runes = _build_lists(bd)
            a = analyze_build(name, items, runes, level=args.level)
            win = win_score(a, champ_class=cls)
            bd["analysis"] = _compact(a, win)
            done.append(f"{variant}:{win['score']}")
        print(f"  {name:12} {' '.join(done)}")
        payload = json.dumps(builds, ensure_ascii=False, indent=2)
        BUILDS.write_text(payload, encoding="utf-8")
        WEB_OUT.write_text(payload, encoding="utf-8")

    print("\nanalysis complete")


if __name__ == "__main__":
    main()
