"""Publish the newest best-partner capture for the website.

Reads the newest data/captures_partners/*/partners.json (scripts/walk_partners)
and writes web-next/src/data/cn_partners.json: every pair once, with both
champions' slugs and lanes, its win rate and appearance rate. The site
builds the per-champion view from that (web-next/src/lib/cn-partners.ts).

Run from the repository root after a capture:

    python scripts/export_partners_for_web.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAPTURES = ROOT / "data" / "captures_partners"
OUT = ROOT / "web-next" / "src" / "data" / "cn_partners.json"
SITE = ROOT / "web-next" / "src" / "data" / "site.json"


def main() -> int:
    captures = sorted(CAPTURES.glob("partners_*/partners.json"))
    if not captures:
        print(f"no capture under {CAPTURES.relative_to(ROOT)}; run scripts.walk_partners first")
        return 1
    source = captures[-1]
    data = json.loads(source.read_text(encoding="utf-8"))
    slugs = {c["name"]: c["slug"] for c in json.loads(SITE.read_text(encoding="utf-8"))["champions"]}

    pairs, seen, unknown = [], set(), set()
    off_list = 0
    for lst in data.get("lists", []):
        for row in lst.get("rows", []):
            # A pair is filed under the lanes printed under its names, not the
            # list it was found in. The app shows the odd pair under another
            # chip (Baron + Mid held four Baron + Support duos, Yasuo 上路 with
            # Malphite 辅助, none of them in the Baron + Support list itself).
            # They are real teammates with real results, so they are kept.
            lanes = {row.get("aLane"), row.get("bLane")}
            if None not in lanes and lanes != {lst.get("lane"), lst.get("partnerLane")}:
                off_list += 1
            a, b = slugs.get(row.get("a")), slugs.get(row.get("b"))
            if not a or not b:
                unknown.update(name for name, slug in ((row.get("a"), a), (row.get("b"), b)) if not slug)
                continue
            # The list's own lanes back up a label that failed to read.
            a_lane = row.get("aLane") or lst.get("lane")
            b_lane = row.get("bLane") or lst.get("partnerLane")
            key = tuple(sorted([(a, a_lane), (b, b_lane)]))
            if key in seen:
                continue
            seen.add(key)
            pairs.append({"a": a, "aLane": a_lane, "b": b, "bLane": b_lane,
                          "winRate": row["winRate"], "pickRate": row["pickRate"]})
    stamp = re.search(r"(\d{8})_(\d{4})", source.parent.name)
    out = {
        "capturedAt": data.get("capturedAt"),
        "bracket": data.get("bracket"),
        "source": "CN companion app, 最佳拍档",
        "lanePairs": sorted({f"{p['aLane']}+{p['bLane']}" for p in pairs}),
        "pairs": pairs,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(pairs)} pairs from {source.parent.name}"
          f"{' (' + stamp.group(1) + ')' if stamp else ''}")
    if off_list:
        print(f"{off_list} pairs were listed under another lane pairing; filed under their own lanes")
    if unknown:
        print("names not on our roster:", ", ".join(sorted(unknown)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
