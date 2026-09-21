"""Download PC League rune art for a Wild Rift rune we have no icon for.

Same reasoning as scripts/fetch_pc_item_icons.py: Riot publishes Wild Rift's
rune art with the client, wr-meta picks it up days after a patch, and 7.3's
Legend: Haste would otherwise be an empty square in the rune picker. PC League
has the same rune, so its art is used until the real one exists.

Run:
    python -m scripts.fetch_pc_rune_icons             # report only
    python -m scripts.fetch_pc_rune_icons --write
"""
from __future__ import annotations

import argparse
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
ICONS = ROOT / "web-next" / "public" / "items"
BASE = "https://ddragon.leagueoflegends.com/cdn/img/perk-images/Styles"

#: our slug -> the path under perk-images/Styles
PC_RUNES = {
    "legend-haste": "Precision/LegendHaste/LegendHaste.png",
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    for slug, path in PC_RUNES.items():
        url = f"{BASE}/{path}"
        if not args.write:
            print(f"  {slug}: would fetch {url}")
            continue
        response = requests.get(url, timeout=60)
        if response.status_code != 200:
            print(f"  {slug}: {url} returned {response.status_code}")
            return 1
        (ICONS / f"{slug}.png").write_bytes(response.content)
        print(f"  {slug}: {len(response.content) // 1024}KB")
    if not args.write:
        print("\ndry run: pass --write to download")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
