"""Scrape Wild Rift rune names + descriptions from wildriftfire.

Same AJAX tooltip endpoint as items, with relation_type=Rune:

    GET /ajax/tooltip?relation_type=Rune&relation_id={id}&lang=1

The rune-list page (/rune-list) lists each rune's data-id and its category via
data-sort (e.g. "Keystone", "Resolve Minor", "Domination Minor"). Runes have no
stats or cost — just a name and an effect description.

Output: data/runes.json
Raw fragments cache under data/wrf_cache/ (shared with the item scraper).

Run:
    python -m scripts.scrape_runes
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "runes.json"
CACHE = ROOT / "data" / "wrf_cache"
BASE = "https://www.wildriftfire.com"
LANG = 1
DELAY = 0.5

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": f"{BASE}/rune-list",
}


def fetch(url: str, cache_key: str) -> str:
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / cache_key
    if cached.exists():
        return cached.read_text(encoding="utf-8")
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            cached.write_text(r.text, encoding="utf-8")
            time.sleep(DELAY)
            return r.text
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))
    return ""


def rune_index() -> list[tuple[int, str]]:
    """Return [(rune_id, category)] from the rune-list page."""
    html = fetch(f"{BASE}/rune-list", "rune-list.html")
    rows = re.findall(
        r"ajax-tooltip[^>]*?t:'Rune',i:(\d+)[^>]*?data-sort=\"([^\"]*)\"", html
    )
    seen: dict[int, str] = {}
    for id_str, cat in rows:
        seen.setdefault(int(id_str), cat.strip())
    return sorted(seen.items())


def _slug_from_icon(src: str, fallback: str) -> str:
    m = re.search(r"/([a-z0-9\-]+)\.png", src or "", re.I)
    return m.group(1).lower() if m else fallback


def _split_category(cat: str) -> tuple[str, str]:
    """'Resolve Minor' -> (tree='Resolve', type='Minor'); 'Keystone' -> ('', 'Keystone')."""
    parts = cat.split()
    if len(parts) == 2 and parts[1] in ("Minor", "Major"):
        return parts[0], parts[1]
    return "", cat  # Keystone (tree not given for keystones)


def parse_rune(rune_id: int, category: str) -> dict | None:
    url = f"{BASE}/ajax/tooltip?relation_type=Rune&relation_id={rune_id}&lang={LANG}"
    html = fetch(url, f"rune_{rune_id}.html")
    soup = BeautifulSoup(html, "html.parser")
    root = soup.select_one(".tt--rune") or soup
    title = root.select_one(".tt__info__title span")
    if not title or not title.get_text(strip=True):
        return None
    name = title.get_text(strip=True)

    icon_el = root.select_one(".tt__image img")
    icon = icon_el.get("src", "") if icon_el else ""
    slug = _slug_from_icon(icon, re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-"))

    desc_el = root.select_one(".tt__info__uniques span")
    description = desc_el.get_text(" ", strip=True) if desc_el else ""

    tree, rtype = _split_category(category)
    return {
        "id": rune_id,
        "slug": slug,
        "name": name,
        "tree": tree,            # Resolve / Domination / Precision / Inspiration / '' for keystones
        "type": rtype,           # Keystone / Minor / Major
        "description": description,
        "icon": BASE + icon if icon.startswith("/") else icon,
    }


def main() -> None:
    index = rune_index()
    print(f"found {len(index)} runes")
    runes = []
    for i, (rune_id, cat) in enumerate(index, 1):
        try:
            r = parse_rune(rune_id, cat)
        except Exception as e:  # noqa: BLE001
            print(f"  ! id={rune_id} failed: {e}")
            continue
        if r:
            runes.append(r)
            print(f"  [{i}/{len(index)}] {r['name']:28} ({r['type']}{'/'+r['tree'] if r['tree'] else ''})")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(runes, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(ROOT)} ({len(runes)} runes, {OUT.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
