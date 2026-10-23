"""Win-rate history per champion, for the chart on each champion page.

Reads the per-collection ladder snapshots (data/history/eu, na, cn_ladder) and
Tencent's daily China rates (data/history/cn), and writes one compact file:

    web-next/src/data/wr_history.json

Ladder points are CENTRED the way the site shows them (raw + that
collection's wrOffset), so a point on the chart is the number the tier list
showed at the time. Snapshots that predate the stored offset get it
recomputed the same way: 50 minus the board's mean raw rate.

One point per COLLECTION, not per snapshot. export_json writes a snapshot
every time it runs, so a multi-day collection leaves several (EU 2026-10-22
and 2026-10-23 are the same run). Snapshots within MERGE_DAYS of the next one
are folded into it, keeping the later, and partial snapshots (under 90% of
the roster, e.g. NA 2026-08-08 with 74 champions) are skipped.

The China daily series is a different measurement -- every ranked game in
Tencent's own stats, not the top players of a ladder -- and is kept apart
(`daily`) so the page can label it as such.

Run from the repository root (the daily CN job runs it too):

    python scripts/export_wr_history.py
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "data" / "history"
OUT = ROOT / "web-next" / "src" / "data" / "wr_history.json"
LADDERS = {"eu": "eu", "na": "na", "cn": "cn_ladder"}
MERGE_DAYS = 5
MIN_COVERAGE = 0.9


def _load(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def ladder_series(folder: str) -> tuple[list[str], dict[str, list]]:
    snaps = []
    for path in sorted((HISTORY / folder).glob("????-??-??.json")):
        doc = _load(path)
        if doc and isinstance(doc.get("champions"), dict):
            snaps.append((path.stem, doc))
    if not snaps:
        return [], {}
    roster = max(len(doc["champions"]) for _d, doc in snaps)
    snaps = [(d, doc) for d, doc in snaps if len(doc["champions"]) >= MIN_COVERAGE * roster]
    kept = []
    for stamp, doc in snaps:
        if kept and _days(kept[-1][0], stamp) <= MERGE_DAYS:
            kept[-1] = (stamp, doc)       # same collection: the later export wins
        else:
            kept.append((stamp, doc))
    series: dict[str, list] = {}
    for stamp, doc in kept:
        champs = doc["champions"]
        raws = [c["wr"] for c in champs.values() if isinstance(c.get("wr"), (int, float))]
        offset = doc.get("wrOffset")
        if offset is None:
            offset = 50 - sum(raws) / len(raws)
        for slug, rec in champs.items():
            if isinstance(rec.get("wr"), (int, float)):
                series.setdefault(slug, []).append([stamp, round(rec["wr"] + offset, 1)])
    return [stamp for stamp, _doc in kept], series


def daily_series() -> dict[str, list]:
    series: dict[str, list] = {}
    for path in sorted((HISTORY / "cn").glob("????-??-??.json")):
        doc = _load(path)
        champs = (doc or {}).get("champions")
        if not isinstance(champs, dict):
            continue
        for slug, rec in champs.items():
            wr = rec.get("wr") if isinstance(rec, dict) else None
            if isinstance(wr, (int, float)):
                series.setdefault(slug, []).append([path.stem, round(wr, 2)])
    return series


def main() -> int:
    collections: dict[str, list[str]] = {}
    per_region: dict[str, dict[str, list]] = {}
    for region, folder in LADDERS.items():
        collections[region], per_region[region] = ladder_series(folder)
    daily = daily_series()

    slugs = sorted(set().union(*per_region.values(), daily))
    champions = {}
    for slug in slugs:
        rec = {region: per_region[region][slug] for region in LADDERS if slug in per_region[region]}
        if slug in daily:
            rec["daily"] = daily[slug]
        champions[slug] = rec

    out = {
        "source": "data/history ladder snapshots (centred) and Tencent daily China rates",
        "collections": collections,
        "dailyFrom": min((pts[0][0] for pts in daily.values()), default=None),
        "dailyTo": max((pts[-1][0] for pts in daily.values()), default=None),
        "champions": champions,
    }
    text = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    if OUT.exists() and json.loads(OUT.read_text(encoding="utf-8")) == out:
        print("Unchanged. Not rewritten.")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)}: {len(champions)} champions, {len(text) // 1024} KB")
    for region, dates in collections.items():
        print(f"  {region}: {len(dates)} collections {dates}")
    print(f"  daily: {out['dailyFrom']} to {out['dailyTo']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
