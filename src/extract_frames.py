"""Offline extractor for --capture-only sessions.

Reads the manifest a capture session wrote, pulls winrate/score/games out of
each saved strip frame (and player identities out of the profile frames), and
writes a CSV in the same schema as the live scraper. Ranks whose strip frame
does not show the target champion are left blank in the CSV and listed in
needs_manual.txt with their exact frame paths, so the manual pass is a short
worklist instead of a hunt.

Because the frames stay on disk, extraction is re-runnable: fix a prompt or a
parser, run again, nothing needs re-scraping.

Re-runnable is not the same as safe to re-run, though. A batch re-extraction
walked into an API quota wall partway through, and the runs after it read ZERO
win rates and wrote that straight over files holding 43 -- the frames survived,
the extraction did not, and nothing warned. So a run that reads FEWER win rates
than the file already on disk does not replace it; see `--force`.

Run:
    python -m src.extract_frames data/captures/aatrox_20260802_1710
    python -m src.extract_frames data/captures/aatrox_20260802_1710 --engine auto
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np

from . import champions as champ_module
from .config import (
    player_name_region,
    LEADERBOARD_LAYOUT,
    LEGACY_BADGE_X_RANGE,
    SCREEN_2_BADGE_X_RANGE,
    SCREEN_2_NAME_HEIGHT,
    SCREEN_2_NAME_X_RANGE,
    SCREEN_2_NAME_Y_OFFSET,
    SCREEN_5_OCR_REGION,
    load_calibration,
)
from .stats_ocr import read_stats_page_ocr, stats_confidence

#: Below this share of readable fields, a stats page is worth a model
#: call. 40 unseen frames read at 0.986 mean confidence, worst 0.88.
STATS_OCR_MIN_CONFIDENCE = 0.85

from .ocr import (
    GENERAL_TESSERACT_CONFIG,
    find_champion_winrates,
    find_target_data,
    locate_badge_column,
    read_player_name,
    read_text,
    scan_visible_ranks,
)
from .storage import CSVWriter, LeaderboardRow
from .tiers import canonical_tier, resolve_tier
from .profile_rank import read_profile_ranks


def _load_manifest(capture_dir: Path) -> list[dict]:
    """Last entry per rank wins (a retried rank overwrote its frames too)."""
    path = capture_dir / "manifest.jsonl"
    if not path.exists():
        raise SystemExit(f"error: no manifest.jsonl in {capture_dir}")
    by_rank: dict[int, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            by_rank[int(entry["rank"])] = entry
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
    return [by_rank[r] for r in sorted(by_rank)]


def _winrate_count(csv_path: Path) -> int:
    """How many rows in an existing extraction actually carry a win rate.

    The count, not the row count: a credit-starved run still writes 50 rows,
    every one of them blank. That is the difference between an extraction that
    exists and one that worked.
    """
    if not csv_path.exists():
        return 0
    import csv as _csv
    try:
        with csv_path.open(encoding="utf-8", newline="") as fh:
            return sum(1 for row in _csv.DictReader(fh) if (row.get("winrate") or "").strip())
    except (OSError, UnicodeDecodeError):
        # An unreadable file is not evidence of good data worth protecting.
        return 0


def _norm_name(s: str) -> str:
    return "".join(ch for ch in s.casefold() if ch.isalnum())


def _usable_ocr_name(s: str, strict_ascii: bool = True) -> bool:
    """Whether a SINGLE, uncorroborated name read is worth believing, so the
    model is only paid for the ones it is not.

    Two failure shapes to reject. Tesseract garbles CJK entirely, which shows
    up as a low ASCII share. And it emits whitespace fragments on a bad crop
    ("oe eee iar immm Ae") that are mostly-ASCII and would sail past an ASCII
    filter alone, so a usable read must also contain a real four-character
    word. Same test the tap verification already applies further down.

    The ASCII rule is a proxy for "this backend cannot read that script", not
    a claim that non-Latin names are invalid. PaddleOCR with a matching
    language reads them cleanly, so a read that a SECOND crop independently
    agrees with bypasses this entirely -- see the caller.
    """
    s = (s or "").strip()
    if len(s) < 3:
        return False
    if s.count(" ") / len(s) > 0.3:
        return False
    if not strict_ascii:
        # The engine that produced this can read the script, so the two tests
        # below -- both proxies for "Tesseract cannot" -- would only reject a
        # correct answer.
        return True
    ascii_share = sum(c.isascii() for c in s) / len(s)
    if ascii_share < 0.7:
        return False
    return bool(re.search(r"[A-Za-z0-9]{4}", s))


# Fixed identity labels on the 2340x1080 main-profile/build layouts.  The
# coordinates are scaled to the captured frame, so the same crops work on a
# resized device screenshot.  Profile is authoritative: unlike the build card
# it preserves the player's capitalization and also prints the Riot tag.
_REFERENCE_FRAME = (2340, 1080)
# Measured by ink projection over 30 captured profiles: the panel's three text
# rows sit at y 36-60 (the "PROFILE" heading), y 140-162 (the name) and the
# tag below that. The name box used to be (175, 100, 535, 158), which was
# wrong on both axes and cost most of the reads:
#
#   VERTICALLY it started 40px above the text and ended at 158, clipping the
#   bottom ~17% of every glyph. Tesseract was reading the top of each letter,
#   which is exactly the confusion set the 2026-10-05 extraction produced:
#   l->i, g->c, y->v, z->7, J->l, B->p, 2->?. "caguamamo" read as
#   "cacuamamo", "Lokij88" as "Loki8s", "Bruno" as "prune".
#
#   HORIZONTALLY it ran to 535, past the panel's gold right border, which
#   OCRs as a trailing "|" or "}". That is the junk on "ColoneliMustang |",
#   "ALGAGoD |" and "LSS TOPerwaRe . r".
#
# Corrected, exact matches against hand-read ground truth go from 9/30 to
# 23/30, and every one of the 7 that still miss is non-ASCII (CJK, or the
# diacritics in "Därtâñän" and "Rapąń") -- which is what the model fallback
# is for. 465 rather than 470 for the right edge: at 470 the longest name on
# record still caught the border.
_PROFILE_NAME_BOX = (175, 132, 465, 168)
# The tag's row is NOT fixed: it sits at y~171 for most players and y~213 for
# others, so this spans both. Measured 28/30 resolved against 23/30 for the
# single-row box. It stops short of the avatar, so there is nothing else
# carrying a "#" inside it.
_PROFILE_TAG_BOX = (175, 168, 465, 245)
#: The build card's name had the SAME clipping bug, milder: its glyphs run
#: y 814-847 and the box ended at 845, so the bottom 2-3px went missing while
#: 34px of empty card sat inside the top. Corrected, exact matches against
#: ground truth go from 4/30 to 21/30. It is wide enough already; the name is
#: centred and the widest on record spans x 342-842.
_BUILD_NAME_BOX = (330, 808, 850, 852)


def _scaled_region(image: np.ndarray, box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Convert a reference-frame (x0,y0,x1,y1) box to an OCR region."""
    height, width = image.shape[:2]
    ref_w, ref_h = _REFERENCE_FRAME
    x0, y0, x1, y1 = box
    left = max(0, round(x0 * width / ref_w))
    top = max(0, round(y0 * height / ref_h))
    right = min(width, round(x1 * width / ref_w))
    bottom = min(height, round(y1 * height / ref_h))
    return left, top, max(0, right - left), max(0, bottom - top)


