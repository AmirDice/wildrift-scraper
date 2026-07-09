"""Score every generated build with the deterministic fight engine.

Adds an `engine` block to each build variant in data/champion_builds.json (and
the frontend copy): burst3 / dps8 / ttk / ehp / sustain / score, computed by
web/fight_engine.py from the extracted ability formulas and item effects.

Champions without extracted formulas are left unannotated (engine coverage is
incremental).

Run:
    python -m scripts.score_builds
"""
from __future__ import annotations

import json
from pathlib import Path

from web.fight_engine import FORMULAS, score_champion_builds

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "champion_builds.json"
WEB_OUT = ROOT / "web-next" / "src" / "data" / "builds.json"


def main() -> None:
    builds = json.loads(OUT.read_text(encoding="utf-8"))
    scored = skipped = 0
    for name, rec in builds.items():
        if name not in FORMULAS:
            skipped += 1
            continue
        try:
            per_variant = score_champion_builds(name, rec)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {name}: engine failed ({e})")
            skipped += 1
            continue
        for variant, m in per_variant.items():
            rec["builds"][variant]["engine"] = m
        scored += 1
        line = " | ".join(f"{v}:{m['score']}" for v, m in per_variant.items())
        print(f"  {name:12} {line}")

    payload = json.dumps(builds, ensure_ascii=False, indent=2)
    OUT.write_text(payload, encoding="utf-8")
    WEB_OUT.write_text(payload, encoding="utf-8")
    print(f"\nannotated {scored} champions ({skipped} without formulas) -> "
          f"{OUT.name} + web-next builds.json")


if __name__ == "__main__":
    main()
