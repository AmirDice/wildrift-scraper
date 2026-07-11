"""Rebuild the CN site data (Diamond+ as the single bracket) and the GLOBAL
biggest-winners/losers file used by the tier list, recap and home cards.

Global win rate = (EU top-50 wr + CN Diamond+ wr) / 2, matching web-next getGlobalChampions.
Before = the production CN snapshot (data/cn_winrates_prev.json), after = the
latest scrape (data/cn_winrates.json). EU is unchanged, so the movement is the
CN patch shift expressed in global terms.

Run:
    python -m scripts.build_movers
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PREV = ROOT / "data" / "cn_winrates_prev.json"          # production (before)
NEW = ROOT / "data" / "cn_winrates.json"                # latest scrape (after)
SITE = ROOT / "web-next" / "src" / "data" / "site.json"  # EU
CN_OUT = ROOT / "web-next" / "src" / "data" / "cn.json"
MOVERS_OUT = ROOT / "web-next" / "src" / "data" / "cn_movers.json"

DIA = "1"  # "Diamond+" in the scraper's bracket scheme; the only steady bracket now
PATCH = "7.2"


def main() -> None:
    prev = json.loads(PREV.read_text(encoding="utf-8"))
    new = json.loads(NEW.read_text(encoding="utf-8"))
    eu = json.loads(SITE.read_text(encoding="utf-8"))

    # --- CN site data: promote Diamond+ to the single bracket "0" ---
    champs = []
    for c in new["champions"]:
        e = c["byBracket"].get(DIA)
        if not e:
            continue
        champs.append({"name": c["name"], "slug": c["slug"], "heroId": c.get("heroId", ""),
                       "cnName": c.get("cnName", ""), "byBracket": {"0": e}})
    cn_out = {
        "source": new.get("source", ""), "date": new["date"],
        "bracketLabels": {"0": "Diamond and above"}, "defaultBracket": "0",
        "nChampions": len(champs), "champions": champs,
    }
    CN_OUT.write_text(json.dumps(cn_out, ensure_ascii=False), encoding="utf-8")

    # --- global movers: (EU + CN Diamond+)/2, before vs after ---
    old_cn = {c["slug"]: c["byBracket"].get(DIA) for c in prev["champions"]}
    new_cn = {c["slug"]: c["byBracket"].get(DIA) for c in new["champions"]}
    rows = []
    for c in eu["champions"]:
        o, n = old_cn.get(c["slug"]), new_cn.get(c["slug"])
        if not o or not n:
            continue
        old_g = round((c["wr"] + o["winRate"]) / 2, 2)
        new_g = round((c["wr"] + n["winRate"]) / 2, 2)
        rows.append({"slug": c["slug"], "name": c["name"], "oldWr": old_g, "newWr": new_g,
                     "delta": round(new_g - old_g, 2), "pickRate": round(n.get("pickRate", 0), 2)})
    rows.sort(key=lambda r: r["delta"], reverse=True)
    movers = {"beforeDate": prev["date"], "afterDate": new["date"], "patch": PATCH,
              "scope": "Global · EU + China", "champions": rows}
    MOVERS_OUT.write_text(json.dumps(movers, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"cn.json: Diamond+ -> bracket 0 ({len(champs)} champs, date {new['date']})")
    print(f"movers: {len(rows)} champions | top {rows[0]['name']} {rows[0]['delta']:+} | "
          f"bottom {rows[-1]['name']} {rows[-1]['delta']:+}")


if __name__ == "__main__":
    main()
