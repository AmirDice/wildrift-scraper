"""Report which completed-item passives the fight engine can actually measure.

Base item stats always flow from items.json. This audit is deliberately about
the passive/active layer: an item with no effective item_engine keys is marked
``stats_only`` even though its AD, AP, health, etc. still affect simulations.

Run:
    python -m scripts.audit_item_engine_coverage
    python -m scripts.audit_item_engine_coverage --json
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
GAP = re.compile(
    r"not model(?:led|ed)|no (?:separate )?(?:combat )?(?:effect )?key|"
    r"engine has neither|priced on its stats|left out|cannot (?:open|see|price)",
    re.I,
)


def load(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def effective(value) -> bool:
    if isinstance(value, dict):
        return any(effective(v) for v in value.values())
    if isinstance(value, (int, float)):
        return value != 0
    return bool(value)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    items = load("items.json")
    base = load("item_engine.json")
    overrides = load("item_engine_overrides.json")
    rows = []
    for item in items:
        categories = set(item.get("categories") or [])
        if item.get("category") in {"Boots", "Enchantment"} or categories & {"Basic", "MidTier"}:
            continue
        passives = item.get("passives") or []
        if not passives:
            continue
        slug = item["slug"]
        merged = dict(base.get(slug) or {})
        merged.update({k: v for k, v in (overrides.get(slug) or {}).items()
                       if not k.startswith("_")})
        channels = sorted(k for k, v in merged.items()
                          if not k.startswith("_") and effective(v))
        entry = overrides.get(slug) or {}
        notes = str(entry.get("_why") or " ".join(
            str(v) for k, v in entry.items()
            if k.startswith("_") and isinstance(v, str)))
        status = "partial" if channels and GAP.search(notes) else (
            "modeled" if channels else "stats_only")
        rows.append({"slug": slug, "name": item.get("name", slug),
                     "status": status, "channels": channels,
                     "gapNote": notes if status != "modeled" else ""})

    rows.sort(key=lambda row: (row["status"], row["name"]))
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    counts = {status: sum(row["status"] == status for row in rows)
              for status in ("modeled", "partial", "stats_only")}
    print(f"completed items with passives: {len(rows)} | "
          f"modeled {counts['modeled']} | partial {counts['partial']} | "
          f"stats-only {counts['stats_only']}")
    for status in ("stats_only", "partial"):
        print(f"\n{status.upper()}")
        for row in rows:
            if row["status"] != status:
                continue
            channels = ", ".join(row["channels"]) or "no passive channel"
            print(f"- {row['name']} ({row['slug']}): {channels}")
            if row["gapNote"]:
                print(f"  {row['gapNote']}")


if __name__ == "__main__":
    main()
