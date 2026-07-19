"""Scrape items, runes and spells from wr-meta.com/items/.

The whole tooltip for every entry is present in the static HTML (hover only
toggles visibility), so one request gets everything: no browser needed.

Why this source beats our current item text:
  - stats are TYPED BY ICON (icon-stat/ad.png -> "ad"), not parsed from prose
  - passives arrive pre-split and named ("Wrath:", "Seething Strike:") instead
    of one run-on blob, which is what the effect extractor chokes on
  - runes expose a real formula: base range, per-level flag, AD/AP ratios, CD

Deliberately EXCLUDED: the per-item "TIPS" paragraph. It is editorial prose and
demonstrably wrong (it credits Bloodthirster with a shield and attack speed it
does not have). Feeding it to the extractor would poison the numbers.

Images are downloaded and renamed by our own slug: the source filenames are
meaningless timestamps, and the underlying art is Riot's, not wr-meta's.

Writes (does NOT overwrite live data; diff before promoting):
    data/wrmeta_items.json, data/wrmeta_runes.json, data/wrmeta_spells.json
    web-next/public/items/<slug>.webp

Run:
    python -m scripts.scrape_wrmeta            # data only
    python -m scripts.scrape_wrmeta --images   # also download icons
"""
from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
from pathlib import Path

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
IMG_DIR = ROOT / "web-next" / "public" / "items"
URL = "https://wr-meta.com/items/"
UA = {"User-Agent": "Mozilla/5.0 (compatible; wrtruemeta/1.0)"}

# icon-stat/<file>.png -> our engine stat key. The icon is authoritative: the
# site spells the same stat several ways ("Max Health" / "Maximum Health").
STAT_ICON = {
    "ad": "ad", "ap": "ap", "as": "attackSpeed", "csc": "crit",
    "cdr": "abilityHaste", "armp": "physicalPen", "mpen": "magicPen",
    "hp": "hp", "ar": "armor", "mres": "mr", "ms": "moveSpeed",
    "mana": "mana", "ten": "tenacity",
    # Verified against the labels these icons actually carry on the page, NOT
    # guessed from the filename: "fls" reads as heal/shield but labels Physical
    # Vamp, and "hps" reads as health-per-second but labels Heal and Shield
    # Strength. Getting these backwards fed vamp into heal amplification and
    # dropped heal/shield power on 10 support items.
    "fls": "physicalVamp",
    "hps": "healShieldPower",
    "hpreg": "hpRegen", "mpreg": "manaRegen",
}

ITEM_SECTIONS = {
    "physical damage items": "Physical", "magic damage items": "Magic",
    "defense items": "Defense", "support items": "Support",
    "active spell items": "Active", "boots tier 2": "Boots2",
    "boots tier 3": "Boots3", "mid tier items": "MidTier",
    "basic items": "Basic",
}
RUNE_SECTIONS = {"keystone": "Keystone", "domination": "Domination",
                 "precision": "Precision", "resolve": "Resolve",
                 "sorcery": "Sorcery"}


# The source has Cyrillic homoglyphs in a few names ("Сhilling Smite" opens with
# U+0421, not "C"). NFKD will not fold those, so they would silently vanish.
HOMOGLYPHS = str.maketrans({"С": "C", "с": "c", "А": "A", "а": "a", "Е": "E",
                            "е": "e", "О": "O", "о": "o", "Р": "P", "р": "p",
                            "Т": "T", "У": "y", "Х": "X", "х": "x", "М": "M",
                            "К": "K", "В": "B", "Н": "H", "і": "i"})


def deglyph(s: str) -> str:
    return s.translate(HOMOGLYPHS)


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFKD", deglyph(name)).encode("ascii", "ignore").decode()
    s = s.lower().replace("'", "").replace("&", "and")
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s)).strip("-")


# wr-meta's rune names drift from the in-game/our-data spelling. Alias theirs
# onto ours so rune_effects.json and rune_slots.json keep resolving.
RUNE_ALIASES = {
    "Eyeball Collection": "Eyeball Collector",
    "Grasp of Undying": "Grasp of the Undying",
}

# Source typos and layout artefacts. The extractor reads this text literally and
# grounds numbers against it, so "4 0" or a padded paren is not cosmetic: it
# changes what can be parsed.
_TEXT_FIXES = [
    (r"\bbasick\b", "basic"),
    (r"\bFore every\b", "For every"),
    (r"\bstaking\b", "stacking"),
    (r"\(s\)", "s"),                       # "second(s)" -> "seconds"
    (r"\[perlevel\]", "based on level"),
    (r"\(\s+", "("),
    (r"\s+\)", ")"),
    (r"\s+([,.;:%])", r"\1"),
    (r"(?<=\d)\s+(?=\d\b)", ""),           # "4 0" -> "40"
]


