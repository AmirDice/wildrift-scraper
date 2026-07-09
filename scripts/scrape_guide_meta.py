"""Scrape per-champion skill order + situational items from wildriftfire guides.

Guides have two sections we previously ignored:
  - "Skill Order": a level grid (<li class="lit" level="N">) showing exactly
    which ability gets a point at each level -> the engine's rank model can use
    the REAL recommended order instead of a damage heuristic.
  - "Situational Items": "vs X" blocks -> grounds per-champion situational
    swaps with the site's own recommendations.

Reads from data/wrf_cache (already fetched). Output: data/wrf_guide_meta.json
  { name: {"skillOrder": {"1": [levels...], ...}, "situational": [{"when": ..,
    "items": [slugs]}] } }

Run:
    python -m scripts.scrape_guide_meta
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "wrf_cache"
CHAMPS = ROOT / "data" / "champions_wr.json"
OUT = ROOT / "data" / "wrf_guide_meta.json"


def _item_slug(src: str) -> str | None:
    m = re.search(r"/images/items/([a-z0-9\-]+)\.png", src or "")
    return m.group(1) if m else None


def parse_guide(html: str, ability_names: list[str]) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    out: dict = {"skillOrder": {}, "situational": []}

    # --- skill order grid: rows are P,1,2,3,4 in kit order ------------------
    mod = soup.select_one(".skills-mod")
    if mod:
        rows = mod.select(".skills-mod__abilities__row")
        slot_i = 0
        slots = ["P", "1", "2", "3", "4"]
        for r in rows:
            if "skills-mod__abilities__row--passive" in " ".join(r.get("class", [])):
                slot_i = max(slot_i, 1)
                continue
            slot = slots[slot_i] if slot_i < len(slots) else None
            slot_i += 1
            if not slot:
                continue
            lit = [int(li.get("level")) for li in r.select("li.lit") if li.get("level")]
            if lit:
                out["skillOrder"][slot] = sorted(lit)

    # --- situational items: "vs X" blocks -----------------------------------
    seen = set()
    for sec in soup.select(".item-builds-mod .section.situation"):
        label = sec.select_one("span.situation")
        when = label.get_text(" ", strip=True) if label else ""
        slugs = []
        for img in sec.select(".ico-holder img"):
            s = _item_slug(img.get("src", ""))
            if s and s not in slugs:
                slugs.append(s)
        key = (when, tuple(slugs))
        if when and slugs and key not in seen:
            seen.add(key)
            out["situational"].append({"when": when, "items": slugs})
    return out


def main() -> None:
    champs = json.loads(CHAMPS.read_text(encoding="utf-8"))
    out: dict = {}
    missing = []
    for c in champs:
        f = CACHE / f"guide_{c['slug']}.html"
        if not f.exists():
            missing.append(c["name"])
            continue
        meta = parse_guide(f.read_text(encoding="utf-8"),
                           [a["name"] for a in c.get("abilities", [])])
        if meta["skillOrder"] or meta["situational"]:
            out[c["name"]] = meta
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    n_so = sum(1 for v in out.values() if v["skillOrder"])
    n_si = sum(1 for v in out.values() if v["situational"])
    print(f"wrote {OUT.relative_to(ROOT)}: {len(out)} champions "
          f"({n_so} with skill order, {n_si} with situational)")
    if missing:
        print(f"  no cached guide: {missing[:8]}")


if __name__ == "__main__":
    main()
