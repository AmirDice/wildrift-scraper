"""Extract champion matchups (strong / weak against) from wildriftfire guides.

wildriftfire lists each champion's "Countered By" set (the champions it is WEAK
against). It has no explicit "strong against", so we derive it by inversion:
champion A is STRONG against B whenever B's counter list contains A.

Guide pages are already cached locally (data/wrf_cache/guide_<slug>.html) from
the champion scrape, so this re-parses the cache — no network needed. Falls back
to fetching if a page is missing.

Output: data/counters.json  { slug: { weak: [slug...], strong: [slug...] } }

Run:
    python -m scripts.scrape_counters
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "web-next" / "src" / "data" / "site.json"
CACHE = ROOT / "data" / "wrf_cache"
OUT = ROOT / "data" / "counters.json"
BASE = "https://www.wildriftfire.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": f"{BASE}/"}

LANES = {"solo", "jungle", "mid", "duo", "support", "baron", "dragon", "adc", "bot"}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _guide_html(slug: str) -> str | None:
    p = CACHE / f"guide_{slug}.html"
    if p.exists():
        return p.read_text(encoding="utf-8", errors="replace")
    try:
        r = requests.get(f"{BASE}/guide/{slug}", headers=HEADERS, timeout=20)
        r.raise_for_status()
        CACHE.mkdir(parents=True, exist_ok=True)
        p.write_text(r.text, encoding="utf-8")
        time.sleep(0.5)
        return r.text
    except requests.RequestException:
        return None


def _countered_by(html: str, norm_to_slug: dict[str, str]) -> list[str]:
    """Champions that counter this champion (from 'Countered By' blocks)."""
    soup = BeautifulSoup(html, "html.parser")
    slugs: list[str] = []
    for blk in soup.select(".wf-champion__data__counters"):
        head = blk.get_text(" ", strip=True).lower()
        if "countered by" not in head:
            continue  # skip 'Synergizes With' blocks
        for im in blk.select("img"):
            alt = im.get("alt") or ""
            if _norm(alt) in LANES:
                continue
            slug = norm_to_slug.get(_norm(alt))
            if slug and slug not in slugs:
                slugs.append(slug)
    return slugs


def main() -> None:
    champs = json.loads(SITE.read_text(encoding="utf-8"))["champions"]
    norm_to_slug = {_norm(c["name"]): c["slug"] for c in champs}
    norm_to_slug.update({_norm(c["slug"]): c["slug"] for c in champs})
    slugs = [c["slug"] for c in champs]

    weak: dict[str, list[str]] = {}
    for i, slug in enumerate(slugs, 1):
        html = _guide_html(slug)
        if not html:
            print(f"  ! {slug}: no page")
            continue
        weak[slug] = _countered_by(html, norm_to_slug)

    # derive strong-against by inverting: A is strong vs B if A counters B
    strong: dict[str, list[str]] = {s: [] for s in slugs}
    for victim, counters in weak.items():
        for c in counters:
            if c in strong and victim not in strong[c]:
                strong[c].append(victim)

    out = {s: {"weak": weak.get(s, []), "strong": strong.get(s, [])} for s in slugs}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    have_weak = sum(1 for s in slugs if out[s]["weak"])
    have_strong = sum(1 for s in slugs if out[s]["strong"])
    print(f"wrote {OUT.relative_to(ROOT)} — {have_weak} champs with counters, "
          f"{have_strong} with strong-against")
    # sample
    for nm in ("aatrox", "hecarim", "graves"):
        if nm in out:
            print(f"  {nm}: weak vs {out[nm]['weak'][:5]} | strong vs {out[nm]['strong'][:5]}")


if __name__ == "__main__":
    main()
