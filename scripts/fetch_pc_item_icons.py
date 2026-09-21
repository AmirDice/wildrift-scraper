"""Download PC League item icons for Wild Rift items we have no art for.

Wild Rift's own item art is published with the client, and wr-meta (where the
rest of our icons come from) only picks it up days after a patch. The ten items
7.3 adds all exist in PC League, which serves its icons from Data Dragon, so
the shop art matches even if the frame does not. This is the owner's call: PC
art now beats an empty square for a week.

Each entry below is a Data Dragon item id, verified by name against
`cdn/<version>/data/en_US/item.json` before anything is written -- an id that
silently points at another item would put the wrong picture on the page.

Run:
    python -m scripts.fetch_pc_item_icons             # report only
    python -m scripts.fetch_pc_item_icons --write
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
ICONS = ROOT / "web-next" / "public" / "items"
VERSIONS = "https://ddragon.leagueoflegends.com/api/versions.json"

#: our slug -> (Data Dragon item id, the name it must have there, and a pinned
#: version for an item PC has since removed from its own shop).
PC_ITEMS = {
    "hexoptics-c44": ("2523", "Hexoptics C44"),
    "yun-tal-wildarrows": ("3032", "Yun Tal Wildarrows"),
    # PC retired Stormrazor, so its art only exists in older versions. Wild
    # Rift brought the item back in 7.3, which is why we still want it.
    "stormrazor": ("3097", "Stormrazor", "16.11.1"),
    "rapid-firecannon": ("3094", "Rapid Firecannon"),
    "fiendhunter-bolts": ("2512", "Fiendhunter Bolts"),
    "immortal-shieldbow": ("6673", "Immortal Shieldbow"),
    "statikk-shiv": ("3087", "Statikk Shiv"),
    "whispering-circlet": ("322526", "Whispering Circlet"),
    "diadem-of-songs": ("322530", "Diadem of Songs"),
    "echoes-of-helia": ("6620", "Echoes of Helia"),
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--version", help="Data Dragon version (default: the newest)")
    args = ap.parse_args()

    default_version = args.version or requests.get(VERSIONS, timeout=30).json()[0]
    catalogues: dict[str, dict] = {}

    def catalogue_for(v: str) -> dict:
        if v not in catalogues:
            catalogues[v] = requests.get(
                f"https://ddragon.leagueoflegends.com/cdn/{v}/data/en_US/item.json", timeout=60
            ).json()["data"]
        return catalogues[v]

    print(f"Data Dragon {default_version}")

    wrote = 0
    for slug, spec in PC_ITEMS.items():
        item_id, expected = spec[0], spec[1]
        version = spec[2] if len(spec) > 2 else default_version
        entry = catalogue_for(version).get(item_id)
        if not entry:
            print(f"  {slug}: id {item_id} is not in Data Dragon {version}")
            continue
        if entry["name"] != expected:
            print(f'  {slug}: id {item_id} is "{entry["name"]}" in {version}, not "{expected}" -- skipped')
            continue
        url = f'https://ddragon.leagueoflegends.com/cdn/{version}/img/item/{entry["image"]["full"]}'
        if not args.write:
            print(f"  {slug}: would fetch {url}")
            continue
        blob = requests.get(url, timeout=60).content
        (ICONS / f"{slug}.png").write_bytes(blob)
        print(f"  {slug}: {len(blob) // 1024}KB from {entry['image']['full']}")
        wrote += 1

    if not args.write:
        print("\ndry run: pass --write to download")
    else:
        print(f"\n{wrote} icons into {ICONS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
