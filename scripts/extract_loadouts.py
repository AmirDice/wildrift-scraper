"""Offline extractor for loadout captures.

Reads a capture directory written by scripts/scrape_loadouts.py and pulls the
numbers out of every row: rank, win rate, pick rate, plus one crop per icon.

WHAT IT RESOLVES: the numbers on all five tabs, the partner champion names
(CN -> English, bridged through the cnName field already in
data/cn_winrates.json, so no network call and no new map), and -- since the
owner named the panel's art on 2026-10-12 -- which item each equip and boots
icon is and which rune each rune icon is.

Items and runes are matched against the LOADOUT banks, not the banks the CN
leaderboard extraction uses. Same icons, differently drawn: the panel renders
them smaller, on its own backgrounds, and the catalogue art alone managed 17
of 33. See scripts/build_loadout_bank.py.

STILL UNRESOLVED: the skills tab. Those are champion abilities, which have no
bank. Every icon is still written to disk beside its row either way, so a
later pass never needs the frames re-captured.

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

from src import icon_match
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


#: Which bank names each tab's icons. The skills tab is absent on purpose:
#: those are champion abilities and no bank holds them.
_ICON_BANK = {"equip": "loadout_items", "boots": "loadout_items",
              "runes": "loadout_runes"}


def _identify(icon: np.ndarray, tab: str, slot: int) -> dict:
    """{"name", "score"} for one icon, or {} where nothing can name it."""
    kind = _ICON_BANK.get(tab)
    if kind is None:
        return {}
    # The game only ever puts a KEYSTONE in the first rune slot, and art
    # alone cannot separate Lethal Tempo from Empowered Attack -- both are
    # an arrow on a dark ground. The rule can. This is also the independent
    # check on the bank: a keystone slot that comes back a minor rune is a
    # matcher error the score would not have flagged.
    only = icon_match.keystones() if (tab == "runes" and slot == 0) else None
    name, score, _gap, _runner = icon_match.match_slot(icon, kind, only)
    return {"name": name, "score": round(score, 3)}


def extract_tab(frame_paths: list[Path], tab: str, icon_dir: Path,
                cn_map: dict[str, str], engine: str = "paddle") -> dict:
    spec = L.TABS[tab]
    rows_out: dict[int, dict] = {}
    tab_review: list[str] = []
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

        rows = L.find_rows(image)
        # Icon geometry is a property of the FRAME, not of the row: measured
        # once over every row at once, because a near-black rune leaves a
        # column its own row cannot distinguish from the panel. None means
        # the frame did not yield the column count this tab has -- the
        # no-data illustration, most often -- and cutting it anyway would
        # write a row of nonsense that nothing downstream could spot.
        geom = L.measure_icons(image, rows, spec["icons"]) if rows else None
        if rows and geom is None:
            tab_review.append(f"{frame_path.name}: no icon grid "
                              f"({spec['icons']} columns expected); "
                              f"numbers kept, icons skipped")
        found = [L.row_cells(image, r) for r in rows]
        offset = _frame_offset([_read_rank(c["rank"]) for c in found])
        for i, cells in enumerate(found):
            rank = offset + i
            # Dedupe across scroll frames -- but a rank already held by a
            # row with NO icons does not count as done. The app renders the
            # table before the artwork, so a tab captured a moment early has
            # a first frame with every number and no icons; first-wins there
            # claims all eleven ranks and the later frames that do have the
            # icons are skipped as duplicates. Braum lost his whole equip
            # tab to this: 21 rows of win rates and not one item.
            held = rows_out.get(rank)
            if held is not None and (held["entities"] or not geom):
                continue
            icons = L.segment_icons(image, rows[i], geom) if geom else []
            entities = []
            for j, icon in enumerate(icons):
                if icon is None:
                    entities.append({"icon": None})
                    continue
                name = f"{tab}_r{rank:02d}_i{j}.png"
                cv2.imwrite(str(icon_dir / name), icon)
                entities.append({"icon": name, **_identify(icon, tab, j)})
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
    review = list(tab_review)
    review += [f"rank {r['rank']}: {k} unreadable"
               for r in rows for k in ("winRate", "pickRate") if r[k] is None]
    unknown = sum(1 for r in rows for e in r["entities"]
                  if e.get("name") == "?")
    if unknown:
        review.append(f"{unknown} icons could not be identified")
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


#: Environment that pins a worker to one compute thread. Set in the PARENT
#: before the pool is created, so every spawned child inherits it at import
#: time -- which is the only moment it can take effect, because the native
#: libraries read it when they load.
_SINGLE_THREAD_ENV = {
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
}


def _extract_one(job: tuple[Path, str]) -> tuple[str, int, float, str]:
    """(name, returncode, seconds, captured output) for one capture.

    Output is captured and handed back rather than printed, so four
    workers cannot interleave half-lines into one unreadable log. The
    parent prints each block whole when the capture finishes.
    """
    import contextlib
    import io
    import time as _time

    folder, engine = job
    try:
        cv2.setNumThreads(1)
    except Exception:  # noqa: BLE001 -- older builds without the setter
        pass
    buf = io.StringIO()
    start = _time.time()
    try:
        with contextlib.redirect_stdout(buf):
            rc = extract_dir(folder, None, engine)
    except Exception as exc:  # noqa: BLE001 -- one bad capture must not end the run
        return folder.name, 1, _time.time() - start, f"{type(exc).__name__}: {exc}"
    return folder.name, rc, _time.time() - start, buf.getvalue()


def _run_pool(todo: list[Path], engine: str, workers: int) -> int:
    """Extract `todo` across `workers` processes. Returns the failure count."""
    import concurrent.futures
    import os
    import time as _time

    os.environ.update(_SINGLE_THREAD_ENV)
    done = bad = 0
    started = _time.time()
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_extract_one, (d, engine)): d for d in todo}
        for future in concurrent.futures.as_completed(futures):
            name, rc, secs, output = future.result()
            done += 1
            bad += rc != 0
            rate = (_time.time() - started) / done
            left = rate * (len(todo) - done)
            print("")
            print(f"[{done}/{len(todo)}] {name}  {secs:.0f}s"
                  f"{'' if rc == 0 else '  FAILED'}"
                  f"   ~{left / 60:.0f} min left")
            if output.strip():
                print(output.rstrip())
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("capture_dir", type=Path,
                    help="one capture directory, or a parent holding many "
                         "(every child with a manifest.json is extracted)")
    ap.add_argument("--no-skip", action="store_true",
                    help="extract the captures _recapture.json holds back "
                         "too. Those lost a whole tab to a frame grabbed "
                         "before the app drew its artwork, so the rows come "
                         "out looking complete with no icons in them")
    ap.add_argument("--force", action="store_true",
                    help="re-extract directories that already have a "
                         "loadouts.json; by default they are skipped, so a "
                         "long batch resumes where it stopped")
    ap.add_argument("--out", type=Path, default=None,
                    help="defaults to loadouts.json inside the capture dir")
    ap.add_argument("--engine", choices=("paddle", "tesseract"), default="paddle",
                    help="paddle (default) is more accurate AND faster here; "
                         "tesseract is the psm-8 fast path at ~90%% on numbers")
    ap.add_argument("--workers", type=int, default=1,
                    help="captures to extract at once when given a parent "
                         "directory. DEFAULT 1, because parallel measured "
                         "SLOWER on this machine: three workers took 709.7s "
                         "on the same three captures that ran 636.4s one "
                         "after another, a 0.90x speedup. Raise it only "
                         "against a measurement on an idle machine. 0 picks "
                         "one worker per core, leaving one free.")
    args = ap.parse_args()

    if (args.capture_dir / "manifest.json").exists():
        return extract_dir(args.capture_dir, args.out, args.engine)

    # A parent directory: extract every capture under it.
    dirs = sorted(d for d in args.capture_dir.iterdir()
                  if d.is_dir() and (d / "manifest.json").exists())
    if not dirs:
        print(f"no captures found under {args.capture_dir}", file=sys.stderr)
        return 2

    # Captures whose artwork had not rendered when the frame was taken.
    # Held back by NAME rather than by deleting anything: a re-capture
    # writes a new timestamped directory, which is not in the list, so it
    # is picked up without anyone having to edit the file.
    held: dict[str, list[str]] = {}
    skip_file = args.capture_dir / "_recapture.json"
    if skip_file.exists() and not args.no_skip:
        try:
            held = json.loads(skip_file.read_text(encoding="utf-8"))["skip"]
        except Exception as exc:                            # noqa: BLE001
            print(f"ignoring {skip_file.name}: {exc}", file=sys.stderr)
    dirs2 = [d for d in dirs if d.name not in held]
    if held:
        tabs = sorted({t for v in held.values() for t in v})
        print(f"holding back {len(dirs) - len(dirs2)} captures listed in "
              f"{skip_file.name} ({', '.join(tabs)} lost to a half-drawn "
              f"frame); --no-skip extracts them anyway")
    dirs = dirs2

    todo = [d for d in dirs if args.force or not (d / "loadouts.json").exists()]
    print(f"{len(dirs)} captures, {len(dirs) - len(todo)} already extracted, "
          f"{len(todo)} to do")
    if not todo:
        return 0
    workers = args.workers or max(1, (os.cpu_count() or 2) - 1)
    workers = min(workers, len(todo))
    if workers > 1:
        print(f"{workers} at a time")
        return 1 if _run_pool(todo, args.engine, workers) else 0

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
