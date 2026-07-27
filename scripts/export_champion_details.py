"""Export per-champion ability cards, skill order and base stats to the frontend.

Sources (all already scraped/cached, no live champion scrape needed):
  - data/champions_wr.json      abilities (slot/name/text/cooldowns) + base stats
  - data/wrmeta_champions.json  skillPriority / skillOrder (max order per level)
  - data/wrf_cache/guide_*.html ability ICON urls (mobafire-hosted Riot art)

The ability icons are Riot's art; like the item images we rehost them locally
(web-next/public/abilities/<file>.png) instead of hotlinking, and reference them
by the local /abilities/<file> path.

Output: web-next/src/data/champion_details.json  (keyed by champion slug)

Run:
    python -m scripts.export_champion_details
    python -m scripts.export_champion_details --no-download   # reuse existing icons
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
DATA = ROOT / "data"
CACHE = DATA / "wrf_cache"
PUBLIC_ABILITIES = ROOT / "web-next" / "public" / "abilities"
OUT = ROOT / "web-next" / "src" / "data" / "champion_details.json"

# slot -> ability key label (Wild Rift: 1=Q 2=W 3=E 4=R, P=passive)
SLOT_KEY = {"P": "Passive", "1": "Q", "2": "W", "3": "E", "4": "R"}
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _canon(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _icons_from_guide(slug: str, start: int = 0, stop: int = 5) -> dict[str, str]:
    """slot -> icon url, parsed from the cached wildriftfire guide page.

    Keyed by slot, so one 5-block group at a time: a transforming champion
    renders both kits and Rhaast's five icons sit in blocks 5-9. Reading all
    ten at once would just overwrite Shadow Assassin's, which is why the caller
    passes a window instead."""
    p = CACHE / f"guide_{slug}.html"
    if not p.exists():
        return {}
    soup = BeautifulSoup(p.read_text(encoding="utf-8"), "html.parser")
    out: dict[str, str] = {}
    for block in soup.select(".statsBlock.abilities .statsBlock__block")[start:stop]:
        name_el = block.select_one(".upper .name span")
        img = block.select_one(".upper img")
        slot = name_el.get_text(strip=True) if name_el else ""
        src = (img.get("src") or img.get("data-src")) if img else None
        if slot and src:
            out[slot] = src
    return out


# some guide pages emit scheme-less, page-relative icon srcs; resolve to origin
WRF_BASE = "https://www.wildriftfire.com"


def _abs_url(url: str) -> str:
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return WRF_BASE + url
    return url


def _download(url: str, headers: dict | None = None) -> str | None:
    """Rehost one icon; returns the /abilities/<file> path (or None on failure)."""
    url = _abs_url(url)
    fname = url.rsplit("/", 1)[-1].split("?")[0]
    if not fname:
        return None
    dest = PUBLIC_ABILITIES / fname
    web = f"/abilities/{fname}"
    if dest.exists() and dest.stat().st_size > 0:
        return web
    try:
        r = requests.get(url, headers=headers or HEADERS, timeout=25)
        r.raise_for_status()
        PUBLIC_ABILITIES.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
        time.sleep(0.15)
        return web
    except requests.RequestException:
        return None


# --- per-form ability icons ------------------------------------------------
# Champions who switch kits freely share ONE tooltip and ONE icon per slot on
# the guide page ("Javelin Toss / Takedown" has a single combined image), so
# the cougar half would render with the human icon. The League wiki publishes
# the two forms separately, so the halves are looked up there by name.
# Restricted to a named set: this is an extra network round-trip per ability,
# and a slash in a name does not otherwise mean "two forms".
WIKI_API = "https://wiki.leagueoflegends.com/en-us/api.php"
WIKI_FORM_ICON_CHAMPIONS = {"Nidalee"}
# The wiki 403s the generic browser User-Agent the guide scrape uses; MediaWiki
# asks automated clients to identify themselves and a contact, so we do.
WIKI_HEADERS = {"User-Agent": "wrtruemeta-icon-fetch/1.0 (+https://wrtruemeta.com)"}


def _wiki_form_icons(champion: str, halves: list[str]) -> dict[str, str]:
    """ability half -> icon url, from the wiki's Wild Rift ability icon files."""
    titles = "|".join(f"File:{champion} {h} WR.png" for h in halves)
    try:
        r = requests.get(WIKI_API, params={"action": "query", "titles": titles,
                                           "prop": "imageinfo", "iiprop": "url",
                                           "format": "json"},
                         headers=WIKI_HEADERS, timeout=25)
        r.raise_for_status()
        pages = (r.json().get("query") or {}).get("pages") or {}
    except (requests.RequestException, ValueError):
        return {}
    out: dict[str, str] = {}
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        title, url = page.get("title", ""), info.get("url")
        if not url:
            continue
        for h in halves:                       # match the title back to its half
            if title == f"File:{champion} {h} WR.png":
                out[h] = url
    return out

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-download", action="store_true",
                    help="don't fetch icons; only map ones already rehosted")
    args = ap.parse_args()

    champs = json.loads((DATA / "champions_wr.json").read_text(encoding="utf-8"))
    wrmeta = json.loads((DATA / "wrmeta_champions.json").read_text(encoding="utf-8"))
    wrmeta_by_canon = {_canon(k): v for k, v in wrmeta.items()}

    out: dict[str, dict] = {}
    n_icons = 0
    # A transform form is exported as its own entry, keyed by its own slug
    # ("kayn-rhaast"), because the frontend looks ability cards up by slugifying
    # the champion name it is showing -- "Kayn (Rhaast)" slugifies to exactly
    # that. Without an entry the form's panel renders with no icons at all.
    # (record, its own slug, the guide slug its icons live on, icon block offset)
    entries = [(c, c["slug"], c["slug"], 0) for c in champs]
    entries += [(f, f["slug"], c["slug"], 5)
                for c in champs for f in (c.get("forms") or [])]
    for c, slug, guide_slug, icon_start in entries:
        icons = _icons_from_guide(guide_slug, icon_start, icon_start + 5)
        abilities = []
        for a in c.get("abilities", []):
            slot = a.get("slot", "")
            url = icons.get(slot)
            icon = None
            if url:
                icon = f"/abilities/{url.rsplit('/', 1)[-1].split('?')[0]}" if args.no_download else _download(url)
                if icon:
                    n_icons += 1
            card = {
                "slot": slot,
                "key": SLOT_KEY.get(slot, slot),
                "name": a.get("name", ""),
                "text": a.get("text", ""),
                "cooldowns": a.get("cooldowns", []),
                "damageTypes": a.get("damageTypes", []),
                "icon": icon,
            }
            # One icon per form, in the order the two halves are named.
            halves = [h.strip() for h in card["name"].split(" / ")]
            if c["name"] in WIKI_FORM_ICON_CHAMPIONS and len(halves) == 2:
                urls = _wiki_form_icons(c["name"], halves)
                per_form = [_download(urls[h], WIKI_HEADERS) if h in urls else None
                            for h in halves]
                if any(per_form):
                    card["formIcons"] = [p or icon for p in per_form]
                    n_icons += sum(1 for p in per_form if p)
            abilities.append(card)
        # A form levels the same abilities as the champion it belongs to, so it
        # inherits the parent's skill priority rather than having none.
        wm = wrmeta_by_canon.get(_canon(c.get("formOf") or c["name"]), {})
        # skillPriority is the max order of the 3 basics, as slots; map to keys
        prio = [SLOT_KEY.get(s, s) for s in (wm.get("skillPriority") or []) if s in ("1", "2", "3")]
        out[slug] = {
            "name": c["name"],
            "baseStats": c.get("baseStats", {}),
            "abilities": abilities,
            "skillPriority": prio,
        }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(out)} champions, {n_icons} ability icons "
          f"({OUT.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
