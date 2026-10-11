"""Offline extractor for loadout captures.

Reads a capture directory written by scripts/scrape_loadouts.py and pulls the
numbers out of every row: rank, win rate, pick rate, plus one crop per icon.

WHAT IT RESOLVES TODAY: the numbers on all five tabs, and the partner
champion names (CN -> English, bridged through the cnName field already in
data/cn_winrates.json, so no network call and no new map).

WHAT IT DOES NOT RESOLVE YET: which item each equip/boots icon is, and which
rune or ability each rune/skill icon is. Those need an icon bank built at the
device's real resolution, and guessing at crops before seeing a real capture
is how you calibrate against the wrong thing. So every icon is written to
disk next to its row and the CN label is OCR'd where the panel shows one;
identification is a second pass over frames that never need re-capturing.

Run:
    python -m scripts.extract_loadouts data/captures_loadouts/milio_20261008_1252
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Set BEFORE importing src.ocr, which reads this at import time.
#
# The default is "en,korean", which is right for a leaderboard carrying player
# names in three scripts. Here it is pure cost: this panel is digits and
# Chinese, "en" reads both at ~1.0 (see the PADDLE_LANGS note in src/ocr.py),
# and "korean" returns EMPTY on Chinese so it never wins. Dropping it saves
# loading a second model at start-up, and saves a second inference pass on
# every crop where the first engine scores under PADDLE_GOOD_SCORE.
os.environ.setdefault("PADDLE_LANGS", "en")

from src import loadouts as L
from src import ocr as ocr_module

ROOT = Path(__file__).resolve().parent.parent
CN_WINRATES = ROOT / "data" / "cn_winrates.json"

#: Digits and a decimal point only: the win/pick columns are "NN.NN%" and
#: nothing else, so constraining the alphabet removes the usual %->5, .->, slips.
#:
#: PSM 8 ("single word"), NOT 7 ("single line"). Measured on the partners tab,
#: whose win rates nearly all begin with 5, psm 7 scored 0/11 and psm 8 scored
#: 11/11: psm 7 was mangling the LEADING digit (58.82 -> 8.82, 56.00 -> 96.00,
#: 55.84 -> 99.84). Across all five tabs that is 66.1% -> 90.3%. Scale made no
#: difference at all, and neither did feeding it native-resolution pixels, so
#: do not go looking for this in the preprocessing.
_NUM_CONFIG = "--oem 3 --psm 8 -c tessedit_char_whitelist=0123456789.%"
#: PSM 8, not 10. PSM 10 is "single CHARACTER", which cannot read a two-digit
#: rank -- and the first tab reaches at least 29 rows, so ranks 10+ are the
#: common case there, not an edge case. Two ranks colliding on a misread get
#: silently dropped by the dedupe, which is how a 11-row frame came back as 10.
_RANK_CONFIG = "--oem 3 --psm 8 -c tessedit_char_whitelist=0123456789"

#: A win rate or a pick rate is a percentage; anything outside this cannot be
#: real. Two of the six residual Tesseract errors were lost decimal points
#: landing at 147.0 and 172.0, which this catches outright.
_PCT_RANGE = (0.0, 100.0)


def _cn_to_english() -> dict[str, str]:
    """Chinese champion name -> our English name, from data already on disk."""
    if not CN_WINRATES.exists():
        return {}
    data = json.loads(CN_WINRATES.read_text(encoding="utf-8"))
    return {c["cnName"]: c["name"] for c in data.get("champions", []) if c.get("cnName")}


def _tesseract_once(crop: np.ndarray) -> str:
    """One Tesseract pass, not read_text's two.

    read_text tries both Otsu polarities and keeps the better, which is right
    on a mixed board but costs 930ms/crop here against 270ms for a single
    pass. This panel is always light digits on dark grey, so the inverted pass
    never wins and is 3.4x of the cost for nothing. Measured on 10 cells.
    """
    text, _conf = ocr_module._run_tesseract(
        ocr_module.preprocess(crop, scale=5.0), _NUM_CONFIG)
    return text


def _parse_pct(text: str) -> float | None:
    m = re.search(r"\d{1,3}(?:\.\d{1,2})?", (text or "").replace(" ", ""))
    if not m:
        return None
    value = float(m.group(0))
    return value if _PCT_RANGE[0] <= value <= _PCT_RANGE[1] else None


def _read_number(crop: np.ndarray, engine: str) -> float | None:
    """Read one percentage cell.

    Paddle is the default because it is both MORE ACCURATE and FASTER here
    than the Tesseract path: it resolved 6/6 of the cells Tesseract got wrong,
    at 2.2s/crop against 2.7s (read_text runs Tesseract twice, once per
    polarity). Only two of those six were catchable by a range check -- the
    rest, like 2.94 -> 2.98 and 42.42 -> 82.42, read as perfectly plausible
    percentages -- so a fallback that fires only on suspicion would let them
    through silently. Hence Paddle on every cell rather than on demand.
    """
    if crop.size == 0:
        return None
    if engine == "tesseract":
        return _parse_pct(_tesseract_once(crop))
    try:
        text, _score, _words = ocr_module._run_paddle(crop)
    except Exception:
        return _parse_pct(_tesseract_once(crop))
    return _parse_pct(text)


def _read_rank(crop: np.ndarray) -> int | None:
    if crop.size == 0:
        return None
    res = ocr_module.read_text(ocr_module.preprocess(crop, scale=4.0), _RANK_CONFIG)
    m = re.search(r"\d{1,2}", (res.text or ""))
    return int(m.group(0)) if m else None


def _frame_offset(ranks: list[int | None]) -> int:
    """The rank of this frame's FIRST row, by majority vote.

    Ranks inside one frame are consecutive, so every row independently implies
    the same offset (its rank minus its position). That makes a single outlier
    outvoted instead of believed: on Shen's scrolled matchup frame the rank 21
    cell read as "2", which as a per-row value silently reordered the table,
    and as one vote among eleven is simply ignored. It also recovers the scroll
    position, which is the other thing a fixed pitch cannot give us.
    """
    votes = Counter(r - i for i, r in enumerate(ranks) if r is not None)
    return votes.most_common(1)[0][0] if votes else 1


def _read_cn(crop: np.ndarray) -> str:
    """CN text via Paddle. The 'en' model reads Chinese at ~1.0 here (see the
    PADDLE_LANGS note in src/ocr.py), so this needs no extra language."""
    if crop.size == 0:
        return ""
    try:
        text, _score, _words = ocr_module._run_paddle(crop)
    except Exception:
        return ""
    return re.sub(r"\s+", "", text or "")


def extract_tab(frame_paths: list[Path], tab: str, icon_dir: Path,
                cn_map: dict[str, str], engine: str = "paddle") -> dict:
    spec = L.TABS[tab]
    rows_out: dict[int, dict] = {}
    date = None

    for frame_path in frame_paths:
        image = cv2.imread(str(frame_path))
        if image is None:
            continue
        if date is None:
            x, y, w, h = L.band(image, (L.DATE_BOX[0], L.DATE_BOX[2]),
                                (L.DATE_BOX[1], L.DATE_BOX[3]))
            d = _read_cn(image[y:y + h, x:x + w])
            m = re.search(r"(20\d{6})", d)
            date = m.group(1) if m else None

        found = [L.row_cells(image, r) for r in L.find_rows(image)]
        offset = _frame_offset([_read_rank(c["rank"]) for c in found])
        for i, cells in enumerate(found):
            rank = offset + i
            if rank in rows_out:          # dedupe across scroll frames
                continue
            icons = L.segment_icons(cells["entity"], spec["icons"])
            entities = []
            for j, icon in enumerate(icons):
                name = f"{tab}_r{rank:02d}_i{j}.png"
                cv2.imwrite(str(icon_dir / name), icon)
                entities.append({"icon": name})
            # Labels: items name themselves under the icon, partners beside it.
            if spec["labels"]:
                label = _read_cn(cells["entity"])
                if spec["labels"] == "beside":
                    entities = entities or [{"icon": None}]
                    entities[0]["cn"] = label
                    entities[0]["champion"] = cn_map.get(label)
                    if not entities[0]["champion"]:
                        # Names render as "title\nname"; try the tail.
                        for cn, en in cn_map.items():
                            if cn and cn in label:
                                entities[0]["champion"] = en
                                entities[0]["cn"] = cn
                                break
                elif entities:
                    entities[0]["cn"] = label      # joined; split in pass two
            rows_out[rank] = {
                "rank": rank,
                "winRate": _read_number(cells["winrate"], engine),
                "pickRate": _read_number(cells["pickrate"], engine),
                "entities": entities,
            }

    kind = None
    if tab == "versus" and frame_paths:
        first = cv2.imread(str(frame_paths[0]))
        if first is not None:
            kind = L.detect_versus_kind(first, _read_cn)

    rows = [rows_out[k] for k in sorted(rows_out)]
    picks = [r["pickRate"] for r in rows if r["pickRate"] is not None]
    coverage = round(sum(picks), 2) if picks else None

    # Shares of one champion's games cannot add to more than 100. When they
    # do, a cell was misread even though every individual value looked like a
    # legal percentage -- which is exactly the failure a range check misses.
    review = [f"rank {r['rank']}: {k} unreadable"
              for r in rows for k in ("winRate", "pickRate") if r[k] is None]
    if coverage is not None and coverage > 101.0:
        review.append(f"pick rates sum to {coverage}%, which is impossible; "
                      f"at least one cell is misread")
    return {
        "date": date,
        "nRows": len(rows),
        "pickCoverage": coverage,
        "needsReview": review,
        "versusKindRead": kind,
        "rows": rows,
    }


def extract_dir(capture_dir: Path, out: Path | None, engine: str) -> int:
    man_path = capture_dir / "manifest.json"
    if not man_path.exists():
        print(f"no manifest.json in {capture_dir}", file=sys.stderr)
        return 2
    manifest = json.loads(man_path.read_text(encoding="utf-8"))

    icon_dir = capture_dir / "icons"
    icon_dir.mkdir(exist_ok=True)
    cn_map = _cn_to_english()

    result = {
        "champion": manifest.get("champion"),
        "capturedAt": manifest.get("capturedAt"),
        "source": "cn-companion-app",
        # Provenance travels with the numbers. Without it a row is just a
        # percentage that cannot be placed against anything else we hold.
        "bracket": manifest.get("bracket"),
        "mode": manifest.get("mode"),
        "lane": manifest.get("lane"),
        "versusKind": manifest.get("versusKind"),
        "tabs": {},
    }
    for tab, info in manifest.get("tabs", {}).items():
        if tab not in L.TABS:
            print(f"  {tab:9s} unknown tab, skipped")
            continue
        paths = [capture_dir / f for f in info["frames"]]
        res = extract_tab(paths, tab, icon_dir, cn_map, engine)
        # Capture derived this from the lane without OCR; this is the check.
        read = res.get("versusKindRead")
        if read and read != result.get("versusKind"):
            res["needsReview"].append(
                f"first tab reads {read}, but the lane implied "
                f"{result.get('versusKind')}; the lane filter may not have "
                f"taken on this champion")
        result["tabs"][tab] = res
        cov = f"{res['pickCoverage']:.1f}%" if res["pickCoverage"] is not None else "n/a"
        flag = f"  ! {len(res['needsReview'])} to review" if res["needsReview"] else ""
        print(f"  {tab:9s} {res['nRows']:2d} rows  date={res['date']}  "
              f"pick coverage {cov}{flag}")

    dest = out or (capture_dir / "loadouts.json")
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {dest}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("capture_dir", type=Path,
                    help="one capture directory, or a parent holding many "
                         "(every child with a manifest.json is extracted)")
    ap.add_argument("--force", action="store_true",
                    help="re-extract directories that already have a "
                         "loadouts.json; by default they are skipped, so a "
                         "long batch resumes where it stopped")
    ap.add_argument("--out", type=Path, default=None,
                    help="defaults to loadouts.json inside the capture dir")
    ap.add_argument("--engine", choices=("paddle", "tesseract"), default="paddle",
                    help="paddle (default) is more accurate AND faster here; "
                         "tesseract is the psm-8 fast path at ~90%% on numbers")
    args = ap.parse_args()

    if (args.capture_dir / "manifest.json").exists():
        return extract_dir(args.capture_dir, args.out, args.engine)

    # A parent directory: extract every capture under it.
    dirs = sorted(d for d in args.capture_dir.iterdir()
                  if d.is_dir() and (d / "manifest.json").exists())
    if not dirs:
        print(f"no captures found under {args.capture_dir}", file=sys.stderr)
        return 2
    todo = [d for d in dirs if args.force or not (d / "loadouts.json").exists()]
    print(f"{len(dirs)} captures, {len(dirs) - len(todo)} already extracted, "
          f"{len(todo)} to do")
    bad = 0
    for i, d in enumerate(todo, start=1):
        print("")
        print(f"[{i}/{len(todo)}] {d.name}")
        try:
            bad += extract_dir(d, None, args.engine) != 0
        except Exception as exc:          # one bad capture must not end a batch
            print(f"  ! failed: {exc}")
            bad += 1
    print("")
    print(f"batch done: {len(todo) - bad} ok, {bad} failed")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