def clean_text(s: str) -> str:
    """Normalise scraped effect text before it reaches the extractor."""
    for pat, rep in _TEXT_FIXES:
        s = re.sub(pat, rep, s)
    return re.sub(r"\s{2,}", " ", s).strip()


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", deglyph(s)).replace(" ", " ").strip()


def _stat_key(b: Tag) -> str | None:
    img = b.find("img")
    if not img or not img.get("src"):
        return None
    return STAT_ICON.get(Path(img["src"]).stem.lower())


def _parse_stat(b: Tag) -> dict | None:
    """'<icon> +55 Attack Damage' -> {key, value, percent}."""
    key = _stat_key(b)
    txt = _clean(b.get_text(" "))
    m = re.search(r"([+-]?\d+(?:\.\d+)?)\s*(%?)", txt)
    if not key or not m:
        return None
    return {"stat": key, "value": float(m.group(1)), "percent": m.group(2) == "%",
            "text": txt}


def _tokenize_icons(p: Tag) -> None:
    """Inline stat icons carry the meaning: '+ 10% extra <img ad.png>' reads as
    '+ 10% extra' once get_text() drops the image. Replace each icon with a text
    token so the ratio keeps its stat. Call AFTER .istats stats are parsed."""
    for img in p.find_all("img"):
        src = img.get("src") or ""
        if "icon-stat/" not in src:
            continue
        stem = Path(src).stem.lower()
        img.replace_with(NavigableString(f" [{STAT_ICON.get(stem, stem)}] "))


def _passives_and_cost(p: Tag) -> tuple[list[dict], int | None, str]:
    """Walk <p> in order. `.istats2` marks a passive NAME; the nodes after it
    are that passive's text, until the next name. `.goldt` is the cost and also
    terminates the useful content: everything after it is the TIPS blurb."""
    passives: list[dict] = []
    cost: int | None = None
    cur: dict | None = None
    tail: list[str] = []
    seen_tagline = False

    for node in p.children:
        if isinstance(node, Tag) and "goldt" in (node.get("class") or []):
            m = re.search(r"\d+", node.get_text())
            cost = int(m.group()) if m else None
            break  # TIPS follows; drop it
        if isinstance(node, Tag) and "istats2" in (node.get("class") or []):
            if cur:
                cur["text"] = _clean(cur["text"])
                passives.append(cur)
            cur = {"name": _clean(node.get_text()).rstrip(":"), "text": ""}
            continue
        cls = set(node.get("class") or []) if isinstance(node, Tag) else set()
        if {"iname", "istats"} & cls:
            continue
        if "cdr" in cls:
            # .cdr is reused: first one is the tagline, later ones are inline
            # labels ("Cooldown:") that belong to the text.
            if not seen_tagline:
                seen_tagline = True
                continue
        txt = node if isinstance(node, NavigableString) else node.get_text(" ")
        if cur is not None:
            cur["text"] += " " + str(txt)
        else:
            tail.append(str(txt))
    if cur:
        cur["text"] = _clean(cur["text"])
        passives.append(cur)
    for p in passives:
        p["text"] = clean_text(p["text"])
    return [x for x in passives if x["text"]], cost, clean_text(_clean(" ".join(tail)))


def _img(box: Tag) -> str:
    im = box.find("img", class_="itemimage") or box.find("img")
    return (im.get("data-src") or im.get("src") or "") if im else ""


def _section_map(soup: BeautifulSoup) -> dict[int, str]:
    """Assign every element to the H2 section above it, by document order."""
    order, cur = {}, None
    for el in soup.find_all(["h2", "div"]):
        if el.name == "h2":
            cur = _clean(el.get_text()).lower()
        else:
            order[id(el)] = cur
    return order


