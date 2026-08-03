"""Map rune names to their local art, and report names the extractor invented.

The catalogue (data/wrmeta_runes.json) is ground truth: 53 runes that exist,
all with art already in web-next/public/items. Nothing is downloaded here --
an earlier version fetched art for 17 "missing" runes before the owner
confirmed none of them are in the game. A captured name with no catalogue
entry is an extraction bug, so this script reports it instead of dressing it
up (see web/runes.py).

Writes web-next/src/data/rune_icons.json, keyed by canonical rune name,
which is what the site renders.

    python -m scripts.export_rune_icons            # write the map + report
    python -m scripts.export_rune_icons --report   # report only
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from web.runes import art_slug, canonical_rune, is_known_rune  # noqa: E402

OUT = ROOT / "web-next" / "src" / "data" / "rune_icons.json"
ITEMS_DIR = ROOT / "web-next" / "public" / "items"
REPORT = ROOT / "data" / "rune_extraction_report.txt"


def observed() -> Counter:
    """Rune names the scraper has captured, canonicalised, by frequency."""
    seen: Counter = Counter()
    for path in glob.glob(str(ROOT / "data" / "captures" / "*" / "builds.jsonl")):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                for n in (json.loads(line).get("runes") or []):
                    if n and n != "?":
                        seen[canonical_rune(n)] += 1
    return seen


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", action="store_true", help="report only, write nothing")
    args = ap.parse_args()

    stems = {os.path.splitext(f)[0]: f for f in os.listdir(ITEMS_DIR)}
    catalogue = json.loads((ROOT / "data" / "wrmeta_runes.json").read_text(encoding="utf-8"))

    icons: dict[str, str] = {}
    no_art: list[str] = []
    for rune in catalogue:
        name = rune["name"]
        stem = art_slug(name)
        if stem in stems:
            icons[name] = f"/items/{stems[stem]}"
        else:
            no_art.append(name)

    seen = observed()
    known = {n: c for n, c in seen.items() if is_known_rune(n)}
    unknown = {n: c for n, c in seen.items() if not is_known_rune(n)}
    total = sum(seen.values())
    good = sum(known.values())

    lines = [
        f"rune catalogue: {len(catalogue)} runes, {len(icons)} with local art"
        + (f", MISSING ART: {', '.join(no_art)}" if no_art else ""),
        "",
        f"captured rune slots: {total}",
        f"  resolve to a real rune : {good} ({good / total * 100:.1f}%)" if total else "",
        f"  extractor invented     : {total - good} ({(total - good) / total * 100:.1f}%)" if total else "",
        "",
        "NAMES THE EXTRACTOR INVENTED (not runes in Wild Rift; each is a misread",
        "of whatever was actually on the build popup):",
    ]
    for n, c in sorted(unknown.items(), key=lambda kv: -kv[1]):
        lines.append(f"  {c:5d}  {n}")
    text = "\n".join(x for x in lines if x != "" or True)

    print(text if args.report else "\n".join(lines[:6]))
    if args.report:
        return 0

    OUT.write_text(json.dumps(icons, ensure_ascii=False, indent=1, sort_keys=True),
                   encoding="utf-8")
    REPORT.write_text(text, encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(ROOT)} ({len(icons)} runes)")
    print(f"wrote {REPORT.relative_to(ROOT)} ({len(unknown)} invented names)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
