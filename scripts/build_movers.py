"""Rebuild CN movement data for every published Tencent bracket.

Before = the production CN snapshot (data/cn_winrates_prev.json), after = the
latest scrape (data/cn_winrates.json).

Run:
    python -m scripts.build_movers
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PREV = ROOT / "data" / "cn_winrates_prev.json"          # production (before)
NEW = ROOT / "data" / "cn_winrates.json"                # latest scrape (after)
MOVERS_OUT = ROOT / "web-next" / "src" / "data" / "cn_movers.json"

BRACKETS = {
    "1": "Diamond+", "2": "Master+", "3": "Challenger", "4": "Legendary",
}
DEFAULT = "3"


def main() -> None:
    prev = json.loads(PREV.read_text(encoding="utf-8"))
    new = json.loads(NEW.read_text(encoding="utf-8"))
    previous = {c["slug"]: c for c in prev["champions"]}
    by_bracket = {}
    for bracket in BRACKETS:
        rows = []
        for c in new["champions"]:
            o = previous.get(c["slug"], {}).get("byBracket", {}).get(bracket)
            n = c["byBracket"].get(bracket)
            if not o or not n:
                continue
            rows.append({"slug": c["slug"], "name": c["name"], "oldWr": o["winRate"], "newWr": n["winRate"],
                         "delta": round(n["winRate"] - o["winRate"], 2), "pickRate": round(n.get("pickRate", 0), 2)})
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
