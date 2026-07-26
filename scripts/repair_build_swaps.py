"""Repair and audit the situational swaps in the curated build catalogue.

Two problems accumulated in data/champion_builds.json:

  1. Dangling swaps. A situational entry names the coreBuild item it replaces,
     but roughly a fifth of them point at an item that is not in that build at
     all (left over from an earlier item order). Those render as a swap with no
     target and are advice for a build nobody has.
  2. No timing. A swap is bought at the position of the item it replaces, but
     that position was never recorded, and the generator drifted into parking
     most swaps on the last item. In a 15-20 minute game an item-5 swap arrives
     after the game is decided.

This pass is deterministic: it drops entries it cannot resolve and records the
position of the ones it can (`atPosition`). It does NOT invent better timing --
re-timing a swap is a build decision, so the script instead reports which
champions are still swap-late so they can be regenerated with the updated
prompt in scripts/build_champions_llm.py.

Run:
    python -m scripts.repair_build_swaps            # report only
    python -m scripts.repair_build_swaps --write    # apply
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "champion_builds.json"
WEB = ROOT / "web-next" / "src" / "data" / "builds.json"


def repair(data: dict) -> tuple[dict, dict]:
    stats = {
        "dropped": 0,
        "positioned": 0,
        "positions": Counter(),
        "late_only": [],
        "rune_swaps_labelled": 0,
    }

    for champion, record in data.items():
        for variant, build in (record.get("builds") or {}).items():
            core = [item.get("slug") for item in build.get("coreBuild") or []]
            label = f"{champion}/{variant}"

            kept = []
            for entry in build.get("situational") or []:
                replaces = entry.get("replaces")
                if not replaces or replaces not in core:
                    stats["dropped"] += 1
                    continue
                entry["atPosition"] = core.index(replaces) + 1
                stats["positions"][entry["atPosition"]] += 1
                stats["positioned"] += 1
                kept.append(entry)
            build["situational"] = kept
            if kept and all(entry["atPosition"] >= 4 for entry in kept):
                stats["late_only"].append(label)

            # Situational runes gain the same shape the advisor now returns, so
            # the frontend can render both sources with one component.
            for entry in build.get("situationalRunes") or []:
                if "replacesType" in entry:
                    continue
                replaces = entry.get("replaces")
                if not replaces:
                    continue
                if replaces in core:
                    entry["replacesType"] = "item"
                    entry["replacesLabel"] = next(
                        (item.get("name") for item in build.get("coreBuild") or []
                         if item.get("slug") == replaces),
                        replaces,
                    )
                else:
                    entry["replacesType"] = "rune"
                    entry["replacesLabel"] = replaces
                stats["rune_swaps_labelled"] += 1

    return data, stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="write the repaired files")
    args = parser.parse_args()

    data = json.loads(SRC.read_text(encoding="utf-8"))
    data, stats = repair(data)

    print(f"situational swaps kept:    {stats['positioned']}")
    print(f"situational swaps dropped: {stats['dropped']} (replaced an item not in the build)")
    print("by purchase position:      "
          + ", ".join(f"{position}: {count}"
                      for position, count in sorted(stats["positions"].items())))
    print(f"rune swaps labelled:       {stats['rune_swaps_labelled']}")
    late = stats["late_only"]
    print(f"\nbuilds where EVERY swap is item 4-5: {len(late)}")
    if late:
        print("  regenerate these with scripts.build_champions_llm to re-time them:")
        for entry in late:
            print(f"    {entry}")

    if not args.write:
        print("\n(dry run: pass --write to apply)")
        return

    payload = json.dumps(data, ensure_ascii=False, indent=2)
    SRC.write_text(payload, encoding="utf-8")
    WEB.write_text(payload, encoding="utf-8")
    print(f"\nwrote {SRC.relative_to(ROOT)} + {WEB.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
