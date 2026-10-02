"""Rebuild CN movement data for every published Tencent bracket.

Before = the production CN snapshot (data/cn_winrates_prev.json), after = the
latest scrape (data/cn_winrates.json).

Run:
    python -m scripts.build_movers
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PREV = ROOT / "data" / "cn_winrates_prev.json"          # production (before)
NEW = ROOT / "data" / "cn_winrates.json"                # latest scrape (after)
MOVERS_OUT = ROOT / "web-next" / "src" / "data" / "cn_movers.json"

BRACKETS = {
    "1": "Diamond+", "2": "Master+", "3": "Challenger", "4": "Legendary",
}
DEFAULT = "3"


def _snapshot(date: str) -> dict:
    """One dated history file, in the same shape the scrape writes."""
    path = ROOT / "data" / "history" / "cn" / f"{date}.json"
    if not path.exists():
        raise SystemExit(f"no snapshot for {date} ({path})")
    doc = json.loads(path.read_text(encoding="utf-8"))
    champs = doc.get("champions") or {}
    # history stores {slug: {wr, pick, ban, byBracket}}; the movers builder
    # wants the list-of-champions shape the scrape's main files use.
    rows = []
    for slug, e in champs.items():
        by = {b: {"winRate": v.get("wr"), "pickRate": v.get("pick")}
              for b, v in (e.get("byBracket") or {}).items()}
        rows.append({"slug": slug, "name": e.get("name") or slug.title(),
                     "byBracket": by})
    return {"date": str(doc.get("date") or date).replace("-", ""), "champions": rows}


def main() -> None:
    # An explicit window, when asked for.
    #
    # The default pair -- cn_winrates_prev.json and cn_winrates.json -- is only
    # valid immediately after a scrape rotates them. Run this at any other time
    # and both point at the SAME snapshot: every delta comes out zero and a
    # correct movers file is overwritten by a run that reports success. Naming
    # two dated history snapshots instead cannot do that, because the dates are
    # in the filenames and a missing one is an error rather than a duplicate.
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if len(args) == 2:
        prev, new = _snapshot(args[0]), _snapshot(args[1])
        if prev["date"] == new["date"]:
            raise SystemExit(f"both ends are {prev['date']}; that is not a window")
        print(f"window: {args[0]} -> {args[1]} (from dated snapshots)")
    else:
        prev = json.loads(PREV.read_text(encoding="utf-8"))
        new = json.loads(NEW.read_text(encoding="utf-8"))
        if prev.get("date") == new.get("date"):
            raise SystemExit(
                f"prev and new are both {new.get('date')}: nothing to compare.\n"
                "Pass two dates instead, e.g.\n"
                "  python scripts/build_movers.py 2026-08-25 2026-08-30")
    previous = {c["slug"]: c for c in prev["champions"]}
    # The history snapshots key by slug and carry no display name, so take the
    # proper names from the roster we already ship.
    site = json.loads((ROOT / "web-next" / "src" / "data" / "site.json").read_text(encoding="utf-8"))
    names = {c["slug"]: c["name"] for c in site.get("champions", [])}
    by_bracket = {}
    for bracket in BRACKETS:
        rows = []
        for c in new["champions"]:
            o = previous.get(c["slug"], {}).get("byBracket", {}).get(bracket)
            n = c["byBracket"].get(bracket)
            if not o or not n:
                continue
            # Pick rate on BOTH dates, not just the latest.
            #
            # A win-rate move on its own does not say what happened. Olaf
            # gained 3.36 points across this window while his pick rate went
            # from 1.15 to 1.10 -- the same small population of players doing
            # better, which means the game around him changed, not him. Syndra
            # gained 4.34 while going from 3.58 to 13.70, which is a different
            # event entirely. Without the old pick rate those two look alike.
            old_pick = round(o.get("pickRate", 0), 2)
            new_pick = round(n.get("pickRate", 0), 2)
            rows.append({"slug": c["slug"], "name": names.get(c["slug"], c["name"]),
                         "oldWr": o["winRate"], "newWr": n["winRate"],
                         "delta": round(n["winRate"] - o["winRate"], 2), "pickRate": new_pick,
                         "oldPickRate": old_pick, "pickDelta": round(new_pick - old_pick, 2)})
        rows.sort(key=lambda r: r["delta"], reverse=True)
        by_bracket[bracket] = rows
    rows = by_bracket[DEFAULT]
    movers = {"beforeDate": prev["date"], "afterDate": new["date"], "patch": "",
              "scope": "China · Challenger", "defaultBracket": DEFAULT,
              "bracketLabels": BRACKETS, "champions": rows, "byBracket": by_bracket}
    MOVERS_OUT.write_text(json.dumps(movers, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"movers: {len(rows)} champions | top {rows[0]['name']} {rows[0]['delta']:+} | "
          f"bottom {rows[-1]['name']} {rows[-1]['delta']:+}")


if __name__ == "__main__":
    main()
