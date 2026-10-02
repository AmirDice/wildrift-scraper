"""Model-free audit of every live Wild Rift rune against engine coverage.

This intentionally makes no advisor/model calls.  It checks catalogue
classification, exercises every rune through both a ranged and melee stat
block, and can save a machine-readable report for later regression review.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from web.fight_engine import (RUNE_COVERAGE, RUNE_ENGINE, RUNE_FX,
                              resolve_stats, rune_mechanics_coverage)


def build_report() -> dict:
    catalogue = json.loads((ROOT / "data" / "runes.json").read_text(encoding="utf-8"))
    partial = RUNE_COVERAGE.get("partial") or {}
    excluded = RUNE_COVERAGE.get("excluded") or {}
    curated = {**(RUNE_FX.get("keystones") or {}), **(RUNE_FX.get("minors") or {})}
    rows = []
    failures = []
    for rune in catalogue:
        name = rune["name"]
        if name in excluded:
            status = "excluded"
        elif name in partial:
            status = "partial"
        else:
            record = curated.get(name) or RUNE_ENGINE.get(name) or {}
            active = [key for key, value in record.items()
                      if not key.startswith("_") and value not in (0, 0.0, None, {}, [])]
            status = "modeled" if active else "unmodeled"
        try:
            # Exercise both range classes because several runes explicitly
            # split melee/ranged values.
            resolve_stats("Jinx", 15, ["bloodthirster"], [name])
            resolve_stats("Olaf", 15, ["black-cleaver"], [name])
        except Exception as exc:  # pragma: no cover - report path
            failures.append({"rune": name, "error": f"{type(exc).__name__}: {exc}"})
        coverage = rune_mechanics_coverage([name])
        rows.append({
            "name": name, "type": rune.get("type"), "status": status,
            "engineAuthoritative": coverage["engineAuthoritative"],
            "limitation": partial.get(name) or excluded.get(name) or "",
        })
    counts = Counter(row["status"] for row in rows)
    catalogue_names = {row["name"] for row in rows}
    return {
        "catalogueCount": len(rows), "counts": dict(sorted(counts.items())),
        "runtimeFailures": failures,
        "coverageEntriesOutsideLiveCatalogue": sorted(
            (set(partial) | set(excluded)) - catalogue_names),
        "runes": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = build_report()
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