#: Which engine reads the profile NAME crop. Split per CROP TYPE rather than
#: globally, because the two jobs have opposite economics. Measured over one
#: champion's 60 name crops:
#:
#:                 accuracy (all)   accuracy (profile)   ms/crop
#:   Tesseract        44/60             23/30              892
#:   PaddleOCR        53/60             27/30             ~3000
#:
#: Paddle on the profile crop ALONE beats the whole corroborated hybrid, and
#: it is one call per rank. The stats strip is the opposite case: numbers, the
#: highest call volume, and Tesseract already reliable, so paying 3x there
#: would take a 144-champion extraction from ~4h to ~17h and make extraction
#: the bottleneck behind a ~5min/champion capture. This costs ~+1.8s a rank.
#:
#: "tesseract" restores the old behaviour for an A/B on one champion.
IDENTITY_ENGINE = os.environ.get("WRTM_IDENTITY_ENGINE", "paddle").strip().lower()


def _read_profile_identity(image: np.ndarray) -> tuple[str | None, str | None]:
    """Read the exact display name and Riot tag from the main profile panel."""
    name = read_player_name(image, _scaled_region(image, _PROFILE_NAME_BOX),
                            prefer=IDENTITY_ENGINE)
    # The TAG stays on Tesseract: it is matched by a `#(\w+)` regex rather
    # than compared as a string, so a character-level improvement buys nothing
    # and would double this crop-type's cost.
    tag_text = read_player_name(image, _scaled_region(image, _PROFILE_TAG_BOX))
    tag = None
    if tag_text:
        match = re.search(r"#\s*([\w-]+)", tag_text, flags=re.UNICODE)
        if match:
            tag = match.group(1).strip()
    return (name.strip() if name else None), tag


def pick_identity(
    profile_name: str | None, build_name: str | None,
    profile_engine: str = "tesseract",
) -> tuple[str | None, str]:
    """Choose a player name from the two crops, or decline.

    Returns (name, source) where source is "profile", "build", "disagree" or
    "none". Kept as a function rather than inlined in main() so the extraction
    harness and the tests exercise the SAME decision -- an evaluation script
    that re-implemented this logic silently measured the old behaviour and
    reported a fix as having done nothing.

    The build card is a second witness for the profile crop. It renders the
    same name in caps, so normalised agreement lets us keep the profile's
    exact capitalization, and disagreement goes to the leaderboard/model
    fallback rather than storing OCR garbage.
    """
    # Two independent witnesses reading the SAME string is stronger evidence
    # than any single-read heuristic, so it overrides the one below. That
    # matters for non-Latin names: _usable_ocr_name rejects a low ASCII share
    # because TESSERACT garbles CJK, but with PaddleOCR configured for the
    # script (see ocr.PADDLE_LANGS) both crops read the Korean names exactly,
    # and the ASCII rule was throwing away two perfect reads that agreed.
    if profile_engine == "paddle":
        # DIFFERENT engines read the two crops, so they are no longer two
        # views of the same question and agreement is not evidence. The build
        # card is on Tesseract, which cannot read Korean at all: asked to
        # arbitrate it returned "LHT- Cj AroH" against Paddle's correct
        # "내가 더 잘해", and because that garbage is ASCII it PASSED the
        # heuristic while the right answer failed it. Corroboration scored
        # 21/30 here against 27/30 for simply trusting the better engine.
        #
        # So the build card demotes to a fallback for when the profile crop
        # yields nothing. That is not a loss: across every disagreement in the
        # captured set the profile was the correct one, including the two the
        # old path escalated (Tintin0201 and Lokij88).
        if profile_name and _usable_ocr_name(profile_name, strict_ascii=False):
            return profile_name, "profile"
        if build_name and _usable_ocr_name(build_name):
            return build_name, "build"
        return None, "none"

    # Both crops on the SAME engine: they really are two witnesses, so
    # agreement is evidence and disagreement is a reason to escalate.
    #
    # Two independent witnesses reading the same string also overrides the
    # single-read heuristic below, which matters for non-Latin names: it
    # rejects a low ASCII share because Tesseract garbles CJK, and that was
    # throwing away two perfect reads that agreed with each other.
    corroborated = bool(
        profile_name and build_name
        and len(_norm_name(profile_name)) >= 2
        and _norm_name(profile_name) == _norm_name(build_name)
    )
    profile_ok = bool(profile_name
                      and (corroborated or _usable_ocr_name(profile_name)))
    build_ok = bool(build_name
                    and (corroborated or _usable_ocr_name(build_name)))
    if profile_ok and (not build_ok
                       or _norm_name(profile_name) == _norm_name(build_name)):
        return profile_name, "profile"
    if build_ok and not profile_ok:
        return build_name, "build"
    if profile_ok and build_ok:
        return None, "disagree"
    return None, "none"


