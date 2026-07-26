"""Export champions that exist in the game but not yet in our win-rate dataset.

A newly released champion has no top-50 leaderboard yet, so `site.json` (built
from the ranked-player scrape) simply does not contain them, and they vanish
from the site entirely -- which reads as "this site is out of date" even though
the data is correct.

This script bridges the gap. For every champion present in the roster but absent
from site.json it writes what wildriftfire *does* know: recommended role, their
tier rating, base stats and the full ability list. The frontend renders these as
"stats pending" cards rather than mixing them into rankings they cannot honestly
be ranked in.

Inputs:
    data/champions_wr.json        (scripts/scrape_champions.py)
    data/wrf_cache/guide_*.html   (raw guide pages, same scrape)
    web-next/src/data/site.json   (the ranked dataset)

Output:
    web-next/src/data/new_champions.json

Run:
    python -m scripts.export_new_champions
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from web.champion_assets import icon_url, splash_url
from web.champion_meta import champion_class, champion_difficulty, difficulty_label
from web.champion_roles import primary_role

ROOT = Path(__file__).resolve().parent.parent
CHAMPS = ROOT / "data" / "champions_wr.json"
CACHE = ROOT / "data" / "wrf_cache"
SITE = ROOT / "web-next" / "src" / "data" / "site.json"
OUT = ROOT / "web-next" / "src" / "data" / "new_champions.json"

# wildriftfire writes the recommended role and its own tier grade into the guide
# header: "... Recommended Role <role> Tier <grade> ...".
ROLE_PATTERN = re.compile(r"Recommended Role\s+([A-Za-z ]+?)\s+Tier\s+([A-Z]{1,3}|TBD)\b")

# wildriftfire's lane names -> ours.
LANE_MAP = {
    "Duo Lane": "Dragon",
    "Bot Lane": "Dragon",
    "Dragon Lane": "Dragon",
    "Baron Lane": "Baron",
    "Solo Lane": "Baron",
    "Mid Lane": "Mid",
    "Jungle": "Jungle",
    "Support": "Support",
}


def _plain_text(html: str) -> str:
    stripped = re.sub(r"<(script|style)[\s\S]*?</\1>", " ", html)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", stripped))


def _guide_meta(slug: str) -> dict:
    """Recommended role + tier grade from the cached guide page."""
    page = CACHE / f"guide_{slug}.html"
    if not page.exists():
        return {}
    match = ROLE_PATTERN.search(_plain_text(page.read_text(encoding="utf-8")))
    if not match:
        return {}
    lane, tier = match.group(1).strip(), match.group(2).strip()
    # A guide published before the champion goes live carries "TBD" for both;
    # treat that as unknown rather than as a role called TBD.
    if lane == "TBD":
        return {"guideTier": None if tier == "TBD" else tier}
    return {
        "guideRole": LANE_MAP.get(lane, lane),
        "guideLane": lane,
        "guideTier": None if tier == "TBD" else tier,
    }


def main() -> None:
    champions = json.loads(CHAMPS.read_text(encoding="utf-8"))
    ranked = {c["name"] for c in json.loads(SITE.read_text(encoding="utf-8"))["champions"]}

    pending = []
    for champion in champions:
        name = champion["name"]
        if name in ranked:
            continue
        guide = _guide_meta(champion["slug"])
        difficulty = champion_difficulty(name)
        pending.append({
            "name": name,
            "slug": champion["slug"],
            "role": guide.get("guideRole") or primary_role(name),
            "class": champion_class(name),
            "difficulty": difficulty,
            "difficultyLabel": difficulty_label(difficulty),
            "icon": icon_url(name),
            "splash": splash_url(name),
            "primaryDamage": champion.get("primaryDamage"),
            "scalesWith": champion.get("scalesWith", []),
            "mechanics": champion.get("mechanics", []),
            "baseStats": champion.get("baseStats", {}),
            "abilities": [
                {
                    "slot": ability["slot"],
                    "name": ability["name"],
                    "text": ability["text"],
                    "cooldowns": ability.get("cooldowns", []),
                }
                for ability in champion.get("abilities", [])
            ],
            "guideTier": guide.get("guideTier"),
            "guideLane": guide.get("guideLane"),
            "guideUrl": f"https://www.wildriftfire.com/guide/{champion['slug']}",
        })

    pending.sort(key=lambda c: c["name"])
    OUT.write_text(
        json.dumps(
            {
                "source": "wildriftfire.com",
                "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "note": "Champions live in Wild Rift but not yet present in our ranked-player dataset.",
                "champions": pending,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"wrote {OUT.relative_to(ROOT)} ({len(pending)} champions: "
          f"{', '.join(c['name'] for c in pending) or 'none'})")


if __name__ == "__main__":
    main()