def scrape() -> tuple[list, list, list]:
    html = requests.get(URL, headers=UA, timeout=60).text
    soup = BeautifulSoup(html, "html.parser")
    sect = _section_map(soup)

    items, runes, spells = {}, [], []

    # ---- items + spells: both use .bild-img-short
    for box in soup.select("div.bild-img-short"):
        p = box.find("p")
        name_el = p.find("b", class_="iname") if p else None
        if not p or not name_el:
            continue
        name = _clean(name_el.get_text())
        parent = box.find_parent("div", class_="items")
        section = sect.get(id(parent) if parent else id(box)) or ""
        tag_el = p.find("b", class_="cdr")
        tagline = _clean(tag_el.get_text()) if tag_el else ""
        stats = [s for s in (_parse_stat(b) for b in p.find_all("b", class_="istats")) if s]
        _tokenize_icons(p)          # after _parse_stat: it reads those icons
        passives, cost, desc = _passives_and_cost(p)
        rec = {
            "name": name, "slug": slugify(name),
            "tagline": tagline,
            "stats": stats,
            "passives": passives,
            "cost": cost,
            "image": _img(box),
        }
        if section == "spells" or (cost is None and not rec["stats"]):
            rec.pop("cost", None); rec.pop("stats", None); rec.pop("passives", None)
            rec["description"] = desc
            spells.append(rec)
            continue
        cat = ITEM_SECTIONS.get(section or "", "")
        if rec["slug"] in items:            # listed under several categories
            if cat and cat not in items[rec["slug"]]["categories"]:
                items[rec["slug"]]["categories"].append(cat)
            continue
        rec["categories"] = [cat] if cat else []
        items[rec["slug"]] = rec

    # ---- runes
    for box in soup.select("div.rune-img"):
        p = box.find("p")
        name_el = p.find("b", class_="iname") if p else None
        if not p or not name_el:
            continue
        name = _clean(name_el.get_text())
        cls = box.get("class") or []
        section = sect.get(id(box)) or ""
        tag_el = p.find("b", class_="cdr")
        _tokenize_icons(p)          # runes ARE formulas: keep the ratio stats
        _, _, desc = _passives_and_cost(p)
        name = RUNE_ALIASES.get(name, name)
        runes.append({
            "name": name, "slug": slugify(name),
            "tagline": _clean(tag_el.get_text()) if tag_el else "",
            "tree": RUNE_SECTIONS.get(section, section.title()),
            "type": "Keystone" if "img-big" in cls else "Minor",
            "text": clean_text(desc),
            "image": _img(box),
        })

    return list(items.values()), runes, spells


def rehost_path(r: dict) -> str:
    """OUR path for this record's icon: /items/<our-slug>.<ext>.

    Rewriting the path is a NAMING decision, so it must not depend on whether we
    are downloading right now. It used to live inside fetch_images(), so any
    re-scrape without --images silently reverted every icon to wr-meta's own
    /uploads/... URL -- which both broke the images (we serve /items/) and
    pointed the site at their server, the exact hotlinking we set out to avoid.
    """
    src = r.get("image") or ""
    if not src or src.startswith("/items/"):
        return src
    return f"/items/{r['slug']}{Path(src).suffix or '.webp'}"


def fetch_images(records: list[dict]) -> int:
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    n = 0
    for r in records:
        src = r.get("image") or ""
        if not src or src.startswith("/items/"):
            continue
        url = src if src.startswith("http") else "https://wr-meta.com" + src
        dest = IMG_DIR / f"{r['slug']}{Path(src).suffix or '.webp'}"
        r["image"] = rehost_path(r)
        if dest.exists():
            continue
        try:
            b = requests.get(url, headers=UA, timeout=60).content
            dest.write_bytes(b)
            n += 1
            time.sleep(0.15)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {r['slug']}: {e}")
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", action="store_true", help="download and rehost icons")
    args = ap.parse_args()

    items, runes, spells = scrape()
    # Always OUR path, download or not. See rehost_path().
    for rows in (items, runes, spells):
        for r in rows:
            r["image"] = rehost_path(r)
    print(f"items  {len(items):4}  ({sum(1 for i in items if i['passives'])} with passives, "
          f"{sum(len(i['passives']) for i in items)} passives total)")
    print(f"runes  {len(runes):4}  ({sum(1 for r in runes if r['type']=='Keystone')} keystones)")
    print(f"spells {len(spells):4}")

    if args.images:
        n = fetch_images(items) + fetch_images(runes) + fetch_images(spells)
        print(f"images {n:4}  -> {IMG_DIR.relative_to(ROOT)}")

    for fname, rows in (("wrmeta_items.json", items), ("wrmeta_runes.json", runes),
                        ("wrmeta_spells.json", spells)):
        (DATA / fname).write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
        print(f"wrote data/{fname}")


if __name__ == "__main__":
    main()
