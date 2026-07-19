"""Scrape per-ability MANA COSTS (and cooldowns, and class) from wr-meta.

Why: we had no mana costs at all. Without them the engine cannot tell that
Hecarim, Ryze or Kassadin actually drain their bar, so mana items and mana regen
are priced by a behaviour guess rather than by what a rotation really costs.

wildriftfire (our champion source) does publish costs, but wr-meta is patch
7.2-current, and its ability blocks are icon-typed exactly like the item page:

    <img src="icon-stat/cdr.png">  7s              <- cooldown
    <img src="icon-stat/Mana.png"> 65/70/75/80     <- mana cost, per rank

Reading the icon rather than the prose is what makes this unambiguous.

The six class pages also give an authoritative champion class for free.

Writes data/wrmeta_champions.json (does NOT overwrite champions_wr.json; use
merge_mana_costs.py to promote).

Run:
    python -m scripts.scrape_wrmeta_champions
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "wrmeta_champions.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; wrtruemeta/1.0)"}

# lxml, NOT html.parser: on this markup html.parser fails to treat <img> as a
# void element, so the "7s" after a cooldown icon is parsed as a CHILD of the
# img. Every cooldown and mana cost then reads as empty.
PARSER = "lxml"

CLASS_PAGES = {
    "https://wr-meta.com/assassins/": "Assassin",
    "https://wr-meta.com/fighters/": "Fighter",
    "https://wr-meta.com/mages/": "Mage",
    "https://wr-meta.com/marksmans/": "Marksman",
    "https://wr-meta.com/supports/": "Support",
    "https://wr-meta.com/tanks/": "Tank",
}

# wr-meta marks abilities Q/W/E/R; our data uses 1/2/3/4 with P for the passive.
SLOT_MAP = {"P": "P", "Q": "1", "W": "2", "E": "3", "R": "4"}

# The listings are ALL-CAPS, so .title() mangles names with numerals or particles
# ("JARVAN IV" -> "Jarvan Iv"). Map those onto our spelling.
NAME_FIXES = {"Jarvan Iv": "Jarvan IV", "Dr. Mundo": "Dr. Mundo",
              "Nunu & Willump": "Nunu & Willump", "Kai'Sa": "Kai'Sa"}


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).replace("\xa0", " ").strip()


def _ranks(s: str) -> list[float]:
    """'65/70/75/80' -> [65, 70, 75, 80]; '7s' -> [7]."""
    return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", s)]


def _after(flat: str, token: str) -> list[float]:
    """Numbers in the ONE slash-separated run right after an icon token:
    '@MANA@ 65/70/75/80' -> [65,70,75,80]; '@CD@ 7s' -> [7].

    The run must not cross whitespace. Allowing \\s here made the match run past
    the cooldown and swallow the next number on the line, producing five values
    for a four-rank ability ("12/11/10/9 70" -> [12,11,10,9,70]) and cooldowns
    that appeared to RISE with rank.
    """
    i = flat.find(token)
    if i < 0:
        return []
    tail = flat[i + len(token):].lstrip()
    m = re.match(r"\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)*", tail)
    return _ranks(m.group()) if m else []


def champion_links() -> dict[str, str]:
    """slug/url -> class, from the six class listings."""
    out: dict[str, tuple[str, str]] = {}
    for url, cls in CLASS_PAGES.items():
        soup = BeautifulSoup(requests.get(url, headers=UA, timeout=60).text, PARSER)
        for a in soup.select("a[href]"):
            href, name = a["href"], _clean(a.get_text())
            if re.search(r"/\d+-[a-z0-9-]+\.html$", href) and name and name.isupper():
                nice = NAME_FIXES.get(name.title(), name.title())
                out.setdefault(nice, (href, cls))
        time.sleep(0.2)
    return out


def _slot_of(text: str) -> str:
    """'(Q) ORB OF DECEPTION' -> '1'."""
    m = re.match(r"\s*\((\w)\)", text or "")
    return SLOT_MAP.get(m.group(1).upper(), "") if m else ""


def parse_extras(soup: BeautifulSoup) -> dict:
    """Skill order and hard counters.

    Skill order: each ability's <h4> owns a <ul> of <li level="N">, so level N
    is where that ability is ranked up. Reconstructs level -> slot for all 15.

    Counters: wr-meta curates a short "Threats" list (Ahri gets three), which is
    the hard-counter set. "Synergies" is a separate list and is NOT a counter.
    Neither carries a severity grade, so we take Threats verbatim rather than
    invent a ranking.
    """
    order: dict[str, str] = {}
    for li in soup.select("li[level]"):
        h4 = li.find_previous("h4")
        slot = _slot_of(h4.get_text(" ", strip=True)) if h4 else ""
        lvl = li.get("level")
        if slot and lvl:
            order[str(lvl)] = slot

    priority: list[str] = []
    for t in soup.select(".bild-tips"):
        txt = _clean(t.get_text(" "))
        if "skill order" in txt.lower():
            priority = [SLOT_MAP.get(x.upper(), x) for x in re.findall(r"\((\w)\)", txt)]
            break

    threats: list[str] = []
    synergies: list[str] = []
    cur = None
    for el in soup.find_all(True):
        cls = " ".join(el.get("class") or [])
        if "bildtitle5" in cls:
            t = el.get_text(strip=True)
            if t in ("Threats", "Synergies"):
                cur = t
        elif "counter-champion" in cls and cur:
            nm = el.select_one(".top-title")
            if nm:
                (threats if cur == "Threats" else synergies).append(
                    _clean(nm.get_text()).title())
    return {"skillOrder": order, "skillPriority": priority,
            "hardCounters": threats, "synergies": synergies}


def parse_champion(url: str) -> list[dict]:
    soup = BeautifulSoup(requests.get(url, headers=UA, timeout=60).text, PARSER)
    abilities = []
    for hold in soup.select(".ability-holder"):
        marker = hold.select_one(".ability-marker")
        p = hold.find("p")
        if not p:
            continue
        slot_raw = _clean(marker.get_text()) if marker else ""
        title = p.find("b")
        name = ""
        if title:
            name = _clean(re.sub(r"\(.*?\)", "", title.get_text(" ")))

        # Icons type the two numbers: cdr.png = cooldown, Mana.png = mana cost.
        # Walking next_siblings does NOT work: this markup makes html.parser
        # treat <img> as non-void, so the "7s" ends up INSIDE the img tag and it
        # has no siblings. Tokenise the icons into the text instead, then read
        # the number that follows each marker.
        for img in p.find_all("img"):
            stem = Path(img.get("src") or "").stem.lower()
            token = {"cdr": " @CD@ ", "mana": " @MANA@ "}.get(stem)
            img.replace_with(token if token else " ")
        flat = _clean(p.get_text(" "))
        cd = _after(flat, "@CD@")
        cost = _after(flat, "@MANA@")

        abilities.append({
            "slot": SLOT_MAP.get(slot_raw, slot_raw),
            "name": name,
            "cooldowns": cd,
            "manaCosts": cost,
        })
    return {"abilities": abilities, **parse_extras(soup)}


def _released(rec: dict) -> bool:
    """wr-meta publishes PREVIEW pages for champions not yet in Wild Rift: the
    abilities are named but carry no cooldowns and no costs. A released champion
    always has cooldowns, even a resourceless one (Katarina has no mana but does
    have CDs). So "no cooldowns anywhere" means unreleased, not a parse failure.
    """
    return any(a["cooldowns"] for a in rec.get("abilities") or [])


def main() -> None:
    links = champion_links()
    print(f"{len(links)} champions found across {len(CLASS_PAGES)} class pages")
    out = {}
    for i, (name, (url, cls)) in enumerate(sorted(links.items()), 1):
        try:
            rec = parse_champion(url)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {name}: {e}")
            continue
        rec = {"name": name, "class": cls, "url": url, **rec}
        rec["released"] = _released(rec)
        out[name] = rec
        if i % 25 == 0:
            print(f"  [{i}/{len(links)}] {name}")
        time.sleep(0.25)

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    live = {n: c for n, c in out.items() if c["released"]}
    unrel = sorted(n for n, c in out.items() if not c["released"])
    tot = sum(len(c["abilities"]) for c in live.values())
    cst = sum(1 for c in live.values() for a in c["abilities"] if a["manaCosts"])
    sk = sum(1 for c in live.values() if c["skillOrder"])
    th = sum(1 for c in live.values() if c["hardCounters"])
    print(f"\nwrote {OUT.relative_to(ROOT)}")
    print(f"  {len(out)} pages | {len(live)} RELEASED | {len(unrel)} unreleased (preview pages)")
    print(f"  released: {tot} abilities | {cst} with mana costs | {sk} skill orders "
          f"| {th} hard-counter lists")
    print(f"  unreleased: {', '.join(unrel[:12])}{' ...' if len(unrel) > 12 else ''}")


if __name__ == "__main__":
    main()
