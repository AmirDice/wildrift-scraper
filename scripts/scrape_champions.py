"""Scrape Wild Rift champion base stats + abilities from wildriftfire guides.

Each champion has a guide at /guide/{slug}. That single page contains:
  - base stats  (.wf-champion__about__stats, via data-base / data-increase)
  - all 5 abilities (.statsBlock.abilities) with cooldowns, base damage,
    scaling ratios (+75% AD) and damage types (physical / magic / true).

From the ability text we derive the champion's *damage profile* and mechanic
tags, which the build optimizer uses to know what stats/items/runes fit:
  - primaryDamage: physical | magic         (item damage-type gating)
  - scalesWith:    {ad, ap, bonusAd, maxHp, attackSpeed}
  - tags:          {dash, cc, shield, heal, onHit}

Slugs come from the homepage's /guide/{slug} links.

Output: data/champions_wr.json
Raw pages cache under data/wrf_cache/.

Run:
    python -m scripts.scrape_champions
    python -m scripts.scrape_champions --limit 5
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
OUT = ROOT / "data" / "champions_wr.json"
CACHE = ROOT / "data" / "wrf_cache"
BASE = "https://www.wildriftfire.com"
DELAY = 0.5

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": f"{BASE}/",
}

STAT_LABELS = {
    "Health": "hp",
    "Health Reg. (5s)": "hpRegen",
    # Mana was missing from this map, not from the source: the page has carried
    # data-base/data-increase for it all along. Its absence is why the engine
    # assumed a flat 500 base mana for every champion, which mispriced every
    # mana item (Muramana grants AD = % of MAX MANA) and made mana-hungry kits
    # indistinguishable from mana-light ones.
    "Mana": "mana",
    "Mana Reg. (5s)": "manaRegen",
    "Armor": "armor",
    "Magic Res.": "mr",
    "Move Speed": "moveSpeed",
    "Attack Dmg.": "ad",
    "Attack Spd.": "attackSpeed",
}


def fetch(url: str, cache_key: str, refresh: bool = False) -> str:
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / cache_key
    if cached.exists() and not refresh:
        return cached.read_text(encoding="utf-8")
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=25)
            r.raise_for_status()
            cached.write_text(r.text, encoding="utf-8")
            time.sleep(DELAY)
            return r.text
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))
    return ""


def champion_slugs() -> list[str]:
    html = fetch(f"{BASE}/", "home.html")
    slugs = sorted(set(re.findall(r"/guide/([a-z0-9\-]+)", html)))
    return slugs


def _base_stats(soup: BeautifulSoup) -> dict:
    out = {}
    for block in soup.select(".statsBlock.champion .statsBlock__block"):
        name_el = block.select_one(".name")
        val_el = block.select_one(".value")
        if not name_el or not val_el:
            continue
        label = name_el.get_text(strip=True)
        key = STAT_LABELS.get(label)
        if not key:
            continue
        base = val_el.get("data-base")
        inc = val_el.get("data-increase")
        try:
            base_f = float(base)
            inc_f = float(inc) if inc is not None else 0.0
        except (TypeError, ValueError):
            continue
        out[key] = {
            "base": base_f,
            "perLevel": inc_f,
            "lvl15": round(base_f + inc_f * 14, 1),
        }
    return out


def _analyse_ability(text: str) -> dict:
    t = text.lower()
    dtypes = []
    for dt in ("physical damage", "magic damage", "true damage"):
        if dt in t:
            dtypes.append(dt.split()[0])  # physical / magic / true
    scales = set()
    if re.search(r"%\s*ad\b", t) or "bonus ad" in t:
        scales.add("ad")
    if "bonus ad" in t:
        scales.add("bonusAd")
    if re.search(r"%\s*ap\b", t) or "ability power" in t:
        scales.add("ap")
    if "maximum health" in t or "max health" in t or "maximum hp" in t:
        scales.add("maxHp")
    if "attack speed" in t:
        scales.add("attackSpeed")
    tags = set()
    if any(k in t for k in ("dash", "blink", "leap", "lunge", "vault", "teleport", "charge")):
        tags.add("dash")
    if any(k in t for k in ("stun", "root", "snare", "slow", "knock", "taunt", "charm",
                            "fear", "suppress", "airborne", "immobiliz", "pull", "grab")):
        tags.add("cc")
    if "shield" in t:
        tags.add("shield")
    if any(k in t for k in ("heal", "restore", "lifesteal", "life steal", "vamp")):
        tags.add("heal")
    if any(k in t for k in ("on-hit", "on hit", "basic attack", "next attack",
                            "empowered attack", "next basic")):
        tags.add("onHit")
    return {"damageTypes": dtypes, "scales": sorted(scales), "tags": sorted(tags)}


# --- source typo corrections ------------------------------------------------
# The guide pages are hand-maintained and occasionally miscount a rank list.
# Extraction transcribes faithfully and must not "fix" numbers on its own, so
# corrections belong here, at the source, where they are visible and survive a
# re-scrape. Keep each one narrow: an exact string, only for the ability it
# belongs to, so it silently stops applying if the page is ever corrected.
SOURCE_TEXT_FIXES: list[tuple[str, str, str, str]] = [
    # slug, ability-name fragment, wrong, right
    # Rhaast's Reaping Slash lists FIVE values for a four-rank ability. Rank 4
    # then read 130 instead of 160, undercounting his main damage ability.
    ("kayn", "Reaping Slash: Rhaast",
     "70 / 100 / 130 / 130 / 160", "70 / 100 / 130 / 160"),
    # "Heath" for "Health". Extraction reads a closed vocabulary of stat names,
    # so the misspelling made Dominus grant nothing at all.
    ("renekton", "Dominus", "750 Heath", "750 Health"),
]


def _fix_source_text(slug: str, name: str, text: str) -> str:
    for fix_slug, fragment, wrong, right in SOURCE_TEXT_FIXES:
        if fix_slug == slug and fragment in name and wrong in text:
            text = text.replace(wrong, right)
    return text


def _abilities(soup: BeautifulSoup, start: int = 0, stop: int = 5, slug: str = "") -> list[dict]:
    """Parse one 5-block ability group.

    A transforming champion renders both kits: Kayn's page carries 10 blocks,
    Shadow Assassin then Rhaast. Only the first five were ever read, so half of
    his kit -- the healing, the max-Health damage, the knock-up -- never
    existed in the data, and the engine simulated one form for both."""
    out = []
    for block in soup.select(".statsBlock.abilities .statsBlock__block")[start:stop]:
        name_el = block.select_one(".upper .name")
        if not name_el:
            continue
        slot_el = name_el.select_one("span")
        slot = slot_el.get_text(strip=True) if slot_el else ""
        name = name_el.get_text(" ", strip=True)
        if slot:
            name = name.replace(slot, "", 1).strip()
        cds = [s.get_text(strip=True) for s in block.select(".cooldown span")]
        # Some abilities wrap the description in <p> tags, others put text straight
        # in the .lower div (e.g. Hecarim's Warpath) — take the whole node's text.
        lower = block.select_one(".lower")
        text = _fix_source_text(slug, name, lower.get_text(" ", strip=True) if lower else "")
        an = _analyse_ability(text)
        out.append({
            "slot": slot,             # P / 1 / 2 / 3 / 4
            "name": name,
            "cooldowns": cds,
            "text": text,
            **an,
        })
    return out


def _derive_profile(abilities: list[dict], base_stats: dict) -> dict:
    phys = magic = 0
    scales: set[str] = set()
    tags: set[str] = set()
    for a in abilities:
        for d in a["damageTypes"]:
            if d == "physical":
                phys += 1
            elif d == "magic":
                magic += 1
        scales.update(a["scales"])
        tags.update(a["tags"])
    # base AD scaling counts toward physical identity
    primary = "physical" if phys >= magic else "magic"
    return {
        "primaryDamage": primary,
        "physicalAbilities": phys,
        "magicAbilities": magic,
        "scalesWith": sorted(scales),
        "mechanics": sorted(tags),
    }


# pages whose displayed name differs from the champion (transform forms, etc.)
SLUG_NAME_OVERRIDES = {"kayn": "Kayn"}


def _name_from_page(soup: BeautifulSoup, slug: str) -> str:
    if slug in SLUG_NAME_OVERRIDES:
        return SLUG_NAME_OVERRIDES[slug]
    h2 = soup.select_one(".statsBlock.champion h2")
    if h2:
        # h2 reads "Level 1 <Champion> Stats" — drop the leading "Level N".
        m = re.search(r"Level\s*\d+\s+(.+?)\s+Stats", h2.get_text(" ", strip=True))
        if m:
            return m.group(1).strip()
    return slug.replace("-", " ").title()


def _form_label(abilities: list[dict]) -> str:
    """The form's name, taken from the suffix the page puts on every ability.

    Rhaast's abilities all read "Reaping Slash: Rhaast", so the text after the
    last colon names the form. Falls back to nothing if the page does not
    follow that convention, in which case the form is skipped rather than
    guessed at."""
    suffixes = {a["name"].rsplit(":", 1)[1].strip()
                for a in abilities if ":" in a["name"]}
    return suffixes.pop() if len(suffixes) == 1 else ""


def parse_champion(slug: str, refresh: bool = False) -> dict | None:
    html = fetch(f"{BASE}/guide/{slug}", f"guide_{slug}.html", refresh=refresh)
    soup = BeautifulSoup(html, "html.parser")
    abilities = _abilities(soup, slug=slug)
    if not abilities:
        return None
    base_stats = _base_stats(soup)
    profile = _derive_profile(abilities, base_stats)
    champ = {
        "slug": slug,
        "name": _name_from_page(soup, slug),
        "baseStats": base_stats,
        **profile,
        "abilities": abilities,
    }
    # Second kit, for champions who transform. It is a full champion record so
    # the formula extractor and the damage engine can treat it as one, sharing
    # the base stats (the same champion, a different kit).
    alt = _abilities(soup, 5, 10, slug=slug)
    label = _form_label(alt) if alt else ""
    if label:
        key = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
        champ["forms"] = [{
            "slug": f"{slug}-{key}",
            "formKey": key,
            "formOf": champ["name"],
            "formLabel": label,
            "name": f"{champ['name']} ({label})",
            "baseStats": base_stats,
            **_derive_profile(alt, base_stats),
            "abilities": alt,
        }]
    return champ


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    # Newly released champions are the usual reason to re-run this: their guide
    # was cached back when the page still said "coming soon" (zeroed stats, no
    # build), so --only <slug> --refresh re-fetches just those pages and merges
    # them into the existing champions_wr.json instead of rebuilding all 140.
    ap.add_argument("--only", default="", help="comma-separated slugs to scrape")
    ap.add_argument("--refresh", action="store_true", help="ignore the HTML cache")
    args = ap.parse_args()

    only = [s.strip() for s in args.only.split(",") if s.strip()]
    slugs = only or champion_slugs()
    if args.limit:
        slugs = slugs[: args.limit]
    print(f"found {len(slugs)} champion slugs")

    champs = []
    for i, slug in enumerate(slugs, 1):
        try:
            c = parse_champion(slug, refresh=args.refresh)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {slug} failed: {e}")
            continue
        if c:
            champs.append(c)
            print(f"  [{i}/{len(slugs)}] {c['name']:16} {c['primaryDamage']:8} "
                  f"scales={c['scalesWith']} mech={c['mechanics']}")
        else:
            print(f"  [{i}/{len(slugs)}] {slug}: no abilities parsed (skipped)")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    if only and OUT.exists():
        # Merge into the existing file, keyed by slug, so a targeted run never
        # drops the champions it did not ask for.
        existing = json.loads(OUT.read_text(encoding="utf-8"))
        by_slug = {c["slug"]: c for c in existing}
        for c in champs:
            by_slug[c["slug"]] = c
        champs = sorted(by_slug.values(), key=lambda c: c["slug"])

    OUT.write_text(json.dumps(champs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(ROOT)} ({len(champs)} champions, {OUT.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
