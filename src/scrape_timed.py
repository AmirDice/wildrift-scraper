"""Timer-driven manual-scroll scraper.

Wild Rift's leaderboard refreshes every ~60 seconds at the back-from-profile
transition. So the strategy is:

  1. Run a window: scrape profiles back-to-back from a known starting rank.
  2. Before starting a NEW profile, check elapsed time. If finishing the
     profile would push us past the refresh threshold, stop the window early
     rather than getting caught mid-scrape.
  3. Tell you exactly which rank to scroll to next. You scroll the
     leaderboard manually, press Enter, and the next window starts.

Works with any ADB device — emulator OR a phone over USB. Just point
--device at the right ADB serial:

    # emulator (MuMu default)
    python -m src.scrape_timed --target Aatrox --device 127.0.0.1:7555

    # physical phone via USB (run `adb devices` to find the serial)
    python -m src.scrape_timed --target Aatrox --device ABCD1234

Tune --window-duration (when to call it quits in a window) and
--expected-profile-time (how long one full tap chain takes) based on what
you measure. The bot prints both after every window so you can see how it
performs and adjust.

Pause: press 'p' (Windows only). Bot finishes the current profile, then
waits for Enter.

Usage:
    python -m src.scrape_timed --target Aatrox --n 200 \\
        --window-duration 55 --expected-profile-time 6 --profiles-per-window 20
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import subprocess
import threading
import time
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np

from .adb_client import ADBClient, ADBError
from .config import (
    ROWS_PER_PAGE,
    SCREEN_2_BADGE_X_RANGE,
    SCREEN_2_NAME_HEIGHT,
    SCREEN_2_NAME_X_RANGE,
    SCREEN_1_NAME_X_RANGE,
    SCREEN_1_ROW_TAP_X,
    SCREEN_2_BACK_POINT,
    SCREEN_2_BOOK_X,
    SCREEN_2_BUILD_CLOSE,
    SCREEN_2_CHAMP_LABEL_REGION,
    SCREEN_2_NAME_Y_OFFSET,
    SCREEN_5_OCR_REGION,
    SCREEN_5_STATS_TAB,
    STATS_LIST_TOGGLE,
    STATS_QUEUE_DROPDOWN,
    STATS_QUEUE_OPTIONS,
    load_calibration,
    load_screen_points,
    save_calibration,
)
from .navigator import LeaderboardNavigator
from .ocr import (
    locate_badge_column,
    read_champion_name,
    read_player_name,
    read_rank_badge,
    read_text,
    scan_champion_rows,
    scan_visible_ranks,
)
from .storage import CSVWriter, LeaderboardRow
from .strip import find_target_in_strip


# ---- pause key polling (Windows-only) ----
if os.name == "nt":
    import msvcrt

    def _key_pressed() -> str | None:
        if msvcrt.kbhit():
            ch = msvcrt.getch()
            if ch in (b"\x00", b"\xe0"):
                msvcrt.getch()
                return None
            try:
                return ch.decode("utf-8").lower()
            except UnicodeDecodeError:
                return None
        return None
else:
    def _key_pressed() -> str | None:
        return None


def _handle_pause(window_start: float) -> float:
    """Pause until user presses Enter. Returns how long the pause lasted so
    the caller can shift its window_start_time forward by that amount (paused
    time shouldn't count against the window budget)."""
    print("\n=== PAUSED ===  fix Wild Rift state, then press Enter to resume")
    pause_start = time.time()
    input()
    print("=== RESUMED ===\n")
    return time.time() - pause_start


class PauseRequested(Exception):
    """Raised mid-profile when user presses 'p' so the caller can abort
    cleanly, prompt for state recovery, and retry the same rank."""
    pass


def _ensure_gemini_key() -> bool:
    """True if GEMINI_API_KEY is available. Falls back to reading it out of
    web-next/.env.local (where it already lives for the site) so the scraper
    works without exporting it separately."""
    if os.environ.get("GEMINI_API_KEY"):
        return True
    env_file = Path(__file__).resolve().parent.parent / "web-next" / ".env.local"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*GEMINI_API_KEY\s*=\s*(.+?)\s*$", line)
            if m:
                os.environ["GEMINI_API_KEY"] = m.group(1).strip().strip('"')
                print("[gemini] using GEMINI_API_KEY from web-next/.env.local")
                return True
    return False


class NameReader:
    """Async page-level name/score reader for the leaderboard screen.

    One Gemini call reads ALL visible rows (rank, name, score) — including the
    CJK names Tesseract cannot read. Calls run on a background thread so they
    are off the critical path: fire on the pre-tap screenshot, collect at
    CSV-write time. Because one page yields 4-5 ranks per call, "submit only
    when the current rank is unknown" naturally batches to one call per page.
    """

    def __init__(self, model: str) -> None:
        self._model = model
        self._pool = ThreadPoolExecutor(max_workers=1)
        self._lock = threading.Lock()
        self._names: dict[int, str] = {}
        self._scores: dict[int, int] = {}
        self._pending: Future | None = None
        self._errors = 0

    def cached(self, rank: int) -> str | None:
        with self._lock:
            return self._names.get(rank)

    def cached_score(self, rank: int) -> int | None:
        with self._lock:
            return self._scores.get(rank)

    def maybe_submit(self, img: np.ndarray, rank: int) -> None:
        """Queue a page read if `rank` is unknown and nothing is in flight."""
        if self._errors >= 3:  # repeated API failures: stop burning time
            return
        with self._lock:
            if rank in self._names:
                return
            if self._pending is not None and not self._pending.done():
                return
            self._pending = self._pool.submit(self._read, img.copy())

    def _read(self, img: np.ndarray) -> None:
        try:
            from .gemini_ocr import read_leaderboard
            rows = read_leaderboard(img, model=self._model)
        except Exception as e:  # noqa: BLE001 -- network/API: names just stay Tesseract
            self._errors += 1
            print(f"  [gemini-names] read failed ({e}); Tesseract fallback stays in effect")
            return
        with self._lock:
            for r in rows:
                if r.player_name:
                    self._names[r.rank] = r.player_name
                if r.score is not None:
                    self._scores[r.rank] = r.score

    def get(self, rank: int, timeout: float = 3.0) -> str | None:
        """Wait briefly for an in-flight read, then return the cached name."""
        pending = self._pending
        if pending is not None and self.cached(rank) is None:
            try:
                pending.result(timeout=timeout)
            except Exception:  # noqa: BLE001 -- timeout or read error: use fallback
                pass
        return self.cached(rank)


def _check_pause_or_raise() -> None:
    """Poll the keyboard; if 'p' was pressed, raise PauseRequested. Caller
    catches it, pauses, and retries the same rank on resume."""
    if _key_pressed() == "p":
        raise PauseRequested()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", default="Aatrox", help="Champion whose winrate to extract per player")
    parser.add_argument("--n", type=int, default=200, help="Total ranks to scrape across all windows")
    parser.add_argument("--start-rank", type=int, default=1)
    parser.add_argument("--profiles-per-window", type=int, default=20,
                        help="Hard cap on profiles per window. Most windows will hit the time cap first.")
    parser.add_argument("--window-duration", type=float, default=55.0,
                        help="Soft deadline (seconds). Bot won't START a profile if elapsed + expected-profile-time would exceed this.")
    parser.add_argument("--expected-profile-time", type=float, default=4.0,
                        help="Rough seconds per full tap chain on YOUR setup. Used only to decide whether the next profile fits in the window budget. Tune based on the per-window summary the bot prints.")
    parser.add_argument("--device", default="127.0.0.1:7555",
                        help="ADB device — emulator IP:port OR phone USB serial")
    parser.add_argument("--no-connect", action="store_true")
    parser.add_argument("--step-wait", type=float, default=0.8,
                        help="Wait after each tap. Lower if your device's UI transitions are fast.")
    parser.add_argument("--tap-hold-ms", type=int, default=60,
                        help="How long each tap is held (ms). 60 is fast and reliable; raise if taps get dropped.")
    parser.add_argument("--output", type=Path, default=Path("data/winrates.csv"))
    parser.add_argument("--save-screenshots", action="store_true")
    parser.add_argument("--max-strip-swipes", type=int, default=3)
    parser.add_argument("--strip-swipe-scale", type=float, default=0.7)
    parser.add_argument("--strip-swipe-duration-ms", type=int, default=400)
    parser.add_argument("--max-retries-per-player", type=int, default=2)
    parser.add_argument("--no-rank-check", action="store_true",
                        help="Skip the pre-tap rank-badge OCR check (faster but won't catch unexpected refreshes)")
    parser.add_argument("--auto-scroll", action="store_true",
                        help="Tap-by-detection mode: read the rank badges to find rows, travel to the "
                             "target rank automatically (fling + slow-drag correction), and recover from "
                             "leaderboard snap-backs without manual scrolling. Falls back to a manual "
                             "prompt whenever detection is lost.")
    parser.add_argument("--badge-x", default=None,
                        help="Rank-badge column x-range as 'x0,x1' (auto-located and remembered if omitted)")
    parser.add_argument("--gemini-names", action="store_true",
                        help="Read player names + scores with one async Gemini call per leaderboard page "
                             "(handles CJK names Tesseract cannot read; off the critical path). "
                             "Tesseract stays as the fallback.")
    parser.add_argument("--gemini-strip", action="store_true",
                        help="Read the screen-5 champion strip with one structured Gemini call per frame "
                             "instead of ~4 Tesseract passes. Falls back to Tesseract on any API error.")
    parser.add_argument("--gemini-model", default="gemini-3.5-flash-lite",
                        help="Gemini model for --gemini-names / --gemini-strip")
    parser.add_argument("--capture-only", action="store_true",
                        help="Fastest mode: save screenshots + a manifest instead of reading anything "
                             "on the critical path (no strip OCR, no swipes, no live name read). "
                             "Extract afterwards with: python -m src.extract_frames <capture dir>")
    parser.add_argument("--capture-dir", type=Path, default=Path("data/captures"),
                        help="Where --capture-only sessions are stored")
    parser.add_argument("--builds", action="store_true",
                        help="capture-only: also capture each player's BUILD popup (book icon "
                             "on the leaderboard row; ~2s/profile)")
    parser.add_argument("--champions", type=int, default=0,
                        help="Carousel mode: process this many champions from the CHAMPION tab, "
                             "navigating rows by name OCR and returning after each top-N capture. "
                             "Requires --auto-scroll --capture-only.")
    parser.add_argument("--auto-extract", action="store_true",
                        help="Carousel: launch offline extraction for each finished champion in "
                             "the background, so capture and extraction overlap")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Carousel: skip champions that already have a near-complete capture "
                             "session under --capture-dir (resume overnight runs)")
    parser.add_argument("--unattended", action="store_true",
                        help="Never block on a keyboard prompt when detection is lost: abandon the "
                             "current champion and move on. Abandoned champions stay below the "
                             "--skip-existing completeness bar, so the next run redoes them.")
    parser.add_argument("--stats", action="store_true",
                        help="capture-only: also capture the rank popup and the STATS page for "
                             "BOTH queues (Ranked + Legendary Ranked; ~5s/profile)")
    args = parser.parse_args()

    if args.champions and not (args.auto_scroll and args.capture_only):
        print("error: --champions requires --auto-scroll --capture-only", file=sys.stderr)
        return 1

    capture_dir: Path | None = None
    if args.capture_only:
        if not args.champions:
            # One directory per session so reruns never mix frames. Carousel
            # mode creates a fresh directory per champion instead.
            stamp = time.strftime("%Y%m%d_%H%M")
            capture_dir = args.capture_dir / f"{args.target.lower().replace(' ', '-')}_{stamp}"
            capture_dir.mkdir(parents=True, exist_ok=True)
        # Live Gemini is pointless here -- extraction happens offline.
        args.gemini_names = False
        args.gemini_strip = False

    name_reader: NameReader | None = None
    if args.gemini_names or args.gemini_strip:
        if _ensure_gemini_key():
            if args.gemini_names:
                name_reader = NameReader(args.gemini_model)
        else:
            print("warning: GEMINI_API_KEY not found; --gemini-names/--gemini-strip disabled", file=sys.stderr)
            args.gemini_names = False
            args.gemini_strip = False

    client = ADBClient(device=args.device)
    if not args.no_connect:
        try:
            client.connect()
        except ADBError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1

    s2 = load_screen_points(2)
    s3 = load_screen_points(3)
    s4 = load_screen_points(4)
    s5 = load_screen_points(5)

    missing = []
    if "player_row_1" not in s2:
        missing.append("screen_2.json:player_row_1 (rank 1 tap position)")
    if "profile" not in s3:
        missing.append("screen_3.json:profile (view-profile button)")
    if "champion_lane" not in s4:
        missing.append("screen_4.json:champion_lane (CHAMPION AND LANE tab)")
    if "recent" not in s5:
        missing.append("screen_5.json:recent (sort/filter button tapped after CnL)")
    if "back" not in s5:
        missing.append("screen_5.json:back (top-left back chevron)")
    if missing:
        print("error: missing required coord keys:", file=sys.stderr)
        for m in missing:
            print(f"  {m}", file=sys.stderr)
        return 1

    target_x, start_y = s2["player_row_1"]

    # Prefer EXPLICIT per-row y positions when mapped (most accurate — row
    # spacing isn't actually uniform: rank-1->2 has extra header padding).
    # Fall back to derived pitch if only a subset is mapped.
    row_ys: list[int] = []
    pitch_y = 0.0  # only used in pitch-fallback mode
    n_mapped = sum(1 for i in range(1, 6) if f"player_row_{i}" in s2)
    if n_mapped >= 2:
        # Build explicit list of available row ys (contiguous from row 1)
        for i in range(1, 6):
            key = f"player_row_{i}"
            if key not in s2:
                break
            row_ys.append(s2[key][1])
        rows_per_window = len(row_ys)
        pitch_src = f"explicit ys from {rows_per_window} mapped rows: {row_ys}"
    else:
        rows_per_window = 1
        pitch_src = ("single-row mode — only player_row_1 is mapped. Map "
                     "player_row_2 (or more) on screen 2 to scrape multiple "
                     "ranks per scroll.")

    s3_view = s3["profile"]
    s4_lane = s4["champion_lane"]
    s5_back = s5["back"]
    s5_recent = s5["recent"]
    writer = CSVWriter(args.output)
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)

    def slot_xy(slot: int) -> tuple[int, int]:
        if row_ys:
            return (target_x, row_ys[slot])
        return (target_x, int(round(start_y + slot * pitch_y)))

    def scrape_one(rank: int, tap_y: int) -> tuple[float | None, int | None, int | None, str | None]:
        """Tap chain through one player's profile at the given row y. Returns
        (winrate, score, games, player_name). Raises PauseRequested if the user
        presses 'p' between any two steps so the caller can abort and retry."""
        px, py = target_x, tap_y

        # Player name from the leaderboard BEFORE tapping in. When the async
        # Gemini page reader already knows this rank (one call covers the whole
        # page), skip the screenshot + Tesseract read entirely; otherwise OCR
        # it as the fallback and hand the screenshot to the page reader.
        # Capture mode reads nothing: it saves the leaderboard frame for the
        # offline extractor and moves on.
        player_name = name_reader.cached(rank) if name_reader else None
        if capture_dir is not None:
            try:
                # Reuse the navigator's decision frame as the leaderboard
                # capture: it is the EXACT frame tap_y came from (stronger
                # for offline tap-verification) and saves a ~1.2s screenshot.
                pre_img = None
                try:
                    pre_img = nav.last_frame
                except NameError:
                    pre_img = None
                if pre_img is None:
                    pre_img = client.screenshot()
                cv2.imwrite(str(capture_dir / f"{rank:03d}_leaderboard.jpg"), pre_img,
                            [cv2.IMWRITE_JPEG_QUALITY, 92])
            except Exception:
                pass
        elif player_name is None:
            try:
                pre_img = client.screenshot()
                if name_reader is not None:
                    name_reader.maybe_submit(pre_img, rank)
                name_x0, name_x1 = SCREEN_2_NAME_X_RANGE
                name_region = (
                    name_x0,
                    max(0, py + SCREEN_2_NAME_Y_OFFSET),
                    name_x1 - name_x0,
                    SCREEN_2_NAME_HEIGHT,
                )
                player_name = read_player_name(pre_img, name_region)
            except Exception:
                player_name = None

        build_frame: str | None = None
        if capture_dir is not None and args.builds:
            # BUILD popup via the book icon on the row we just located. The
            # popup prints "Rank: N" inside, so correlation is intrinsic.
            client.tap(SCREEN_2_BOOK_X, py, hold_ms=args.tap_hold_ms)
            time.sleep(args.step_wait + 0.2)
            build_frame = f"{rank:03d}_build.jpg"
            cv2.imwrite(str(capture_dir / build_frame), client.screenshot(),
                        [cv2.IMWRITE_JPEG_QUALITY, 92])
            client.tap(*SCREEN_2_BUILD_CLOSE, hold_ms=args.tap_hold_ms)
            time.sleep(args.step_wait)
        # Single tap per transition. Pause is checked after each step so a
        # mid-profile 'p' press lands within ~step_wait seconds.
        client.tap(px, py, hold_ms=args.tap_hold_ms)
        time.sleep(args.step_wait)
        popup_frame: str | None = None
        if capture_dir is not None:
            # Rank popup: name#tag, tier (Grandmaster etc.), account level --
            # free, we pass through this screen on the way to the profile.
            popup_frame = f"{rank:03d}_popup.jpg"
            cv2.imwrite(str(capture_dir / popup_frame), client.screenshot(),
                        [cv2.IMWRITE_JPEG_QUALITY, 92])
        _check_pause_or_raise()

        client.tap(*s3_view, hold_ms=args.tap_hold_ms)
        time.sleep(args.step_wait)
        _check_pause_or_raise()

        client.tap(*s4_lane, hold_ms=args.tap_hold_ms)
        time.sleep(args.step_wait)
        _check_pause_or_raise()

        # Tap RECENT to switch to the recent-games sort/filter view before
        # reading the champion strip.
        client.tap(*s5_recent, hold_ms=args.tap_hold_ms)
        time.sleep(args.step_wait)
        _check_pause_or_raise()

        if capture_dir is not None:
            # Capture mode: save the strip frame + manifest entry and leave.
            # No OCR, no swipes -- if the target isn't in the visible tiles,
            # the offline extractor flags this rank for manual review.
            strip_img = client.screenshot()
            strip_name = f"{rank:03d}_strip.jpg"
            cv2.imwrite(str(capture_dir / strip_name), strip_img,
                        [cv2.IMWRITE_JPEG_QUALITY, 92])
            stats_frames: dict[str, str] = {}
            if args.stats:
                # STATS tab -> list view. The page always opens on Ranked
                # (owner-verified), so capture it directly and open the
                # dropdown only ONCE, to switch to Legendary Ranked. The
                # extractor re-verifies the queue label visible in each
                # frame, so a surprise default gets flagged, not mislabeled.
                client.tap(*SCREEN_5_STATS_TAB, hold_ms=args.tap_hold_ms)
                time.sleep(args.step_wait + 0.3)
                client.tap(*STATS_LIST_TOGGLE, hold_ms=args.tap_hold_ms)
                time.sleep(0.5)
                fn = f"{rank:03d}_stats_ranked.jpg"
                cv2.imwrite(str(capture_dir / fn), client.screenshot(),
                            [cv2.IMWRITE_JPEG_QUALITY, 92])
                stats_frames["ranked"] = fn
                client.tap(*STATS_QUEUE_DROPDOWN, hold_ms=args.tap_hold_ms)
                time.sleep(0.45)
                client.tap(*STATS_QUEUE_OPTIONS["legendary"], hold_ms=args.tap_hold_ms)
                time.sleep(0.7)
                fn = f"{rank:03d}_stats_legendary.jpg"
                cv2.imwrite(str(capture_dir / fn), client.screenshot(),
                            [cv2.IMWRITE_JPEG_QUALITY, 92])
                stats_frames["legendary"] = fn
            entry = {
                "champion": args.target,
                "rank": rank,
                "strip_frame": strip_name,
                "lb_frame": f"{rank:03d}_leaderboard.jpg",
                "tap_y": py,
                "strip_region": list(SCREEN_5_OCR_REGION),
                "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            if build_frame:
                entry["build_frame"] = build_frame
            if popup_frame:
                entry["popup_frame"] = popup_frame
            if stats_frames:
                entry["stats_frames"] = stats_frames
            with (capture_dir / "manifest.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            wr = sc = gm = None
        else:
            wr, sc, gm, _, _, last_img = find_target_in_strip(
                client, args.target,
                max_swipes=args.max_strip_swipes,
                swipe_scale=args.strip_swipe_scale,
                swipe_duration_ms=args.strip_swipe_duration_ms,
                wait_after_swipe=args.step_wait,
                use_gemini=args.gemini_strip,
                gemini_model=args.gemini_model,
            )
            if args.save_screenshots:
                cv2.imwrite(str(data_dir / f"run_rank_{rank:03d}.png"), last_img)
        _check_pause_or_raise()

        if capture_dir is not None and args.stats:
            # Exit from the stats page is normally two backs (stats -> profile
            # -> leaderboard), but the chain cannot PROVE it is on the stats
            # page (a missed tap leaves it one screen shallower, and then a
            # fixed second back exits the leaderboard to the MAIN MENU -- a
            # live Karma run died exactly this way). Nor can 'leaderboard'
            # be recognised by badges alone: the rows repopulate slowly after
            # backing, and an impatient extra press on a loading list is the
            # same main-menu exit. The reliable identity signal is the
            # champion LABEL (bottom-left): it renders with the screen chrome
            # immediately, appears on NO other screen in the chain (verified
            # against all ten flow frames and a captured main-menu frame),
            # and is independent of row loading. So: CHECK for the label
            # before every press, and never press more than 3 times.
            # The first press is blind: this code runs right after the stats
            # phase, so the screen is the stats page (or, if a tap missed,
            # the profile) -- one back from either depth cannot exit the
            # leaderboard, and skipping the check saves a screenshot round.
            client.back()
            time.sleep(args.step_wait + 0.3)
            for _press in range(3):
                img_chk = client.screenshot()
                if read_champion_name(img_chk, SCREEN_2_CHAMP_LABEL_REGION) is not None:
                    break
                try:
                    # RAW scan, not the self-relocating wrapper: mid-chain
                    # screens read as empty, and an empty read sends the
                    # wrapper into its ~15s column-relocation sweep -- twice
                    # per back-out, which tripled the profile time.
                    ranks_chk, _pchk = scan_visible_ranks(
                        img_chk, badge_x, expected_pitch=nav.last_pitch)
                    if len(ranks_chk) >= 3:
                        break
                except NameError:   # manual mode: no scanner state in scope
                    break
                except Exception:   # noqa: BLE001 -- scan hiccup: label rules anyway
                    pass
                if _press == 2:
                    print("  [detect] back-out could not verify the leaderboard -- stopping presses")
                    break
                client.back()
                time.sleep(args.step_wait + 0.3)
        else:
            client.tap(*s5_back, hold_ms=args.tap_hold_ms)
            time.sleep(args.step_wait)
        return wr, sc, gm, player_name

    def quick_rank_check(slot: int) -> int | None:
        """Return the integer rank that OCR sees at the given slot, or None if
        nothing parseable. Returns within ~200ms."""
        try:
            img = client.screenshot()
            row_y = int(round(start_y + slot * pitch_y))
            crop = img[max(0, row_y - 22): row_y + 22,
                       SCREEN_2_BADGE_X_RANGE[0]:SCREEN_2_BADGE_X_RANGE[1]]
            text = read_text(crop).text
            digits = re.sub(r"\D", "", text)
            if not digits:
                return None
            v = int(digits)
            return v if 1 <= v <= 250 else None
        except Exception:
            return None

    # Cap profiles_per_window by what's actually mapped. A "window" can't
    # be longer than the number of visible rows we can tap before needing
    # a manual scroll.
    effective_window_profiles = min(args.profiles_per_window, rows_per_window)
    # The rank-badge OCR check uses SCREEN_2_BADGE_X_RANGE which was tuned
    # for the 1600x900 emulator. Phone layouts (2340x1080 etc.) need a new
    # crop region. Default the check OFF unless user has handled this.
    # (--auto-scroll mode does not need it: it auto-locates the badge column.)
    if not args.no_rank_check:
        args.no_rank_check = True

    # ------------------------------------------------------------------
    # AUTO-SCROLL MODE: tap-by-detection + closed-loop travel.
    #
    # Instead of requiring rows to land on calibrated positions (impossible:
    # Android flings are inertial), every profile starts from a screenshot:
    # scan the rank-badge column (one small OCR, all visible rows at once),
    # tap the target rank at its REAL y. Travel to off-screen ranks is dead
    # reckoning (fast flings) plus one slow-drag correction — slow drags have
    # no inertia, so they move exactly the requested distance. Snap-backs
    # after ~6 profile views are detected by the same scan (suddenly seeing
    # ranks 1-5) and recovered by travelling again; scrolling itself does not
    # trigger the reset, so a ~6s journey is safe.
    # ------------------------------------------------------------------
    if args.auto_scroll:
        cal = load_calibration()
        if args.badge_x:
            try:
                p0, p1 = (int(v) for v in args.badge_x.split(","))
                badge_x: tuple[int, int] = (p0, p1)
            except ValueError:
                print(f"error: --badge-x must be 'x0,x1', got {args.badge_x!r}", file=sys.stderr)
                return 1
        elif "badge_x0" in cal and "badge_x1" in cal:
            badge_x = (int(cal["badge_x0"]), int(cal["badge_x1"]))
        else:
            badge_x = SCREEN_2_BADGE_X_RANGE
        fling_rows = float(cal.get("fling_rows", 10.0))  # rows one fling moves; self-tunes

        low_reads = 0

        def scan(img, hint: float | None = None) -> tuple[dict[int, int], float | None]:
            """Badge scan; re-locates the column on a total miss OR after
            consecutive degraded reads. (A miscalibrated column can read the
            narrow single-digit ranks fine while clipping two-digit ones --
            it looks like flaky deep-rank OCR, but it's geometry.)"""
            nonlocal badge_x, low_reads
            ranks, pitch = scan_visible_ranks(img, badge_x, hint=hint,
                                              expected_pitch=nav.last_pitch)
            if len(ranks) >= 3:
                low_reads = 0
                return ranks, pitch
            low_reads += 1
            if not ranks or low_reads >= 2:
                rng, ranks2, pitch2 = locate_badge_column(img)
                # A re-location gets PERSISTED, so it must prove itself: full
                # window, physical pitch, and agreement with where the
                # navigator believes we are. One real run re-located on a
                # degraded frame, locked onto avatar digits, and poisoned
                # every following run -- a proven-good column must never lose
                # to one bad frame.
                ok = (
                    rng is not None and len(ranks2) >= 4 and pitch2 is not None
                    and (nav.last_pitch is None
                         or abs(pitch2 - nav.last_pitch) / nav.last_pitch <= 0.3)
                    and (hint is None
                         or abs((min(ranks2) + max(ranks2)) / 2 - hint) <= 8)
                    # A real column DRIFTS (the clipping fix moved it ~30px);
                    # it never teleports. A candidate that does not even
                    # overlap the proven column is another screen's digits:
                    # a run with hint=None once accepted x=(835,1005) mid
                    # back-out, saved it, and every later scan of a perfect
                    # leaderboard failed. Refuse, never persist.
                    and rng is not None
                    and min(rng[1], badge_x[1]) - max(rng[0], badge_x[0])
                        >= 0.5 * (badge_x[1] - badge_x[0])
                )
                if ok:
                    badge_x = rng
                    save_calibration({"badge_x0": rng[0], "badge_x1": rng[1]})
                    print(f"  [detect] badge column re-located at x={rng} (saved to calibration)")
                    low_reads = 0
                    return ranks2, pitch2
            return ranks, pitch

        def slow_drag(rows: float, pitch: float) -> None:
            """Move the list by ~rows rows with an inertia-free drag.
            rows > 0 reveals deeper ranks (content moves up)."""
            H = nav.screen_h or 1080
            dist = int(round(rows * pitch))
            if dist == 0:
                return
            y_from = int(H * 0.72) if dist > 0 else int(H * 0.30)
            y_to = max(int(H * 0.08), min(int(H * 0.92), y_from - dist))
            dur = max(500, min(1300, int(abs(y_from - y_to) * 1.8)))
            client.swipe(target_x, y_from, target_x, y_to, dur)
            time.sleep(0.45)

        def fling(down: bool) -> None:
            """Fast inertial page-jump. Imprecise by nature; used only for
            long hauls, always followed by a scan + slow-drag correction.
            The settle wait must outlast the coast, or the next scan reads a
            moving (blurred, misread-prone) list."""
            H = nav.screen_h or 1080
            y_a, y_b = int(H * 0.80), int(H * 0.22)
            if down:
                client.swipe(target_x, y_a, target_x, y_b, 120)
            else:
                client.swipe(target_x, y_b, target_x, y_a, 120)
            time.sleep(1.0)

        def stable_screenshot() -> np.ndarray:
            """Screenshot only once the list has STOPPED moving: two frames
            250ms apart must match on the badge column. Every 'clearly visible
            badge that failed to read' traced back to scanning a frame taken
            while the list was still coasting or bounce-settling -- the saved
            (settled) frames from the same runs all scan perfectly."""
            prev = client.screenshot()
            cur = prev
            for _ in range(4):
                time.sleep(0.15)
                cur = client.screenshot()
                a = prev[:, badge_x[0]:badge_x[1]]
                b = cur[:, badge_x[0]:badge_x[1]]
                if a.shape == b.shape and float(np.mean(cv2.absdiff(a, b))) < 2.0:
                    return cur
                prev = cur
            return cur

        def careful_rescan(img) -> dict[int, int]:
            """Arbitration read for when the action ledger proves the fast
            scan wrong (e.g. a systematically dropped leading digit).

            Preferred arbitrator: one Gemini read of the leaderboard -- it
            reads the stylized badges near-perfectly where Tesseract cannot.
            Its rank NUMBERS are mapped onto the badge y POSITIONS the fast
            scan located (positions are reliable even when digits misread;
            both are top-to-bottom). Falls back to a per-badge multi-PSM
            Tesseract pass without a key or on API failure. Only runs in the
            rare locked state, so its 1-2s latency is irrelevant."""
            fast, _p = scan(img)
            ys = sorted(fast.values())
            if not ys:
                return {}
            if _ensure_gemini_key():
                from .gemini_ocr import read_leaderboard
                # One empty Gemini response during a live run left a confirmed
                # misread ('30-34' as '50-54') with no arbiter and cost the
                # whole champion. Empty/transient failures deserve one retry;
                # a sane-but-unusable answer does not.
                for attempt in (1, 2):
                    try:
                        rows = read_leaderboard(img, model=args.gemini_model)
                    except Exception as e:  # noqa: BLE001 -- retry once, then Tesseract
                        print(f"  [detect] gemini arbitration failed ({e})"
                              + (" -- retrying" if attempt == 1 else ""))
                        if attempt == 1:
                            time.sleep(0.6)
                        continue
                    rr = sorted(r.rank for r in rows)
                    if rr and rr == list(range(rr[0], rr[0] + len(rr))):
                        if len(rr) == len(ys) + 1:
                            # Gemini saw a row whose badge the fast scan missed
                            # (usually clipped under the header): drop the top.
                            rr = rr[1:]
                        if len(rr) == len(ys):
                            mapping = dict(zip(rr, ys))
                            print(f"  [detect] arbitration: screen shows ranks "
                                  f"{rr[0]}-{rr[-1]}")
                            return mapping
                    break
            reads: list[tuple[int, int]] = []  # (y, rank)
            for y in ys:
                r = read_rank_badge(img, 0, y, 0.0, badge_x)
                if r is not None:
                    reads.append((y, r[0]))
            best: list[tuple[int, int]] = []
            for i in range(len(reads)):
                chain = [reads[i]]
                for j in range(i + 1, len(reads)):
                    if reads[j][1] == chain[-1][1] + 1:
                        chain.append(reads[j])
                if len(chain) > len(best):
                    best = chain
            if len(best) < 2:
                return {}
            out = {r: y for y, r in best}
            # fill unread badges by grid position relative to the chain
            pitch = (best[-1][0] - best[0][0]) / (best[-1][1] - best[0][1])
            for y in ys:
                slots = (y - best[0][0]) / pitch
                slot = round(slots)
                if abs(slots - slot) <= 0.35:
                    inferred = best[0][1] + slot
                    if inferred >= 1:
                        out.setdefault(inferred, y)
            return out

        def _dump_frame(img, rank):
            dump = Path("data/debug_scans")
            dump.mkdir(parents=True, exist_ok=True)
            path = dump / f"lost_rank{rank}_{time.strftime('%H%M%S')}.png"
            try:
                cv2.imwrite(str(path), img)
                return str(path)
            except Exception:  # noqa: BLE001
                return None

        # The travel logic lives in navigator.py so it can be simulated
        # offline against replayed failure frames (tests/test_navigator.py).
        nav = LeaderboardNavigator(
            screenshot=stable_screenshot,
            screenshot_fast=client.screenshot,
            scan=scan,
            drag_rows=slow_drag,
            fling=fling,
            arbitrate=careful_rescan,
            on_fling_calibrated=lambda v: save_calibration({"fling_rows": round(v, 1)}),
            dump_frame=_dump_frame,
            fling_rows=fling_rows,
        )

        print(f"target        : {args.target}")
        print(f"ranks         : {args.start_rank}..{args.start_rank + args.n - 1}")
        print(f"mode          : AUTO-SCROLL (tap-by-detection)")
        print(f"badge column  : x={badge_x} (auto-relocates if wrong)")
        print(f"fling estimate: ~{fling_rows:.0f} rows/fling (self-tuning)")
        print(f"CSV output    : {args.output}")
        print()
        print("Open the leaderboard at ANY scroll position. The bot finds its own way.")
        print("Press 'p' anytime to pause after the current profile.")
        input("Press Enter to start: ")

        # The carousel installs a self-recovery here: from any wrecked
        # mid-chain UI state, walk back to the champions page and re-enter
        # the current champion's leaderboard. run_ranks calls it before
        # abandoning a champion.
        recovery: dict = {"fn": None}

        def run_ranks() -> int:
            """Capture ranks start..start+n-1 for the CURRENT args.target
            into the CURRENT capture_dir. Returns the number of profiles
            captured (the carousel uses 0 as a leaderboard-down signal).
            Re-raises KeyboardInterrupt after its summary so a carousel
            stops cleanly."""
            interrupted = False
            current_rank = args.start_rank
            end_rank = args.start_rank + args.n - 1
            successes = 0
            total = 0
            recoveries = 0
            t0 = time.time()
            try:
                while current_rank <= end_rank:
                    if _key_pressed() == "p":
                        _handle_pause(time.time())

                    tap_y = nav.ensure_visible(current_rank)
                    if tap_y is None:
                        print(f"\n[detect] lost position looking for rank {current_rank}.")
                        if args.unattended:
                            # Overnight runs cannot wait on a human. First
                            # choice: SELF-RECOVER -- re-enter this champion's
                            # leaderboard from the champions page and continue
                            # at the same rank. Only when that fails (twice)
                            # is the champion abandoned; the partial session
                            # stays under the --skip-existing completeness
                            # bar, so the next run redoes it from scratch.
                            if recovery["fn"] is not None and recoveries < 2:
                                recoveries += 1
                                print(f"[unattended] self-recovery {recoveries}/2: "
                                      f"re-entering {args.target}'s leaderboard")
                                if recovery["fn"]():
                                    nav.last_center = None
                                    continue
                            print(f"[unattended] abandoning {args.target} at rank "
                                  f"{current_rank} -- will be redone next run")
                            break
                        input(f">>> Scroll so rank {current_rank} is visible, then press Enter: ")
                        continue

                    t_profile = time.time()
                    print(f"\n--- rank {current_rank} (tap y={tap_y}) ---")
                    wr: float | None = None
                    sc: int | None = None
                    gm: int | None = None
                    player_name: str | None = None
                    for attempt in range(args.max_retries_per_player):
                        try:
                            wr, sc, gm, player_name = scrape_one(current_rank, tap_y)
                            # Capture mode has no live read result -- one clean pass
                            # through the tap chain is success by definition.
                            if wr is not None or capture_dir is not None:
                                break
                        except PauseRequested:
                            print(f"\n[PAUSED] rank {current_rank} aborted mid-chain.")
                            input("Restore the leaderboard, then press Enter to re-do this rank: ")
                        except Exception:
                            print(f"  exception on attempt {attempt + 1}:")
                            traceback.print_exc()
                            # Verified recovery: CHECK first (the exception may
                            # have left us on the leaderboard already -- an
                            # unneeded back exits it), then back out one press
                            # at a time. The champion label is the identity
                            # signal; it shows even while the rows repopulate.
                            for _ in range(4):
                                img_chk = client.screenshot()
                                if read_champion_name(img_chk, SCREEN_2_CHAMP_LABEL_REGION) is not None:
                                    break
                                try:
                                    # raw scan: the wrapper's relocation sweep
                                    # costs ~15s on every empty mid-chain frame
                                    r_chk, _pc = scan_visible_ranks(
                                        img_chk, badge_x, expected_pitch=nav.last_pitch)
                                    if len(r_chk) >= 3:
                                        break
                                except Exception:  # noqa: BLE001
                                    pass
                                client.back()
                                time.sleep(0.4)
                        # Whatever happened, re-detect before the next attempt —
                        # the list may have snapped back mid-recovery.
                        ny = nav.ensure_visible(current_rank)
                        if ny is None:
                            break
                        tap_y = ny

                    # Collect the async Gemini page read (if any): its names beat
                    # Tesseract's (CJK), and its screen-2 score fills a missing one.
                    if name_reader is not None:
                        g_name = name_reader.get(current_rank)
                        if g_name:
                            player_name = g_name
                        if sc is None:
                            sc = name_reader.cached_score(current_rank)

                    # Capture mode: the manifest is the record; the offline
                    # extractor writes the CSV.
                    if capture_dir is None:
                        writer.write(LeaderboardRow(
                            champion=args.target,
                            rank=current_rank,
                            player_name=player_name or "",
                            score=sc,
                            games=gm,
                            winrate=wr,
                        ))
                    total += 1
                    if wr is not None or capture_dir is not None:
                        successes += 1
                    print(f"  player={player_name!r}  winrate={wr}  score={sc}  games={gm}"
                          f"  [took {time.time() - t_profile:.1f}s]")
                    current_rank += 1
            except KeyboardInterrupt:
                interrupted = True
                print("\n^C — stopping")

            mins = (time.time() - t0) / 60
            print(f"\n==================== SESSION DONE ====================")
            print(f"profiles scraped : {total} in {mins:.1f} min")
            if capture_dir is not None:
                print(f"frames captured  : {capture_dir}")
                print(f"next step        : python -m src.extract_frames \"{capture_dir}\"")
            else:
                print(f"winrate parsed   : {successes}")
                print(f"CSV              : {args.output}")
            if interrupted:
                raise KeyboardInterrupt
            return total

        if not args.champions:
            try:
                run_ranks()
            except KeyboardInterrupt:
                pass
            return 0

        # ------------------------------------------------------------------
        # CHAMPION CAROUSEL: full automation across the CHAMPION tab.
        # Rows have no number badges, so navigation is name-driven: scan the
        # visible champion names (unread rows become grid slots), tap the
        # first unvisited one, let the screen-2 champion label be the
        # AUTHORITATIVE identity, capture its top-N, back out verified, and
        # page down when the visible rows are exhausted.
        # ------------------------------------------------------------------
        scraped: set[str] = set()
        if args.skip_existing:
            for mf in args.capture_dir.glob("*/manifest.jsonl"):
                lines = [ln for ln in mf.read_text(encoding="utf-8").splitlines() if ln.strip()]
                if len(lines) < max(1, int(args.n * 0.9)):
                    continue
                try:
                    ch = json.loads(lines[0]).get("champion")
                except json.JSONDecodeError:
                    continue
                if ch:
                    scraped.add(ch)
            if scraped:
                print(f"[carousel] resuming: {len(scraped)} champion(s) already captured")

        print(f"CAROUSEL MODE: {args.champions} champion(s), top {args.n} each"
              + (", builds" if args.builds else "") + (", stats" if args.stats else "")
              + (", UNATTENDED" if args.unattended else ""))
        print("Open the CHAMPION tab of the leaderboard (the champions list).")
        input("Press Enter to start: ")

        done = 0
        stale_pages = 0
        empty_sessions = 0   # consecutive zero-profile champions (down detector)
        t_carousel = time.time()

        def back_to_champions() -> None:
            """Verified return to the champions page (never blind).

            HOW we leave matters as much as how many times: the champions TAB
            is not in Android's back stack, so SYSTEM back from a champion's
            leaderboard pops the whole leaderboard activity to the MAIN MENU
            (a live run ended there when one flaky label read triggered this
            recovery). When the current screen IS a leaderboard, leave via
            the chevron tap; system back is only for deeper screens (profile,
            popups), where it is the correct control."""
            for _ in range(4):
                img = client.screenshot()
                if scan_champion_rows(img, SCREEN_1_NAME_X_RANGE):
                    return
                on_leaderboard = read_champion_name(img, SCREEN_2_CHAMP_LABEL_REGION) is not None
                if not on_leaderboard:
                    try:
                        r_chk, _pc = scan_visible_ranks(img, badge_x,
                                                        expected_pitch=nav.last_pitch)
                        on_leaderboard = len(r_chk) >= 3
                    except Exception:  # noqa: BLE001
                        pass
                if on_leaderboard:
                    client.tap(*SCREEN_2_BACK_POINT, hold_ms=args.tap_hold_ms)
                else:
                    client.back()
                time.sleep(0.7)

        def reenter_champion() -> bool:
            """Self-recovery from any wrecked mid-chain state: navigate back
            to the champions page, page down until the CURRENT champion's row
            is visible, tap it, and verify the label. True = the leaderboard
            is open again (at the top; the caller resets position memory)."""
            target = args.target
            back_to_champions()
            for _page in range(12):
                img = stable_screenshot()
                slots = scan_champion_rows(img, SCREEN_1_NAME_X_RANGE)
                if not slots:
                    return False
                H = nav.screen_h or img.shape[0]
                hit = next((y for y, cname in slots
                            if cname == target and 260 <= y <= H * 0.88), None)
                if hit is not None:
                    client.tap(SCREEN_1_ROW_TAP_X, hit, hold_ms=args.tap_hold_ms)
                    time.sleep(args.step_wait + 0.5)
                    for _read in range(3):
                        if read_champion_name(client.screenshot(),
                                              SCREEN_2_CHAMP_LABEL_REGION) == target:
                            return True
                        time.sleep(0.6)
                    return False
                y_from = int(H * 0.78)
                y_to = max(int(H * 0.10), y_from - int(4 * 146))
                client.swipe(SCREEN_1_ROW_TAP_X, y_from, SCREEN_1_ROW_TAP_X, y_to,
                             max(500, min(1300, int((y_from - y_to) * 1.8))))
                time.sleep(0.7)
            return False

        recovery["fn"] = reenter_champion

        def find_partial_session(champ: str) -> tuple[Path | None, int]:
            """The newest incomplete capture session for `champ`, and the rank
            to resume from. (None, 1) when there is nothing worth resuming.

            A champion that died at rank 45 used to redo all 44 captured
            profiles in a fresh directory; resuming appends to the same
            manifest, so extraction and the completeness bar see one whole
            session. Sessions with fewer than 3 ranks are not worth the
            deep-rank journey bookkeeping -- redo those from scratch."""
            best: tuple[str, Path, int] | None = None
            for mf in args.capture_dir.glob("*/manifest.jsonl"):
                lines = [ln for ln in mf.read_text(encoding="utf-8").splitlines() if ln.strip()]
                if not lines:
                    continue
                try:
                    if json.loads(lines[0]).get("champion") != champ:
                        continue
                    ranks_seen = {int(json.loads(ln)["rank"]) for ln in lines}
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue
                if len(ranks_seen) >= max(1, int(args.n * 0.9)):
                    continue    # complete: --skip-existing territory, not ours
                if len(ranks_seen) < 3 or max(ranks_seen) >= args.n:
                    continue
                # Never stitch two leaderboard weeks into one session: a
                # partial older than ~20h may predate a ranking reset, and
                # its ranks 1..k would describe a different ladder than the
                # fresh ranks k+1..n appended to it.
                try:
                    stamp = time.strptime(mf.parent.name.split("_", 1)[1], "%Y%m%d_%H%M")
                    if time.time() - time.mktime(stamp) > 20 * 3600:
                        continue
                except (IndexError, ValueError):
                    continue
                if best is None or mf.parent.name > best[0]:
                    best = (mf.parent.name, mf.parent, max(ranks_seen))
            if best is None:
                return None, 1
            return best[1], best[2] + 1

        prev_names: set[str] = set()
        skip_ys: list[int] = []   # rows on THIS page that resolved to captured champions
        try:
            while done < args.champions:
                img = stable_screenshot()
                slots = scan_champion_rows(img, SCREEN_1_NAME_X_RANGE)
                H = nav.screen_h or img.shape[0]
                cand = None
                for y, cname in slots:
                    if not (260 <= y <= H * 0.88):
                        continue          # header overlap / bottom clip
                    if cname is not None and cname in scraped:
                        continue
                    if any(abs(y - sy) < 40 for sy in skip_ys):
                        continue          # tapped before; resolved to a captured champion
                    cand = (y, cname)
                    break
                if cand is None:
                    # The list resets to the TOP each time we back out, so a
                    # resumed (or deep) run must page down through screens of
                    # already-captured names to reach fresh ones. A page whose
                    # names are still CHANGING between swipes is progress --
                    # only an unchanged or unreadable view counts as stale.
                    names = {c for _, c in slots if c}
                    if names and names != prev_names:
                        stale_pages = 0
                    else:
                        stale_pages += 1
                    prev_names = names or prev_names
                    if not slots and stale_pages >= 3:
                        print("[carousel] champions page not detected -- stopping")
                        break
                    if stale_pages >= 5:
                        print("[carousel] end of the champion list")
                        break
                    # page exhausted (or unreadable): scroll one page down
                    y_from = int(H * 0.78)
                    y_to = max(int(H * 0.10), y_from - int(4 * 146))
                    client.swipe(SCREEN_1_ROW_TAP_X, y_from, SCREEN_1_ROW_TAP_X, y_to,
                                 max(500, min(1300, int((y_from - y_to) * 1.8))))
                    time.sleep(0.7)
                    skip_ys.clear()       # rows moved; the y blacklist no longer maps
                    continue
                stale_pages = 0
                prev_names = {c for _, c in slots if c}

                y, cname = cand
                client.tap(SCREEN_1_ROW_TAP_X, y, hold_ms=args.tap_hold_ms)
                time.sleep(args.step_wait + 0.5)
                # One label read is not a verdict: the screen may still be
                # loading, and a false 'no label' sends us into a back-out
                # that skips a champion (and once ended on the main menu).
                label = None
                for _read in range(3):
                    label = read_champion_name(client.screenshot(), SCREEN_2_CHAMP_LABEL_REGION)
                    if label is not None:
                        break
                    time.sleep(0.6)
                if label is None:
                    print(f"[carousel] no champion label after tapping y={y} -- backing out")
                    if cname:
                        scraped.add(cname)   # do not loop on a broken row
                    else:
                        skip_ys.append(y)    # nameless row: remember it by position
                    back_to_champions()
                    continue
                if label in scraped:
                    print(f"[carousel] {label} already captured -- skipping")
                    scraped.add(label)
                    skip_ys.append(y)        # this row IS that champion; never re-tap it
                    client.tap(*SCREEN_2_BACK_POINT, hold_ms=args.tap_hold_ms)
                    time.sleep(args.step_wait + 0.3)
                    back_to_champions()
                    continue

                slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
                resume_dir, resume_from = find_partial_session(label)
                if resume_dir is not None:
                    capture_dir = resume_dir
                else:
                    capture_dir = args.capture_dir / f"{slug}_{time.strftime('%Y%m%d_%H%M')}"
                    capture_dir.mkdir(parents=True, exist_ok=True)
                args.target = label
                nav.last_center = None   # fresh position memory per champion
                print()
                print(f"#################### {label} ({done + 1}/{args.champions}) ####################")
                if resume_dir is not None:
                    print(f"[carousel] resuming {label} at rank {resume_from} "
                          f"({resume_dir.name}: ranks 1-{resume_from - 1} already captured)")
                prev_start, prev_n = args.start_rank, args.n
                if resume_dir is not None:
                    args.start_rank = resume_from
                    args.n = prev_n - (resume_from - prev_start)
                try:
                    n_captured = run_ranks()
                finally:
                    args.start_rank, args.n = prev_start, prev_n
                scraped.add(label)
                done += 1
                if args.unattended:
                    # Champions failing with ZERO profiles back-to-back means
                    # the leaderboard itself is broken (rankings lock, server
                    # maintenance) -- stop instead of burning the champion
                    # list on a dead screen all night.
                    empty_sessions = empty_sessions + 1 if n_captured == 0 else 0
                    if empty_sessions >= 3:
                        print("[unattended] 3 consecutive champions captured NOTHING -- "
                              "the leaderboard looks down; stopping the carousel")
                        break
                if args.auto_extract:
                    log_path = capture_dir / "extract.log"
                    with log_path.open("w", encoding="utf-8") as lf:
                        subprocess.Popen(
                            [sys.executable, "-m", "src.extract_frames", str(capture_dir)],
                            stdout=lf, stderr=subprocess.STDOUT,
                            cwd=str(Path(__file__).resolve().parent.parent),
                        )
                    print(f"[carousel] extraction launched in background -> {log_path}")

                client.tap(*SCREEN_2_BACK_POINT, hold_ms=args.tap_hold_ms)
                time.sleep(args.step_wait + 0.4)
                back_to_champions()
        except KeyboardInterrupt:
            print()
            print("^C -- carousel stopped")

        mins = (time.time() - t_carousel) / 60
        print()
        print("==================== CAROUSEL DONE ====================")
        print(f"champions captured : {done} in {mins:.1f} min")
        print(f"sessions under     : {args.capture_dir}")
        print("extract each session with: python -m src.extract_frames <session dir>")
        return 0


    print(f"target            : {args.target}")
    print(f"ranks to scrape   : {args.start_rank}..{args.start_rank + args.n - 1}")
    print(f"row mapping       : {pitch_src}")
    print(f"profiles per scroll: {effective_window_profiles}  (mapped rows: {rows_per_window})")
    print(f"window time cap   : {args.window_duration:.0f}s")
    print(f"expected per profile: {args.expected_profile_time:.1f}s  (tune this after first window)")
    print(f"rank-check OCR    : {'OFF' if args.no_rank_check else 'ON'}")
    print(f"CSV output        : {args.output}")
    print()
    print(f"Open Wild Rift. Scroll the leaderboard so rank {args.start_rank} is at slot 0 (top).")
    print("Press 'p' anytime during scraping to pause after the current profile.")
    input("Press Enter when ready to start: ")

    current_rank = args.start_rank
    end_rank = args.start_rank + args.n - 1
    successes = 0
    total_profiles = 0
    window_num = 0

    try:
        while current_rank <= end_rank:
            window_num += 1
            window_start_rank = current_rank
            window_start_time = time.time()
            window_profiles = 0
            window_successes = 0

            print(f"\n========== WINDOW {window_num} starts at rank {window_start_rank} ==========")

            while True:
                if current_rank > end_rank:
                    break
                if window_profiles >= effective_window_profiles:
                    print(f"  reached profile cap ({window_profiles}/{effective_window_profiles})")
                    break

                elapsed = time.time() - window_start_time
                # Soft deadline: would the next profile push us past the window?
                if elapsed + args.expected_profile_time > args.window_duration:
                    print(f"  would push past {args.window_duration:.0f}s window "
                          f"(elapsed={elapsed:.1f}s + ~{args.expected_profile_time:.1f}s); "
                          f"stopping window early")
                    break

                # Pause check between profiles
                if _key_pressed() == "p":
                    pause_dur = _handle_pause(window_start_time)
                    window_start_time += pause_dur

                slot = (current_rank - window_start_rank) % rows_per_window

                # Optional rank-badge OCR sanity check (catches mid-window refresh)
                if not args.no_rank_check:
                    detected = quick_rank_check(slot)
                    if detected is not None and detected != current_rank:
                        # Slot 0 has rank-1 trophy that won't OCR; only react
                        # to a confirmed wrong rank (not an empty OCR).
                        print(f"\n  [GUARDRAIL] expected rank {current_rank} at slot {slot}, "
                              f"OCR sees rank {detected}. Leaderboard probably refreshed.")
                        print(f"  Stopping window early. Your last good rank was {current_rank - 1}.")
                        break

                profile_start = time.time()
                print(f"\n--- rank {current_rank} (slot {slot}, t={elapsed:.1f}s, "
                      f"window {window_profiles + 1}/{effective_window_profiles}) ---")

                wr: float | None = None
                sc: int | None = None
                gm: int | None = None
                player_name: str | None = None
                # Loop wraps the retry block so a mid-profile 'p' press redoes
                # the whole rank from scratch instead of advancing.
                while True:
                    pause_mid_profile = False
                    for attempt in range(args.max_retries_per_player):
                        try:
                            wr, sc, gm, player_name = scrape_one(current_rank, slot_xy(slot)[1])
                            if wr is not None or capture_dir is not None:
                                break
                        except PauseRequested:
                            pause_mid_profile = True
                            break
                        except Exception:
                            print(f"  exception on attempt {attempt + 1}:")
                            traceback.print_exc()
                            # Hardware-back recovery
                            for _ in range(3):
                                client.back()
                                time.sleep(0.2)

                    if not pause_mid_profile:
                        break

                    # User paused mid-chain. Shift window_start so the pause
                    # doesn't count against the timing budget, and prompt
                    # them to restore leaderboard state before retrying.
                    print(f"\n[PAUSED MID-PROFILE] aborted rank {current_rank} mid-chain.")
                    print(f"Navigate Wild Rift back to the leaderboard so rank {current_rank} is at slot {slot}.")
                    pause_t0 = time.time()
                    input("Press Enter to resume and RE-DO this profile: ")
                    window_start_time += time.time() - pause_t0
                    print(f"=== RESUMED, re-doing rank {current_rank} ===\n")
                    # Reset profile_start so the per-profile timer reflects
                    # only the successful run, not the aborted attempt.
                    profile_start = time.time()

                profile_time = time.time() - profile_start
                print(f"  player={player_name!r}  winrate={wr}  score={sc}  games={gm}  [took {profile_time:.1f}s]")

                if name_reader is not None:
                    g_name = name_reader.get(current_rank)
                    if g_name:
                        player_name = g_name
                    if sc is None:
                        sc = name_reader.cached_score(current_rank)

                if capture_dir is None:
                    writer.write(LeaderboardRow(
                        champion=args.target,
                        rank=current_rank,
                        player_name=player_name or "",
                        score=sc,
                        games=gm,
                        winrate=wr,
                    ))
                if wr is not None or capture_dir is not None:
                    successes += 1
                    window_successes += 1
                current_rank += 1
                window_profiles += 1
                total_profiles += 1

            elapsed = time.time() - window_start_time
            avg_per_profile = elapsed / window_profiles if window_profiles else 0.0
            print(f"\n========== WINDOW {window_num} done ==========")
            print(f"  scraped {window_profiles} profiles in {elapsed:.1f}s  (avg {avg_per_profile:.1f}s/profile)")
            print(f"  {window_successes}/{window_profiles} had winrate parsed")

            if current_rank > end_rank:
                break

            # Manual scroll prompt
            print(f"\n>>> Scroll Wild Rift so rank {current_rank} is at slot 0 (top of visible list). <<<")
            print("    (Or type 'p' + Enter to pause first if Wild Rift needs other fixing.)")
            response = input("    Press Enter to start the next window: ").strip().lower()
            if response.startswith("p"):
                _handle_pause(time.time())

    except KeyboardInterrupt:
        print("\n^C — stopping")

    print(f"\n==================== SESSION DONE ====================")
    print(f"total profiles scraped : {total_profiles}")
    if capture_dir is not None:
        print(f"frames captured        : {capture_dir}")
        print(f"next step              : python -m src.extract_frames \"{capture_dir}\"")
    else:
        print(f"with winrate parsed    : {successes}")
        print(f"CSV                    : {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
