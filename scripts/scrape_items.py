"""Scrape Wild Rift item stats + passives from wildriftfire's tooltip endpoint.

We pull only *factual game data* (item names, costs, stats, passive text) — not
their build recommendations. The item list lives at /item-list where each item
is a hover-tooltip loaded on demand from an AJAX endpoint:

    GET /ajax/tooltip?relation_type=Item&relation_id={id}&lang=1

which returns a small HTML fragment (.tt--item) we parse into structured JSON.

Output: data/items.json  — the canonical item dataset the build optimizer reads.
Raw fragments are cached under data/wrf_cache/ so re-runs don't re-hit the site.

Run:
    python -m scripts.scrape_items          # scrape everything
    python -m scripts.scrape_items --limit 5  # quick test
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "items.json"
CACHE = ROOT / "data" / "wrf_cache"
BASE = "https://www.wildriftfire.com"
LANG = 1
DELAY = 0.5  # polite pause between requests (seconds)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": f"{BASE}/item-list",
}

# --- canonical stat names -------------------------------------------------
STAT_KEYS = {
    "ability power": "ap",
    "attack damage": "ad",
    "attack speed": "attackSpeed",
    "critical strike chance": "crit",
    "critical rate": "crit",
    "critical strike": "crit",
    "armor": "armor",
    "magic resist": "mr",
    "magic resistance": "mr",
    "health": "hp",
    "max health": "hp",
    "mana": "mana",
    "ability haste": "abilityHaste",
    "magic penetration": "magicPen",
    "physical penetration": "physicalPen",
    "armor penetration": "physicalPen",
    "lethality": "lethality",
    "move speed": "moveSpeed",
    "movement speed": "moveSpeed",
    "life steal": "lifesteal",
    "physical vamp": "physicalVamp",
    "omnivamp": "omnivamp",
    "heal and shield power": "healShieldPower",
    "hp regen": "hpRegen",
    "mana regen": "manaRegen",
    "base mana regen": "manaRegen",
    "base health regen": "hpRegen",
    "tenacity": "tenacity",
}

# --- keyword -> passive tags (auto-tag the optimizer keys off) -------------
TAG_RULES = [
    ("antiHeal", ("grievous", "healing is reduced", "reduces healing", "wounds")),
    ("armorShred", ("reduces armor", "armor is reduced", "sunder", "shred")),
    ("magicPen", ("magic penetration", "magic pen")),
    ("lethality", ("lethality", "armor penetration")),
    ("onHit", ("on-hit", "on hit")),
    ("shield", ("shield", "barrier")),
    ("sustain", ("heal", "vamp", "life steal", "lifesteal", "regenerate")),
    ("slow", ("slow",)),
    ("burn", ("burn", "damage over time", "per second")),
    ("mana", ("mana", "spellblade")),
    ("mobility", ("move speed", "movement speed", "dash", "haste")),
]


def fetch(url: str, cache_key: str) -> str:
    """GET with disk cache + retries."""
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
        except requests.RequestException as e:
            if attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))
    return ""


def item_index() -> list[tuple[int, str]]:
    """Return [(item_id, category)] from the item-list page."""
    html = fetch(f"{BASE}/item-list", "item-list.html")
    rows = re.findall(
        r"ajax-tooltip[^>]*?t:'Item',i:(\d+)[^>]*?data-sort=\"([^\"]*)\"", html
    )
    seen: dict[int, str] = {}
    for id_str, cat in rows:
        seen.setdefault(int(id_str), cat)  # keep first category seen
    return sorted(seen.items())


def _num(text: str) -> tuple[float | None, bool]:
    """Parse '+100' / '+7%' -> (value, is_percent)."""
    is_pct = "%" in text
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    return (float(m.group()) if m else None, is_pct)


def _slug_from_icon(src: str, fallback: str) -> str:
    m = re.search(r"/([a-z0-9\-]+)\.png", src or "", re.I)
    return m.group(1).lower() if m else fallback


def parse_item(item_id: int, category: str) -> dict | None:
    url = f"{BASE}/ajax/tooltip?relation_type=Item&relation_id={item_id}&lang={LANG}"
    html = fetch(url, f"item_{item_id}.html")
    soup = BeautifulSoup(html, "html.parser")
    root = soup.select_one(".tt--item") or soup
    title = root.select_one(".tt__info__title span")
    if not title or not title.get_text(strip=True):
        return None
    name = title.get_text(strip=True)

    cost_el = root.select_one(".tt__info__cost span")
    cost = None
    if cost_el:
        c, _ = _num(cost_el.get_text())
        cost = int(c) if c is not None else None

    icon_el = root.select_one(".tt__image img")
    icon = icon_el.get("src", "") if icon_el else ""
    slug = _slug_from_icon(icon, re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-"))

    stats: dict[str, dict] = {}
    for sp in root.select(".tt__info__stats > span"):
        val_span = sp.find("span")
        if not val_span:
            continue
        value, is_pct = _num(val_span.get_text())
        label = sp.get_text(" ", strip=True).replace(val_span.get_text(strip=True), "").strip()
        key = STAT_KEYS.get(label.lower())
        if key and value is not None:
            stats[key] = {"value": value, "percent": is_pct}

    passives = [
        s.get_text(" ", strip=True)
        for s in root.select(".tt__info__uniques span")
        if s.get_text(strip=True)
    ]
    passive_text = " ".join(passives).lower()
    tags = sorted({tag for tag, kws in TAG_RULES if any(k in passive_text for k in kws)})

    return {
        "id": item_id,
        "slug": slug,
        "name": name,
        "category": category,          # Physical / Magic / Defense / Enchantment / Boots
        "cost": cost,
        "stats": stats,                # {ap:{value,percent}, ...}
        "passives": passives,          # list of unique passive strings
        "tags": tags,                  # auto-derived optimizer tags
        "icon": BASE + icon if icon.startswith("/") else icon,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="only scrape first N items")
    ap.add_argument("--fresh", action="store_true", help="ignore cache")
    args = ap.parse_args()

    if args.fresh and CACHE.exists():
        for f in CACHE.glob("*.html"):
            f.unlink()

    index = item_index()
    if args.limit:
        index = index[: args.limit]
    print(f"found {len(index)} items")

    items = []
    for i, (item_id, cat) in enumerate(index, 1):
        try:
            it = parse_item(item_id, cat)
        except Exception as e:  # noqa: BLE001
            print(f"  ! id={item_id} failed: {e}")
            continue
        if it:
            items.append(it)
            print(f"  [{i}/{len(index)}] {it['name']}  ({cat}, {it['cost']})  tags={it['tags']}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(ROOT)} ({len(items)} items, {OUT.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