def _read_build_name(image: np.ndarray) -> str | None:
    """Read the large build-card label; fallback only because it uppercases."""
    return read_player_name(image, _scaled_region(image, _BUILD_NAME_BOX))


def verify_taps(
    capture_dir: Path, entries: list[dict],
) -> tuple[dict[int, str], list[str]]:
    """Prove, from the frames on disk, that each manifest rank matches the row
    that was actually tapped.

    The lb_frame is captured milliseconds before the tap, so it is ground
    truth for what was on screen at tap time. Badge-scanning it and checking
    which rank sits at tap_y catches every snap-back that happened between
    the navigation scan and the tap. Returns ({rank: 'ok'|'unknown'|'MISMATCH
    ...'}, human-readable anomaly lines).
    """
    cal = load_calibration()
    badge_x = (
        (int(cal["badge_x0"]), int(cal["badge_x1"]))
        if "badge_x0" in cal and "badge_x1" in cal
        else SCREEN_2_BADGE_X_RANGE
    )
    # Current live calibration must not leak into archived sessions. New
    # captures carry their layout explicitly; old captures can still relocate.
    if entries and all(e.get("leaderboard_layout") == LEADERBOARD_LAYOUT for e in entries):
        badge_x = SCREEN_2_BADGE_X_RANGE
    elif cal.get("leaderboard_layout") == LEADERBOARD_LAYOUT:
        badge_x = LEGACY_BADGE_X_RANGE
    located = False
    status: dict[int, str] = {}
    anomalies: list[str] = []

    # Two passes. The first collects the session's row pitch (a device
    # constant) from whatever frames read cleanly; the second verifies every
    # frame with the same priors the live navigator enjoys -- the expected
    # rank as the chain hint plus the pitch band. Without them, the verifier
    # re-suffers every OCR quirk the scanner was hardened against and files
    # false mismatches on correct taps.
    pitches: list[float] = []
    images: dict[int, np.ndarray] = {}
    for e in entries:
        lb_path = capture_dir / e.get("lb_frame", "")
        if e.get("tap_y") is None or not lb_path.exists():
            continue
        img = cv2.imread(str(lb_path))
        if img is None:
            continue
        images[e["rank"]] = img
        frame_badge_x = tuple(e.get("badge_x_range") or badge_x)
        _r, p = scan_visible_ranks(img, frame_badge_x, hint=float(e["rank"]))
        if p:
            pitches.append(p)
    session_pitch = sorted(pitches)[len(pitches) // 2] if pitches else None

    for e in entries:
        rank = e["rank"]
        tap_y = e.get("tap_y")
        img = images.get(rank)
        if tap_y is None or img is None:
            status[rank] = "unknown"
            continue
        frame_badge_x = tuple(e.get("badge_x_range") or badge_x)
        ranks_map, pitch = scan_visible_ranks(
            img, frame_badge_x, hint=float(rank), expected_pitch=session_pitch)
        if not ranks_map and not located:
            # Badge column may be calibrated for a different device; find it
            # once from the frames themselves.
            rng, ranks_map, pitch = locate_badge_column(img)
            located = True
            if rng is not None:
                badge_x = rng
        if not ranks_map:
            status[rank] = "unknown"
            continue
        nearest_rank, ny = min(ranks_map.items(), key=lambda kv: abs(kv[1] - int(tap_y)))
        tol = (pitch * 0.55) if pitch else 60.0
        if abs(ny - int(tap_y)) > tol:
            status[rank] = "unknown"
        elif nearest_rank == rank:
            status[rank] = "ok"
        else:
            status[rank] = f"MISMATCH: tapped the rank-{nearest_rank} row"
            anomalies.append(
                f"rank {rank:>3}: lb_frame shows rank {nearest_rank} at the tap position "
                f"-- stats likely belong to rank {nearest_rank} ({capture_dir / e.get('lb_frame', '')})"
            )
    return status, anomalies


#: Where the lifetime label sits inside the strip region, as fractions of that
#: region's height. Expressed relatively so it follows the region across phone
#: and emulator layouts instead of pinning one device's pixels.
_LABEL_BAND_TOP = 0.28
_LABEL_BAND_HEIGHT = 0.23


def strip_is_all_time(img: np.ndarray, region: tuple[int, int, int, int]) -> bool | None:
    """True when this strip frame was captured on the ALL-TIME tab.

    The capture taps the season toggle, sleeps a fixed interval and shoots
    (scrape_timed.py). When the tap does not take -- network lag, a slow
    relayout -- the frame is a perfectly clean capture of the WRONG lifetime,
    so every structural check passes and the numbers are silently career
    totals. One board reached us with 4,298 games on a 35-game ladder.

    The tiles label themselves, so the frame carries the answer:
        season tab    "Season Highest:"
        all-time tab  "Highest Achieved:"
    This is the same trick the STATS capture already uses on its queue label.

    Returns None when the band reads as neither, which must not be treated as
    a failure: an unreadable label is not evidence of the wrong tab, and
    rejecting on it would throw away good rows.
    """
    x, y, w, h = region
    by = y + int(h * _LABEL_BAND_TOP)
    bh = max(1, int(h * _LABEL_BAND_HEIGHT))
    band = img[by:by + bh, x:x + w]
    if band.size == 0:
        return None
    text = (read_text(band, GENERAL_TESSERACT_CONFIG).text or "").lower()
    if "achiev" in text:
        return True
    if "season" in text:
        return False
    return None


def _extract_strip_tesseract(
    img: np.ndarray, region: tuple[int, int, int, int], target: str,
) -> tuple[float | None, int | None, int | None]:
    found = find_champion_winrates(img, region, target=target)
    if any(c.lower() == target.lower() for c in found.keys()):
        return find_target_data(img, region, target)
    return (None, None, None)


def _extract_strip_gemini(
    img: np.ndarray, region: tuple[int, int, int, int], target: str, model: str,
) -> tuple[float | None, int | None, int | None]:
    from .gemini_ocr import read_strip

    x, y, w, h = region
    for t in read_strip(img[y:y + h, x:x + w], model=model):
        canonical = champ_module.match(t.champion.split())
        if canonical is not None and canonical.lower() == target.lower():
            return (t.win_rate, t.score, t.games)
    return (None, None, None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("capture_dir", type=Path, help="A --capture-only session directory")
    parser.add_argument("--engine", choices=("gemini", "auto", "tesseract", "paddle"), default="auto",
                        help="Strip/name extractor. auto uses Tesseract first, then PaddleOCR only for low-confidence reads; gemini is the explicit model path.")
    parser.add_argument("--identity-engine", choices=("paddle", "tesseract"),
                        default=None,
                        help="Engine for the profile NAME crop specifically "
                             "(default paddle). Tesseract cannot flag its own "
                             "errors here, so this crop is read by the better "
                             "engine FIRST rather than as a fallback; the "
                             "stats strip stays on Tesseract because paying 3x "
                             "there would quadruple a full extraction. Pass "
                             "tesseract to A/B one champion.")
    parser.add_argument("--model", default="gemini-3.5-flash-lite")
    parser.add_argument("--workers", type=int, default=4, help="Parallel frame reads")
    parser.add_argument("--output", type=Path, default=None,
                        help="CSV path (default: <capture_dir>/extracted.csv)")
    parser.add_argument("--force", action="store_true",
                        help="Replace the existing CSV even when this run read fewer "
                             "win rates than it already holds. Without this, a run that "
                             "comes back emptier is kept aside instead of overwriting.")
    args = parser.parse_args()

    # Keep the extractor backend explicit and process-local. Gemini remains a
    # model path; its OCR fallback intentionally stays Tesseract unless the
    # caller explicitly requests Paddle for the benchmark.
    if args.engine == "paddle":
        os.environ["OCR_ENGINE"] = "paddle"
    elif args.engine == "tesseract":
        os.environ["OCR_ENGINE"] = "tesseract"
    elif args.engine == "auto":
        os.environ["OCR_ENGINE"] = "auto"
    if args.identity_engine:
        globals()["IDENTITY_ENGINE"] = args.identity_engine
    # --engine tesseract means "no optional backend at all", including for the
    # name crop; honouring the per-crop default there would contradict the
    # flag the user actually passed.
    if args.engine == "tesseract" and not args.identity_engine:
        globals()["IDENTITY_ENGINE"] = "tesseract"

    entries = _load_manifest(args.capture_dir)
    if not entries:
        raise SystemExit("error: manifest is empty")
    target = entries[0]["champion"]
    out_csv = args.output or (args.capture_dir / "extracted.csv")
    print(f"{len(entries)} rank(s) in manifest | target: {target} | "
          f"engine: {args.engine} | names: {IDENTITY_ENGINE}")

    if args.engine == "gemini":
        # Reuse the scraper's key discovery (env var or web-next/.env.local).
        from .scrape_timed import _ensure_gemini_key
        if not _ensure_gemini_key():
            raise SystemExit("error: GEMINI_API_KEY not found; use --engine auto")

    # ---- player identities: profile first, then build/leaderboard fallback ----
    # The profile is the canonical source. It shows one player in a fixed,
    # high-contrast location, preserves mixed case, and carries the Riot tag.
    # The build card is an excellent OCR fallback but renders names in caps.
    # The leaderboard remains the final fallback because it has several small
    # names, variable row backgrounds, truncation, and row-correlation risk.
    names: dict[int, str] = {}
    profile_tags: dict[int, str] = {}
    lb_scores: dict[int, int] = {}
    profile_count = 0
    build_count = 0
    for e in entries:
        rank = e["rank"]
        profile_name = None
        build_name = None
        profile_path = args.capture_dir / e.get("profile_frame", "")
        if profile_path.exists():
            image = cv2.imread(str(profile_path))
            if image is not None:
                try:
                    profile_name, riot_tag = _read_profile_identity(image)
                    if riot_tag:
                        profile_tags[rank] = riot_tag
                except Exception as exc:  # noqa: BLE001 -- continue through fallbacks
                    print(f"  [identity/profile] rank {rank}: {exc}")

        build_path = args.capture_dir / e.get("build_frame", "")
        if build_path.exists():
            image = cv2.imread(str(build_path))
            if image is not None:
                try:
                    build_name = _read_build_name(image)
                except Exception as exc:  # noqa: BLE001 -- leaderboard can still resolve it
                    print(f"  [identity/build] rank {rank}: {exc}")

        # Two independent witnesses reading the SAME string is stronger
        # evidence than any single-read heuristic, so it overrides the one
        # below. That matters for non-Latin names: _usable_ocr_name rejects a
        # low ASCII share because TESSERACT garbles CJK, but with PaddleOCR
        # configured for the script (see ocr.PADDLE_LANGS) both crops read
        # "내가 더 잘해" and "반지하의 제왕" exactly, and the ASCII rule was
        # throwing away two perfect reads that agreed with each other.
        chosen, source = pick_identity(profile_name, build_name,
                                       profile_engine=IDENTITY_ENGINE)
        if source == "profile":
            names[rank] = chosen  # type: ignore[assignment]
            profile_count += 1
        elif source == "build":
            names[rank] = chosen  # type: ignore[assignment]
            build_count += 1
        elif source == "disagree":
            print(f"  [identity] rank {rank}: profile/build disagree "
                  f"({profile_name!r} vs {build_name!r}) -> leaderboard fallback")

    print(f"  [identity] profile={profile_count}, build fallback={build_count}, "
          f"leaderboard pending={len(entries) - len(names)}")

    # One Gemini leaderboard read covers 4-5 ranks, so unresolved names still
    # retain the old economical page-level fallback.
    if args.engine == "gemini":
        from .gemini_ocr import read_leaderboard
        for e in entries:
            if e["rank"] in names:
                continue
            lb_path = args.capture_dir / e.get("lb_frame", "")
            if not lb_path.exists():
                continue
            img = cv2.imread(str(lb_path))
            if img is None:
                continue
            try:
                for row in read_leaderboard(img, model=args.model):
                    names.setdefault(row.rank, row.player_name)
                    if row.score is not None:
                        lb_scores.setdefault(row.rank, row.score)
            except Exception as exc:  # noqa: BLE001 -- keep extracting without names
                print(f"  [names] {lb_path.name}: {exc}")
    else:
        # OCR first, and Gemini ONLY for the names OCR could not read. Tesseract
        # is free and handles ASCII names fine; it garbles CJK and occasionally
        # returns fragments ("oe eee iar immm Ae"). Those are the only ranks
        # worth paying a model for, and one page read covers 4-5 of them, so the
        # bill is a handful of calls per champion rather than one per rank.
        needs_model: list[dict] = []
        for e in entries:
            if e["rank"] in names:
                continue
            lb_path = args.capture_dir / e.get("lb_frame", "")
            tap_y = e.get("tap_y")
            if not lb_path.exists() or tap_y is None:
                continue
            img = cv2.imread(str(lb_path))
            if img is None:
                continue
            region = player_name_region(tap_y, e.get("leaderboard_layout"))
            name = read_player_name(img, region)
            if name and _usable_ocr_name(name):
                names[e["rank"]] = name
            else:
                needs_model.append(e)
                if name:
                    print(f"  [names] rank {e['rank']}: OCR read {name!r}, "
                          f"low confidence -> model")

        if needs_model:
            try:
                from .gemini_ocr import read_leaderboard
                from .scrape_timed import _ensure_gemini_key
                if not _ensure_gemini_key():
                    raise RuntimeError("GEMINI_API_KEY not found")
                seen_frames: set[str] = set()
                calls = 0
                for e in needs_model:
                    if e["rank"] in names:
                        continue          # a previous page read already covered it
                    frame = e.get("lb_frame", "")
                    if not frame or frame in seen_frames:
                        continue
                    seen_frames.add(frame)
                    lb_path = args.capture_dir / frame
                    img = cv2.imread(str(lb_path))
                    if img is None:
                        continue
                    calls += 1
                    for row in read_leaderboard(img, model=args.model):
                        names.setdefault(row.rank, row.player_name)
                        if row.score is not None:
                            lb_scores.setdefault(row.rank, row.score)
                print(f"  [names] {len(needs_model)} rank(s) needed the model, "
                      f"covered by {calls} page read(s)")
            except Exception as exc:  # noqa: BLE001 -- no key/network: keep the OCR names
                print(f"  [names] model fallback unavailable ({exc}); "
                      f"{len(needs_model)} name(s) left unread")
    print(f"names resolved: {len(names)}/{len(entries)}")

    # ---- winrate/score/games from the strip frames (parallel) ----
    Triple = tuple[float | None, int | None, int | None]

    def extract_one(e: dict) -> tuple[int, Triple, bool]:
        """(rank, (winrate, score, games), captured_on_the_all_time_tab)."""
        rank = e["rank"]
        path = args.capture_dir / e["strip_frame"]
        img = cv2.imread(str(path))
        if img is None:
            return rank, (None, None, None), False
        region = tuple(e.get("strip_region") or SCREEN_5_OCR_REGION)  # type: ignore[arg-type]
        # Wrong-lifetime frames are rejected BEFORE extraction. Reading them
        # would succeed and write career totals into a season board.
        if strip_is_all_time(img, region):
            return rank, (None, None, None), True
        # A miss is only believed after the OTHER engine confirms it: Gemini
        # occasionally drops visible tiles (retried first -- flaky misses
        # collapse under retries), and Tesseract sees through an entirely
        # different pipeline. A frame is only "target not visible" when both
        # agree.
        try:
            if args.engine == "gemini":
                for _attempt in range(2):
                    triple = _extract_strip_gemini(img, region, target, args.model)
                    if triple[0] is not None:
                        return rank, triple, False
                return rank, _extract_strip_tesseract(img, region, target), False
            triple = _extract_strip_tesseract(img, region, target)
            if triple[0] is not None:
                return rank, triple, False
            try:
                return rank, _extract_strip_gemini(img, region, target, args.model), False
            except Exception:  # noqa: BLE001 -- no key/network: keep the miss
                return rank, triple, False
        except Exception as exc:  # noqa: BLE001 -- a bad frame shouldn't kill the batch
            print(f"  [strip] rank {rank}: {exc}")
            return rank, (None, None, None), False

    results: dict[int, Triple] = {}
    all_time_ranks: set[int] = set()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for rank, triple, all_time in pool.map(extract_one, entries):
            results[rank] = triple
            if all_time:
                all_time_ranks.add(rank)
            wr = triple[0]
            if all_time:
                note = "ALL-TIME TAB -- season toggle did not take"
            elif wr is None:
                note = "TARGET NOT VISIBLE"
            else:
                note = f"wr={wr}"
            print(f"  rank {rank:>3}: {note}")

    # ---- correlation verification: prove name<->stats joins from the frames ----
    # 1. Tap verification: the badge at tap_y in the pre-tap frame must read
    #    the manifest rank. Catches snap-backs between navigation and tap.
    tap_status, anomalies = verify_taps(args.capture_dir, entries)
    tap_ok = sum(1 for s in tap_status.values() if s == "ok")
    tap_unknown = sum(1 for s in tap_status.values() if s == "unknown")

    # 2. Name agreement: Tesseract's independent read of the name crop at
    #    tap_y should agree with Gemini's page read for that rank. Two readers
    #    on the same pixels agreeing is strong evidence the name is right.
    #    Only meaningful for mostly-ASCII names (Tesseract garbles CJK).
    ascii_share = lambda s: sum(c.isascii() for c in s) / max(1, len(s))  # noqa: E731

    def _looks_like_a_name(s: str) -> bool:
        """Tesseract failure output ('oe eee iar immm Ae') is mostly-ASCII and
        sailed past a plain ASCII-share filter, filing 7 false disagreements
        against perfectly good Gemini names in one run. A usable read has a
        real word in it and is not mostly whitespace fragments."""
        if ascii_share(s) < 0.7 or s.count(" ") / max(1, len(s)) > 0.3:
            return False
        return bool(re.search(r"[A-Za-z0-9]{4}", s))

    if args.engine == "gemini":
        for e in entries:
            rank = e["rank"]
            g_name = names.get(rank)
            tap_y = e.get("tap_y")
            lb_path = args.capture_dir / e.get("lb_frame", "")
            # The name check exists to catch wrong-row captures -- but the
            # badge-based tap verification above proves those authoritatively.
            # Once a rank is tap-verified, a Tesseract/Gemini name mismatch
            # can only be a Tesseract misread of a stylized font (4 false
            # alarms in one 29-rank run). Only second-guess unverified ranks.
            if tap_status.get(rank) == "ok":
                continue
            # Tesseract is only a fair second witness for pure-ASCII names;
            # any diacritic or CJK in the true name guarantees a garbage
            # Tesseract read and a meaningless "disagreement".
            if not g_name or tap_y is None or not lb_path.exists() \
                    or any(not c.isascii() for c in g_name):
                continue
            img = cv2.imread(str(lb_path))
            if img is None:
                continue
            region = player_name_region(tap_y, e.get("leaderboard_layout"))
            t_name = read_player_name(img, region)
            if not t_name or not _looks_like_a_name(t_name):
                continue
            ratio = difflib.SequenceMatcher(None, _norm_name(t_name), _norm_name(g_name)).ratio()
            if ratio < 0.5:
                anomalies.append(
                    f"rank {rank:>3}: name disagreement -- Tesseract read {t_name!r}, "
                    f"Gemini read {g_name!r} ({lb_path})"
                )

    # 3. Duplicate players: the same name under two manifest ranks means a
    #    snap-back was scraped twice under different assumed ranks.
    manifest_ranks = {e["rank"] for e in entries}
    by_name: dict[str, list[int]] = {}
    for r in manifest_ranks:
        n = names.get(r)
        if n:
            by_name.setdefault(_norm_name(n), []).append(r)
    for norm, rs in by_name.items():
        if norm and len(rs) > 1:
            anomalies.append(
                f"ranks {sorted(rs)}: same player name {names[rs[0]]!r} under multiple ranks "
                f"-- probable snap-back re-scrape; keep one, re-check the rest"
            )

    # ---- write CSV + review worklist ----
    # Into a sidecar, not over the real file. Whether this run is an improvement
    # is only knowable once it has finished, and by then the old rows are gone
    # if it wrote in place.
    prior = _winrate_count(out_csv)
    staged_csv = out_csv.with_name(out_csv.name + ".new")
    if staged_csv.exists():
        staged_csv.unlink()
    writer = CSVWriter(staged_csv)
    missing: list[dict] = []
    all_time: list[dict] = []
    found = 0
    for e in entries:
        rank = e["rank"]
        wr, sc, gm = results.get(rank, (None, None, None))
        if sc is None:
            sc = lb_scores.get(rank)
        if wr is not None:
            found += 1
        elif rank in all_time_ranks:
            # Kept separate from `missing`: the frame is not unreadable, it
            # holds the wrong lifetime, and no amount of hand-reading turns
            # career totals into season ones.
            all_time.append(e)
        else:
            missing.append(e)
        writer.write(LeaderboardRow(
            champion=target,
            rank=rank,
            player_name=names.get(rank, ""),
            score=sc,
            games=gm,
            winrate=wr,
            captured_at=e.get("captured_at", ""),
        ))

    # ---- extended frames: rank popup, stats pages, build popups ----
    # All optional (present only when the capture ran with --stats/--builds).
    # Each write their own artifact next to extracted.csv.
    def _read_frame_file(name: str | None):
        if not name:
            return None
        fp = args.capture_dir / name
        return cv2.imread(str(fp)) if fp.exists() else None

    if True:
        # Extras used to sit behind `engine == "gemini"`, which silently
        # produced no stats.csv and no builds.jsonl on an OCR run -- and builds
        # are icon-matched, so they never needed a model at all. Stats now read
        # by OCR with a model fallback; the popup still needs the model, so it
        # is skipped rather than faked when there is no key.
        model_stats = args.engine == "gemini"
        read_rank_popup = read_stats_page = None
        try:
            from .gemini_ocr import read_rank_popup, read_stats_page  # noqa: F811
        except Exception as exc:  # noqa: BLE001
            print(f"  [extras] model reader unavailable ({exc}); "
                  f"OCR only, popups skipped")

        # canonical item-slug resolution against the site's item catalog
        items_path = Path(__file__).resolve().parent.parent / "data" / "items.json"
        item_canon: dict[str, str] = {}
        if items_path.exists():
            _norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())  # noqa: E731
            for it in json.loads(items_path.read_text(encoding="utf-8")):
                item_canon[_norm(it["name"])] = it["slug"]
                # Gemini reads "Amaranth Twinguard" off the popup where the
                # catalog says "Amaranth's Twinguard" -- index a possessive-
                # stripped alias so mid-name 's never blocks resolution.
                item_canon.setdefault(_norm(re.sub(r"'s\b", "", it["name"], flags=re.I)), it["slug"])
                item_canon.setdefault(_norm(it["slug"]), it["slug"])

        def resolve_item(name: str) -> str | None:
            c = re.sub(r"[^a-z0-9]", "", name.lower())
            if c in item_canon:
                return item_canon[c]
            for cand in (c.rstrip("s"), c + "s"):
                if cand in item_canon:
                    return item_canon[cand]
            hits = {slug for cc, slug in item_canon.items() if c and (c in cc or cc in c)}
            if len(hits) == 1:
                return hits.pop()
            # Last resort for one-character OCR slips: a very close fuzzy
            # match (>=0.9) is unambiguous at this catalog size.
            close = difflib.get_close_matches(c, list(item_canon), n=2, cutoff=0.9)
            return item_canon[close[0]] if len(close) == 1 else None

        def extract_extras(e: dict) -> tuple[int, dict | None, dict[str, dict], dict | None]:
            rank = e["rank"]
            popup = stats = build = None
            profile_ranks = None
            stats_by_queue: dict[str, dict] = {}
            img = _read_frame_file(e.get("popup_frame"))
            if img is not None and read_rank_popup is not None:
                try:
                    popup = read_rank_popup(img, model=args.model)
                except Exception as exc:  # noqa: BLE001
                    print(f"  [popup] rank {rank}: {exc}")
            for queue, fn in (e.get("stats_frames") or {}).items():
                img = _read_frame_file(fn)
                if img is None:
                    continue
                # OCR FIRST. The stats page is a fixed grid of large numerals,
                # which reads at ~99% of fields for a hundredth of the cost of
                # a model call, and there are two of these pages per player.
                # The model is only paid when OCR leaves real holes.
                if not model_stats:
                    try:
                        read = read_stats_page_ocr(img)
                        conf = stats_confidence(read)
                        if conf >= STATS_OCR_MIN_CONFIDENCE:
                            read.setdefault("queue", None)
                            stats_by_queue[queue] = read
                            continue
                        print(f"  [stats/{queue}] rank {rank}: OCR confidence "
                              f"{conf:.2f} below {STATS_OCR_MIN_CONFIDENCE} -> model")
                    except Exception as exc:  # noqa: BLE001
                        print(f"  [stats/{queue}] rank {rank}: OCR failed ({exc}) -> model")
                if read_stats_page is None:
                    continue
                try:
                    stats_by_queue[queue] = read_stats_page(img, model=args.model)
                except Exception as exc:  # noqa: BLE001
                    print(f"  [stats/{queue}] rank {rank}: {exc}")
            img = _read_frame_file(e.get("build_frame"))
            if img is not None:
                # NO MODEL CALL HERE. Template matching owns every icon: the
                # vision model invented runes that are not in the game for
                # 17.6% of slots and disagreed with itself on two reads of the
                # same image, so its spells/runes/items were being overwritten
                # wholesale. What remained of its answer -- champion,
                # player_name, position -- is read by nothing downstream
                # (_builds_by_rank takes items, runes and spells only), and
                # the champion is already in the manifest while the rank is
                # independently tap-verified. That made this a fifth of every
                # session's API spend, 50 calls of 250, buying nothing.
                build = {"champion": e.get("champion")}
                try:
                    from .icon_match import read_build_icons

                    icons = read_build_icons(img)
                    for key in ("spells", "runes", "items"):
                        if icons.get(key):
                            build[key] = icons[key]
                    build["_iconConfidence"] = icons.get("_confidence")
                    unresolved = sum(1 for k in ("spells", "runes", "items")
                                     for v in build.get(k, []) if v == "?")
                    if unresolved:
                        print(f"  [build] rank {rank}: {unresolved} icon slot(s) unresolved")
                except Exception as exc:  # noqa: BLE001
                    print(f"  [icons] rank {rank}: {exc}")
                    build = None
            img = _read_frame_file(e.get("profile_frame"))
            if img is not None:
                try:
                    profile_ranks = read_profile_ranks(img)
                except Exception as exc:  # noqa: BLE001 -- one bad frame must not stop a batch
                    print(f"  [profile-rank] rank {rank}: {exc}")
            # The current profile badge supersedes the legacy popup/stats tier.
            # Keep the old fields for sessions captured before this frame was
            # added, and preserve the historical badge/count separately.
            if profile_ranks is not None:
                popup = popup or {"player_name": names.get(rank, "")}
                # Current profile captures carry the canonical identity even
                # though the old mini-popup no longer exists.
                popup["player_name"] = names.get(rank, popup.get("player_name", ""))
                if profile_tags.get(rank):
                    popup["riot_tag"] = profile_tags[rank]
                current = profile_ranks.get("current") or {}
                historical = profile_ranks.get("historical") or {}
                if current.get("rank"):
                    popup["tier"] = current["rank"]
                    popup["current_rank"] = current["rank"]
                popup["current_rank_count"] = current.get("count")
                popup["historical_rank"] = historical.get("rank")
                popup["historical_rank_count"] = historical.get("count")
                popup["rank_confidence"] = profile_ranks.get("confidence")
                popup["rank_source"] = profile_ranks.get("source", "template")
                print(f"  [profile-rank] rank {rank}: "
                      f"current={current.get('rank') or '?'} ({current.get('count') or '?'}) "
                      f"historical={historical.get('rank') or '?'} ({historical.get('count') or '?'}) "
                      f"confidence={profile_ranks.get('confidence', 'low')}")
            # The popup card animates in, so a screenshot taken a beat early
            # catches it before the tier line paints -- 71 of 686 captured
            # players had no tier. The STATS page prints the same tier and is
            # already captured, so ask it rather than lose the field. The
            # canonicaliser also drops sub-Diamond readings: those are the
            # player's Adventure-mode rank shown in the ranked slot, and
            # nobody below Diamond is in a champion's top 50.
            if popup is not None and not (profile_ranks and (profile_ranks.get("current") or {}).get("rank")):
                before = popup.get("tier")
                popup["tier"] = resolve_tier(
                    before, *(s.get("tier") for s in stats_by_queue.values()))
                if popup["tier"] != before:
                    if not popup["tier"]:
                        where = "dropped, not a ranked tier"
                    elif canonical_tier(before):
                        where = "cleaned"       # the popup's own value, titled
                    else:
                        where = "from stats page"
                    print(f"  [tier] rank {rank}: {before!r} -> {popup['tier']!r} ({where})")
            return rank, popup, stats_by_queue, build

        has_extras = any(e.get("popup_frame") or e.get("profile_frame") or e.get("stats_frames") or e.get("build_frame")
                         for e in entries)
        if has_extras:
            import csv as _csv
            popups: dict[int, dict] = {}
            stats_rows: list[dict] = []
            builds: list[dict] = []
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                for rank, popup, stats_by_queue, build in pool.map(extract_extras, entries):
                    if popup:
                        popups[rank] = popup
                    for queue, st in stats_by_queue.items():
                        st["_rank"], st["_requested_queue"] = rank, queue
                        stats_rows.append(st)
                    if build:
                        build["_rank"] = rank
                        builds.append(build)

            if popups:
                with (args.capture_dir / "players.csv").open("w", encoding="utf-8", newline="") as f:
                    w = _csv.writer(f)
                    w.writerow(["rank", "player_name", "riot_tag", "tier", "level", "guild",
                                "current_rank", "current_rank_count", "historical_rank",
                                "historical_rank_count", "rank_confidence", "rank_source"])
                    for r in sorted(popups):
                        pp = popups[r]
                        w.writerow([r, pp.get("player_name") or names.get(r, ""),
                                    pp.get("riot_tag"), pp.get("tier"),
                                    pp.get("level"), pp.get("guild"),
                                    pp.get("current_rank"), pp.get("current_rank_count"),
                                    pp.get("historical_rank"), pp.get("historical_rank_count"),
                                    pp.get("rank_confidence"), pp.get("rank_source")])
                print(f"players.csv : {len(popups)} rows (profile rank + tier/level/tag)")

            if stats_rows:
                cols = ["rank", "queue", "requested_queue", "games", "win_rate", "kda",
                        "teamfight_participation", "gold_per_minute",
                        "damage_dealt_per_match", "damage_taken_per_match",
                        "turret_damage_per_match", "mvp", "s_rating", "a_rating",
                        "legendary", "pentakill", "quadra_kill", "triple_kill", "first_blood"]
                mismatched = 0
                with (args.capture_dir / "stats.csv").open("w", encoding="utf-8", newline="") as f:
                    w = _csv.writer(f)
                    w.writerow(cols)
                    for st in sorted(stats_rows, key=lambda x: (x["_rank"], x["_requested_queue"])):
                        shown = str(st.get("queue") or "").lower()
                        req = st["_requested_queue"]
                        # 'legendary' request must show 'Legendary Ranked';
                        # 'ranked' must show plain 'Ranked'
                        ok_q = ("legendary" in shown) == (req == "legendary")
                        if not ok_q:
                            mismatched += 1
                        # OCR often captures the dropdown as "Legendary Ranked ~"
                        # (the trailing glyph is the menu icon). Persist the
                        # canonical queue label while retaining requested_queue
                        # for auditability.
                        queue_label = ("Legendary Ranked" if "legendary" in shown
                                       else "Ranked" if "ranked" in shown
                                       else st.get("queue"))
                        w.writerow([st["_rank"], queue_label, req,
                                    st.get("games"), st.get("win_rate"), st.get("kda"),
                                    st.get("teamfight_participation"), st.get("gold_per_minute"),
                                    st.get("damage_dealt_per_match"), st.get("damage_taken_per_match"),
                                    st.get("turret_damage_per_match"), st.get("mvp"),
                                    st.get("s_rating"), st.get("a_rating"), st.get("legendary"),
                                    st.get("pentakill"), st.get("quadra_kill"),
                                    st.get("triple_kill"), st.get("first_blood")])
                note = f" ({mismatched} queue mismatches -- check dropdown taps)" if mismatched else ""
                print(f"stats.csv   : {len(stats_rows)} rows{note}")

            if builds:
                with (args.capture_dir / "builds.jsonl").open("w", encoding="utf-8") as f:
                    for b in sorted(builds, key=lambda x: x["_rank"]):
                        items = [{"name": n, "slug": resolve_item(str(n)) if n and n != "?" else None}
                                 for n in (b.get("items") or [])]
                        f.write(json.dumps({
                            "rank": b["_rank"],
                            "champion": b.get("champion"),
                            "spells": b.get("spells"),
                            "runes": b.get("runes"),
                            "items": items,
                        }, ensure_ascii=False) + chr(10))
                unresolved = sum(1 for b in builds for n in (b.get("items") or [])
                                 if n and n != "?" and resolve_item(str(n)) is None)
                print(f"builds.jsonl: {len(builds)} builds ({unresolved} unresolved item names)")

    # Promote or keep. A run that read fewer win rates than the file already
    # holds is a worse answer to the same question, and the usual cause is an
    # exhausted API quota rather than anything about the frames.
    regressed = found < prior and not args.force
    if regressed:
        print(f"\nextracted    : {found}/{len(entries)} ranks")
        print(f"REFUSING to replace {out_csv.name}: it holds {prior} win rates and this "
              f"run read {found}.", file=sys.stderr)
        print(f"  kept  : {out_csv}", file=sys.stderr)
        print(f"  staged: {staged_csv}   (delete it, or re-run with --force to promote)",
              file=sys.stderr)
        print("  an empty run usually means the extraction API is out of quota, not that "
              "the frames are bad -- they are still on disk, so try again later.",
              file=sys.stderr)
        return 1
    out_csv.unlink(missing_ok=True)
    staged_csv.replace(out_csv)

    report = args.capture_dir / "needs_manual.txt"
    sections: list[str] = []
    if missing:
        sections.append("TARGET NOT VISIBLE -- read these frames by hand and fill the blank CSV rows:\n"
                        + "\n".join(f"  rank {e['rank']:>3}: {args.capture_dir / e['strip_frame']}"
                                    for e in missing))
    if all_time:
        sections.append(
            "ALL-TIME TAB -- these frames were captured before the season toggle"
            " took, so they show career totals, not this season. They cannot be\n"
            "read by hand; the ranks below need RE-CAPTURING:\n"
            + "\n".join(f"  rank {e['rank']:>3}: {args.capture_dir / e['strip_frame']}"
                        for e in all_time))
    if anomalies:
        sections.append("CORRELATION ANOMALIES -- name and stats may not belong together:\n"
                        + "\n".join(f"  {a}" for a in anomalies))
    if sections:
        report.write_text("\n\n".join(sections) + "\n", encoding="utf-8")
    elif report.exists():
        report.unlink()

    print(f"\nextracted    : {found}/{len(entries)} ranks")
    print(f"tap-verified : {tap_ok} ok, {tap_unknown} unverifiable, "
          f"{len(entries) - tap_ok - tap_unknown} MISMATCHED")
    print(f"CSV          : {out_csv}")
    if sections:
        print(f"review       : {len(missing)} missing + {len(all_time)} all-time + {len(anomalies)} anomaly item(s) -> {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
