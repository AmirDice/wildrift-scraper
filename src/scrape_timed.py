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
import os
import re
import sys
import time
import traceback
from pathlib import Path

import cv2

from .adb_client import ADBClient, ADBError
from .config import (
    ROWS_PER_PAGE,
    SCREEN_2_BADGE_X_RANGE,
    SCREEN_2_NAME_HEIGHT,
    SCREEN_2_NAME_X_RANGE,
    SCREEN_2_NAME_Y_OFFSET,
    load_screen_points,
)
from .ocr import read_player_name, read_text
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
    args = parser.parse_args()

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

    def scrape_one(rank: int, slot: int) -> tuple[float | None, int | None, int | None, str | None]:
        """Tap chain through one player's profile. Returns (winrate, score,
        games, player_name). Raises PauseRequested if the user presses 'p'
        between any two steps so the caller can abort and retry the rank."""
        px, py = slot_xy(slot)

        # OCR the player name from the leaderboard BEFORE tapping in — the
        # row is already visible at slot's y position. Cheaper than reading
        # it from inside the profile and we keep it even if profile load
        # fails downstream.
        try:
            pre_img = client.screenshot()
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

        # Single tap per transition. Pause is checked after each step so a
        # mid-profile 'p' press lands within ~step_wait seconds.
        client.tap(px, py, hold_ms=args.tap_hold_ms)
        time.sleep(args.step_wait)
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

        wr, sc, gm, _, _, last_img = find_target_in_strip(
            client, args.target,
            max_swipes=args.max_strip_swipes,
            swipe_scale=args.strip_swipe_scale,
            swipe_duration_ms=args.strip_swipe_duration_ms,
            wait_after_swipe=args.step_wait,
        )
        _check_pause_or_raise()

        if args.save_screenshots:
            cv2.imwrite(str(data_dir / f"run_rank_{rank:03d}.png"), last_img)
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
    if not args.no_rank_check:
        args.no_rank_check = True

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
                            wr, sc, gm, player_name = scrape_one(current_rank, slot)
                            if wr is not None:
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

                writer.write(LeaderboardRow(
                    champion=args.target,
                    rank=current_rank,
                    player_name=player_name or "",
                    score=sc,
                    games=gm,
                    winrate=wr,
                ))
                if wr is not None:
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
    print(f"with winrate parsed    : {successes}")
    print(f"CSV                    : {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
