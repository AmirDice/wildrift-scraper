"""Publish the newest best-partner capture of each queue for the website.

Reads the newest partners.json PER BRACKET of any partners run, current or
archived (data/captures/partners/<date>/, data/archive/partners/<date>/;
scripts/walk_partners) and writes web-next/src/data/cn_partners.json: per
queue, every pair once, with both champions' slugs and lanes, its win rate and
appearance rate. The site builds its views from that
(web-next/src/lib/cn-partners.ts).

The app's rank filter is how the queue is chosen on the page, and the owner
names them by queue: the "legendary" capture is SOLO QUEUE, the "challenger"
capture is PREMADE (2026-10-26).

Run from the repository root after a capture:

    python scripts/export_partners_for_web.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "web-next" / "src" / "data" / "cn_partners.json"
SITE = ROOT / "web-next" / "src" / "data" / "site.json"
LANE_ORDER = ["baron", "jungle", "mid", "dragon", "support"]
#: bracket recorded by walk_partners --bracket -> (queue id, label), in site order.
QUEUES = {"legendary": ("solo", "Solo queue"), "challenger": ("premade", "Premade")}


def stamp_of(path: Path) -> str:
    """The capture's own folder stamp (YYYYMMDD_HHMM), so captures of different
    brackets order by time and not by bracket name."""
    m = re.search(r"(\d{8}_\d{4})", path.parent.name)
    return m.group(1) if m else ""


def build_pairs(data: dict, slugs: dict) -> tuple[list[dict], int, set]:
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
            # One orientation per lane pairing (Baron before Mid, Dragon before
            # Support), whichever champion the app printed first.
            if LANE_ORDER.index(a_lane) > LANE_ORDER.index(b_lane):
                a, a_lane, b, b_lane = b, b_lane, a, a_lane
            pairs.append({"a": a, "aLane": a_lane, "b": b, "bLane": b_lane,
                          "winRate": row["winRate"], "pickRate": row["pickRate"]})
    return pairs, off_list, unknown


def main() -> int:
    from src.capture_runs import all_runs
    captures = [p for run in all_runs("partners") for p in run.glob("partners_*/partners.json")]
    if not captures:
        print("no partners capture under data/captures/partners or data/archive/partners; "
              "run scripts.walk_partners first")
        return 1
    newest: dict[str, tuple[Path, dict]] = {}
    for path in sorted(captures, key=stamp_of):
        data = json.loads(path.read_text(encoding="utf-8"))
        bracket = data.get("bracket")
        if bracket in QUEUES:
            newest[bracket] = (path, data)
        else:
            print(f"skipped {path.parent.name}: bracket {bracket!r} is not a known queue")
    slugs = {c["name"]: c["slug"] for c in json.loads(SITE.read_text(encoding="utf-8"))["champions"]}

    queues = []
    for bracket, (qid, label) in QUEUES.items():
        if bracket not in newest:
            continue
        source, data = newest[bracket]
        pairs, off_list, unknown = build_pairs(data, slugs)
        queues.append({
            "id": qid,
            "label": label,
            "bracket": bracket,
            "capturedAt": data.get("capturedAt"),
            "lanePairs": sorted({f"{p['aLane']}+{p['bLane']}" for p in pairs}),
            "pairs": pairs,
        })
        print(f"{label}: {len(pairs)} pairs from {source.parent.name}")
        if off_list:
            print(f"  {off_list} pairs were listed under another lane pairing; filed under their own lanes")
        if unknown:
            print("  names not on our roster:", ", ".join(sorted(unknown)))
    out = {"source": "CN companion app, 最佳拍档", "queues": queues}
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
