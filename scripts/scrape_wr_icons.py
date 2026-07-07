"""Build a map of champion slug -> official Wild Rift head-icon URL.

Our champion icons were pulled from ddragon (PC League), which shows PC art and
is often out of date vs Wild Rift (Xin Zhao, Shyvana, Nidalee, ...). The official
CN hero list exposes each champion's real WR head icon, so we map those to our
English slugs (via data/cn_hero_map.json) and let the pipeline prefer them.

Output: data/wr_icons.json  { slug: iconUrl }

Run:
    python -m scripts.scrape_wr_icons
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "web-next" / "src" / "data" / "site.json"
NAME_MAP = ROOT / "data" / "cn_hero_map.json"
OUT = ROOT / "data" / "wr_icons.json"
HERO_LIST_URL = "https://game.gtimg.cn/images/lgamem/act/lrlib/js/heroList/hero_list.js"
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://lolm.qq.com/"}


def _slug(name: str) -> str:
    s = name.lower().replace("&", "and").replace("'", "")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def main() -> None:
    hero_map = json.loads(NAME_MAP.read_text(encoding="utf-8"))  # heroId -> English name
    roster = {c["slug"] for c in json.loads(SITE.read_text(encoding="utf-8"))["champions"]}
    hero_list = json.loads(requests.get(HERO_LIST_URL, headers=HEADERS, timeout=20).text)["heroList"]

    icons: dict[str, str] = {}
    for hid, en in hero_map.items():
        h = hero_list.get(hid)
        if not h or not h.get("avatar"):
            continue
        slug = _slug(en)
        if slug in roster:
            icons[slug] = h["avatar"]

    OUT.write_text(json.dumps(icons, ensure_ascii=False, indent=2), encoding="utf-8")
    missing = sorted(roster - set(icons))
    print(f"wrote {OUT.relative_to(ROOT)} — {len(icons)}/{len(roster)} champions with WR icons")
    if missing:
        print(f"  no WR icon (keep ddragon): {missing}")
    for s in ("xin-zhao", "shyvana", "nidalee", "thresh"):
        if s in icons:
            print(f"  {s}: {icons[s]}")


if __name__ == "__main__":
    main()
