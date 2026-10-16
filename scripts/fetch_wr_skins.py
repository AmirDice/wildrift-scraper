"""Fetch every champion's skins from the official Wild Rift website.

Each champion page on wildrift.leagueoflegends.com carries an "Available
Skins" carousel in its embedded Next.js data: one entry per skin with its
name and a 1280x720 splash on Riot's CMS image host. This writes them to
web-next/src/data/wr_skins.json keyed by OUR champion slug.

Why not the older champion_skins.json: that is League PC's skin list from
ddragon, which includes skins Wild Rift never had and misses the Wild
Rift exclusives. This is the official Wild Rift list.

Images are not downloaded. The CMS host resizes on request
(``&w=480&fm=webp`` turns a 182 KB JPEG into a 28 KB WebP), so the site
links to it at the size each view needs.

Names arrive upper-case ("ARCADE RIVEN"), the way the official carousel
renders them, and are title-cased here.

Run from the repository root:

    python scripts/fetch_wr_skins.py
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "web-next" / "src" / "data" / "site.json"
OUT = ROOT / "web-next" / "src" / "data" / "wr_skins.json"
BASE = "https://wildrift.leagueoflegends.com/en-gb/champions/"
UA = {"User-Agent": "Mozilla/5.0 (WrTrueMeta skin catalogue; +https://wrtruemeta.com/contact)"}

#: Words kept lower-case inside a title-cased skin name.
SMALL = {"of", "the", "and", "a", "an", "in", "on", "at", "to", "for", "vs"}
#: Tokens kept upper-case (acronyms and roman numerals in skin and champion names).
UPPER = {"PROJECT:", "PROJECT", "PROJEKT:", "IV", "II", "III", "K/DA", "KDA", "SKT", "T1", "DRX",
         "EDG", "DWG", "FPX", "IG", "RNG", "SSG", "SSW", "TPA", "WE", "LCK", "LPL", "MSI", "WR", "2XKO"}


def norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def title(name: str, champion: str = "") -> str:
    words = name.strip().split()
    out = []
    for index, word in enumerate(words):
        lead = len(word) - len(word.lstrip("(\"'"))
        core = word.strip("(),:\"'")
        if core.upper() in UPPER:
            out.append(word.upper())
        elif index and core.lower() in SMALL:
            out.append(word.lower())
        else:
            parts = []
            for part in word.split("-"):
                low = part.lower()
                # first letter after any opening bracket or quote
                parts.append(low[:lead] + low[lead:lead + 1].upper() + low[lead + 1:])
                lead = 0
            out.append("-".join(parts))
    text = " ".join(out)
    # The champion's own name keeps its real casing ("Kai'Sa", "Jarvan IV").
    if champion:
        text = re.sub(re.escape(champion), champion, text, flags=re.I)
    return text


def page_data(url: str) -> dict:
    request = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(request, timeout=30) as response:
        html = response.read().decode("utf-8")
    match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    if not match:
        raise ValueError("no __NEXT_DATA__")
    return json.loads(match.group(1))


def official_slugs() -> list[str]:
    data = json.dumps(page_data(BASE))
    return sorted(set(re.findall(r"/en-gb/champions/([a-z0-9-]+)/", data)))


def skins_of(slug: str, champion: str = "") -> list[dict]:
    page = page_data(f"{BASE}{slug}/")["props"]["pageProps"]["page"]
    for blade in page.get("blades", []):
        if blade.get("type") != "landingMediaCarousel":
            continue
        if "skin" not in str((blade.get("header") or {}).get("title", "")).lower():
            continue
        skins = []
        for group in blade.get("groups", []):
            media = ((group.get("content") or {}).get("media") or {}) or (group.get("thumbnail") or {})
            url = str(media.get("url") or "")
            if not group.get("label") or not url:
                continue
            skins.append({"name": title(str(group["label"]), champion), "image": url})
        return skins
    return []


def main() -> None:
    site = json.loads(SITE.read_text(encoding="utf-8"))
    ours = {norm(champion["slug"]): champion["slug"] for champion in site["champions"]}
    ours.update({norm(champion["name"]): champion["slug"] for champion in site["champions"]})
    names = {champion["slug"]: champion["name"] for champion in site["champions"]}

    champions: dict[str, list[dict]] = {}
    unmatched, empty, failed = [], [], []
    for slug in official_slugs():
        key = norm(slug)
        our = ours.get(key) or ours.get(key.replace("and", "", 1))
        if not our:
            unmatched.append(slug)
            continue
        try:
            skins = skins_of(slug, names[our])
        except Exception as error:  # noqa: BLE001 - report and continue
            failed.append(f"{slug} ({error})")
            continue
        if not skins:
            empty.append(slug)
        champions[our] = skins
        time.sleep(0.4)  # one page at a time, politely

    total = sum(len(skins) for skins in champions.values())
    OUT.write_text(json.dumps({
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source": "wildrift.leagueoflegends.com champion pages, Available Skins",
        "champions": champions,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    missing = sorted(set(c["slug"] for c in site["champions"]) - set(champions))
    print(f"Wrote {OUT.relative_to(ROOT)}: {len(champions)} champions, {total} skins")
    print("Not matched to our roster:", unmatched or "none")
    print("Pages without a skins carousel:", empty or "none")
    print("Failed:", failed or "none")
    print("Our champions with no official page:", missing or "none")


if __name__ == "__main__":
    main()
