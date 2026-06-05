"""Scrape top-N players' winrates for one champion and write to CSV.

Architecture (post-Gemini refactor):
    1. Enter the champion's leaderboard (screen 1 -> screen 2).
    2. Take a screenshot. Send to Gemini -> [{rank, player_name, score}, ...].
    3. For each new (player_name, score) pair we haven't seen, tap into their
       profile, OCR the Aatrox winrate on screen 5, tap back. Record the row.
    4. Scroll screen 2 forward one page; repeat.
    5. Stop when target_n unique players collected, or several consecutive
       page scrolls return zero new players (bottom of leaderboard reached).

Wild Rift's periodic list reset is now harmless — when the list snaps back to
ranks 1..5, Gemini reports them, we see them in the seen-set, and skip
straight to the next scroll without scraping duplicates.

Prereq:
    - GEMINI_API_KEY env var set (see src/gemini_ocr.py)
    - In MuMu, on screen 1 (CHAMPION tab) with target champion at the mapped
      row position (coords/screen_1.json).

Run:
    python -m src.scrape_champion --target Aatrox --n 20 --save-screenshots
"""
from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path

import cv2

from .adb_client import ADBClient, ADBError
from .config import ROWS_PER_PAGE, load_screen_points
from .gemini_ocr import read_leaderboard
from .storage import CSVWriter, LeaderboardRow
from .strip import find_target_in_strip


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", default="Aatrox", help="Champion to look up on each player's profile")
    parser.add_argument("--n", type=int, default=20, help="Number of unique players to scrape")
    parser.add_argument("--device", default="127.0.0.1:7555")
    parser.add_argument("--no-connect", action="store_true")
    parser.add_argument("--step-wait", type=float, default=2.0, help="Seconds to wait after each tap")
    parser.add_argument("--output", type=Path, default=Path("data/winrates.csv"), help="CSV file to append to")
    parser.add_argument("--save-screenshots", action="store_true", help="Save the screen 5 screenshot for each rank")
    parser.add_argument("--swipe-scale", type=float, default=0.8, help="Multiplier on the per-page swipe distance")
    parser.add_argument("--swipe-duration-ms", type=int, default=1500, help="Page-scroll swipe duration")
    parser.add_argument("--scroll-wait", type=float, default=1.5, help="Extra seconds to wait after a scroll for the list to settle")
    parser.add_argument("--max-strip-swipes", type=int, default=3, help="If target champion isn't in the first 4 tiles on screen 5, swipe the strip up to N times")
    parser.add_argument("--strip-swipe-scale", type=float, default=0.7)
    parser.add_argument("--strip-swipe-duration-ms", type=int, default=800)
    parser.add_argument("--gemini-model", default="gemini-2.5-flash-lite", help="Gemini model for leaderboard OCR")
    parser.add_argument("--stop-after-empty-pages", type=int, default=3, help="Stop after this many consecutive scrolls return no new players")
    parser.add_argument("--max-pages", type=int, default=80, help="Hard cap on screen-2 scrolls (safety against infinite loops)")
    args = parser.parse_args()

    try:
        s1 = load_screen_points(1)
        s2 = load_screen_points(2)
        s3 = load_screen_points(3)
        s4 = load_screen_points(4)
        s5 = load_screen_points(5)
    except FileNotFoundError as e:
        print(f"error: missing coord file: {e}", file=sys.stderr)
        return 1

    if "aatrox" not in s2:
        print("error: screen_2.json needs 'aatrox' (rank 1 tap)", file=sys.stderr)
        return 1
    rank_1_x, rank_1_y = s2["aatrox"]

    if "player_row_5" in s2:
        _, deep_y = s2["player_row_5"]
        row_pitch = (deep_y - rank_1_y) / 4
        pitch_source = "rank 1 -> rank 5"
    elif "player_row_3" in s2:
        _, deep_y = s2["player_row_3"]
        row_pitch = (deep_y - rank_1_y) / 2
        pitch_source = "rank 1 -> rank 3"
    elif "player_row_2" in s2:
        _, deep_y = s2["player_row_2"]
        row_pitch = deep_y - rank_1_y
        pitch_source = "rank 1 -> rank 2"
    else:
        print("error: screen_2.json needs at least one of 'player_row_2/3/5'", file=sys.stderr)
        return 1
    if row_pitch <= 0:
        print(f"error: invalid row pitch {row_pitch}", file=sys.stderr)
        return 1

    if "back" not in s5:
        print("error: screen_5.json needs a 'back' point", file=sys.stderr)
        return 1

    champ_tap = s1["aatrox"]
    view_profile_tap = s3["aatrox"]
    champ_and_lane_tap = s4["aatrox"]
    back_tap = s5["back"]

    def slot_tap(slot: int) -> tuple[int, int]:
        return (rank_1_x, int(round(rank_1_y + slot * row_pitch)))

    print(f"target champion : {args.target}")
    print(f"target N        : {args.n} unique players")
    print(f"row pitch       : {row_pitch:.1f}px  ({pitch_source})")
    print(f"gemini model    : {args.gemini_model}")
    print(f"CSV output      : {args.output}")
    print()

    client = ADBClient(device=args.device)
    if not args.no_connect:
        try:
            client.connect()
        except ADBError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1

    writer = CSVWriter(args.output)
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)

    # screen 1 -> screen 2 (once per champion)
    print(f"enter champion: tap ({champ_tap[0]}, {champ_tap[1]})")
    client.tap(*champ_tap)
    time.sleep(args.step_wait)

    def scroll_to_next_page() -> None:
        start_y = int(round(rank_1_y + (ROWS_PER_PAGE - 1) * row_pitch))
        distance_px = int(round(ROWS_PER_PAGE * row_pitch * args.swipe_scale))
        end_y = max(50, start_y - distance_px)
        print(f"  swipe scroll      -> ({rank_1_x}, {start_y}) -> ({rank_1_x}, {end_y})")
        client.swipe(rank_1_x, start_y, rank_1_x, end_y, args.swipe_duration_ms)
        time.sleep(args.step_wait + args.scroll_wait)

    def scrape_one_player(rank: int, player_name: str, score: int | None, slot: int) -> float | None:
        """Tap chain into the player's profile, OCR winrate, tap back."""
        px, py = slot_tap(slot)
        print(f"  rank {rank} ({player_name}, score={score}) at slot {slot}: tap ({px}, {py})")
        client.tap(px, py)
        time.sleep(args.step_wait)

        client.tap(*view_profile_tap)
        time.sleep(args.step_wait)

        if args.save_screenshots:
            cv2.imwrite(str(data_dir / f"run_rank_{rank:03d}_pre_cnl.png"), client.screenshot())
        # Double-tap CHAMPION AND LANE — first tap can miss during transition
        client.tap(*champ_and_lane_tap)
        time.sleep(0.4)
        client.tap(*champ_and_lane_tap)
        time.sleep(args.step_wait)

        target_wr, found, swipes_done, img = find_target_in_strip(
            client,
            args.target,
            max_swipes=args.max_strip_swipes,
            swipe_scale=args.strip_swipe_scale,
            swipe_duration_ms=args.strip_swipe_duration_ms,
        )
        if args.save_screenshots:
            cv2.imwrite(str(data_dir / f"run_rank_{rank:03d}.png"), img)

        vis = ", ".join(found.keys()) if found else "(none)"
        swipe_note = f" (after {swipes_done} swipe{'s' if swipes_done != 1 else ''})" if swipes_done else ""
        print(f"    strip OCR : {vis}{swipe_note}")
        print(f"    {args.target} winrate : {target_wr}")

        client.tap(*back_tap)
        time.sleep(args.step_wait)
        return target_wr

    # Dedup by score (int) alone. Gemini's Chinese-character recognition is
    # not consistent across calls — the same player can come back as
    # "討厭它Akaza" one iteration and "對厭亡Akaza" the next, breaking name-
    # based dedup. Scores are precise integers and effectively unique per
    # player on a champion leaderboard, so they're the stable key.
    seen: set[int] = set()
    successes = 0
    consecutive_no_progress = 0  # iterations in a row with no new scrape
    iteration = 0

    # Each iteration: re-read leaderboard, find first new player on screen,
    # scrape it. We do NOT batch a whole page — Wild Rift can reset the list
    # to ranks 1..5 between any two profile views, which would invalidate any
    # cached layout. Re-reading every loop keeps us honest at the cost of one
    # extra Gemini call per scrape (~$0.00021 = a fraction of a cent).
    while len(seen) < args.n and iteration < args.max_pages:
        iteration += 1
        print(f"\n=== iter {iteration}  (collected {len(seen)}/{args.n}) ===")

        img = client.screenshot()
        if args.save_screenshots:
            cv2.imwrite(str(data_dir / f"run_i{iteration:03d}_screen2.png"), img)
        try:
            rows = read_leaderboard(img, model=args.gemini_model)
        except RuntimeError as e:
            print(f"  gemini error: {e}; scrolling forward")
            scroll_to_next_page()
            consecutive_no_progress += 1
            if consecutive_no_progress >= args.stop_after_empty_pages:
                print(f"  stopping (consecutive no-progress)")
                break
            continue

        if not rows:
            print(f"  gemini returned 0 rows; scrolling forward")
            scroll_to_next_page()
            consecutive_no_progress += 1
            if consecutive_no_progress >= args.stop_after_empty_pages:
                print(f"  stopping (consecutive no-progress)")
                break
            continue

        rows.sort(key=lambda r: r.rank)
        min_visible_rank = rows[0].rank
        rank_summary = ", ".join(f"r{r.rank}={r.player_name}" for r in rows)

        # Find the first new player whose slot is in range.
        # Skip rows where Gemini couldn't parse a score — re-read next iter.
        next_row = None
        next_slot = -1
        for row in rows:
            if row.score is None:
                continue
            if row.score in seen:
                continue
            if row.rank > args.n:
                seen.add(row.score)  # mark past-target so we don't waste time
                continue
            slot = row.rank - min_visible_rank
            if 0 <= slot < ROWS_PER_PAGE:
                next_row = row
                next_slot = slot
                break

        if next_row is None:
            print(f"  visible: {rank_summary} — all already scraped; scrolling forward")
            consecutive_no_progress += 1
            if consecutive_no_progress >= args.stop_after_empty_pages:
                print(f"  stopping (consecutive no-progress = {consecutive_no_progress})")
                break
            scroll_to_next_page()
            continue

        print(f"  visible: {rank_summary}")

        try:
            winrate = scrape_one_player(
                next_row.rank, next_row.player_name, next_row.score, next_slot,
            )
        except Exception:
            print(f"  exception scraping rank {next_row.rank}:")
            traceback.print_exc()
            print("  continuing")
            continue

        seen.add(next_row.score)  # next_row.score is guaranteed non-None here
        writer.write(LeaderboardRow(
            champion=args.target,
            rank=next_row.rank,
            player_name=next_row.player_name,
            score=next_row.score,
            winrate=winrate,
        ))
        if winrate is not None:
            successes += 1
        consecutive_no_progress = 0

    print(f"\ndone. {successes} winrates parsed out of {len(seen)} unique players seen. CSV -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
