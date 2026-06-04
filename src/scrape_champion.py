"""Scrape top-N players' winrates for one champion and write to CSV.

Prereq: in MuMu, you are on screen 1 (CHAMPION tab of the Leaderboard) with
your target champion visible in the row that `coords/screen_1.json`'s tap
point hits. Ranks 1..N must be visible on screen 2 without scrolling
(true for N <= ~6 on a 1600x900 device).

Pipeline per rank:
    tap player row -> screen 3 (popup)
    tap view-profile -> screen 4 (profile OVERVIEW)
    tap CHAMPION AND LANE -> screen 5
    OCR the champion-tile strip, look up target winrate
    tap back chevron -> screen 2 (Aatrox leaderboard)

Run:
    python -m src.scrape_champion --target Aatrox --n 5
    python -m src.scrape_champion --target Aatrox --n 5 --save-screenshots
"""
from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path

import cv2

from .adb_client import ADBClient, ADBError, jittered_sleep
from .config import (
    ROWS_PER_PAGE,
    SCREEN_2_BADGE_X_RANGE,
    SCREEN_2_SAFE_Y_BOTTOM,
    SCREEN_2_SAFE_Y_TOP,
    SCREEN_5_OCR_REGION,
    load_screen_points,
)
from .ocr import find_champion_winrates, read_all_visible_ranks
from .storage import CSVWriter, LeaderboardRow
from .strip import find_target_in_strip


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", default="Aatrox", help="Champion to look up on each player's profile")
    parser.add_argument("--n", type=int, default=5, help="Number of top players to scrape (rank 1..N)")
    parser.add_argument("--device", default="127.0.0.1:7555")
    parser.add_argument("--no-connect", action="store_true")
    parser.add_argument("--step-wait", type=float, default=2.0, help="Seconds to wait after each tap")
    parser.add_argument("--output", type=Path, default=Path("data/winrates.csv"), help="CSV file to append to")
    parser.add_argument("--save-screenshots", action="store_true", help="Save the screen 5 screenshot for each rank")
    parser.add_argument("--swipe-scale", type=float, default=0.8, help="Multiplier on the per-page swipe distance (tune if scroll under/over-shoots)")
    parser.add_argument("--swipe-duration-ms", type=int, default=1500, help="Swipe gesture duration in ms (longer = more controlled, less fling)")
    parser.add_argument("--scroll-wait", type=float, default=1.5, help="Extra seconds to wait after a scroll for the list to settle")
    parser.add_argument("--max-strip-swipes", type=int, default=3, help="If target champion isn't in the first 4 tiles on screen 5, swipe the strip up to N times to find it")
    parser.add_argument("--strip-swipe-scale", type=float, default=0.7, help="Scale on screen-5 strip swipe distance")
    parser.add_argument("--strip-swipe-duration-ms", type=int, default=800, help="Screen-5 strip swipe duration")
    parser.add_argument("--max-scroll-attempts", type=int, default=4, help="Per-rank scroll budget — if OCR can't bring target rank on-screen in this many tries, skip the rank")
    parser.add_argument("--tap-jitter-px", type=int, default=8, help="Random offset (in pixels) added to each tap. Helps avoid pixel-perfect repeat behavior. Set 0 to disable.")
    parser.add_argument("--time-jitter-ms", type=int, default=200, help="Random ms added/subtracted from each step_wait. Set 0 to disable.")
    args = parser.parse_args()

    # Load all 5 screens' tap points
    try:
        s1 = load_screen_points(1)
        s2 = load_screen_points(2)
        s3 = load_screen_points(3)
        s4 = load_screen_points(4)
        s5 = load_screen_points(5)
    except FileNotFoundError as e:
        print(f"error: missing coord file: {e}", file=sys.stderr)
        return 1

    # Derive screen-2 row pitch. The 1->2 delta is larger than the
    # steady-state 2->3, 3->4, ... pitch because of header padding on row 1.
    # If the user mapped a deeper row (player_row_5 or player_row_3), use that
    # for a more accurate pitch.
    if "aatrox" not in s2:
        print("error: screen_2.json needs 'aatrox' (rank 1 tap)", file=sys.stderr)
        return 1
    rank_1_x, rank_1_y = s2["aatrox"]

    pitch_source: str
    if "player_row_5" in s2:
        _, rank_5_y = s2["player_row_5"]
        row_pitch = (rank_5_y - rank_1_y) / 4
        pitch_source = "rank 1 -> rank 5"
    elif "player_row_3" in s2:
        _, rank_3_y = s2["player_row_3"]
        row_pitch = (rank_3_y - rank_1_y) / 2
        pitch_source = "rank 1 -> rank 3"
    elif "player_row_2" in s2:
        _, rank_2_y = s2["player_row_2"]
        row_pitch = rank_2_y - rank_1_y
        pitch_source = "rank 1 -> rank 2 (may be inflated by header padding)"
    else:
        print("error: screen_2.json needs at least one of 'player_row_2', 'player_row_3', 'player_row_5'", file=sys.stderr)
        return 1
    if row_pitch <= 0:
        print(f"error: invalid row pitch {row_pitch}", file=sys.stderr)
        return 1

    if "back" not in s5:
        print("error: screen_5.json needs a 'back' point (top-left chevron)", file=sys.stderr)
        return 1

    champ_tap = s1["aatrox"]              # screen 1 -> screen 2
    view_profile_tap = s3["aatrox"]       # screen 3 -> screen 4
    champ_and_lane_tap = s4["aatrox"]     # screen 4 -> screen 5
    back_tap = s5["back"]                 # screen 5 -> screen 2

    def slot_tap(slot: int) -> tuple[int, int]:
        """Tap position for the Nth visible row (slot 0 = topmost)."""
        return (rank_1_x, int(round(rank_1_y + slot * row_pitch)))

    print(f"target champion : {args.target}")
    print(f"ranks to scrape : 1..{args.n}")
    print(f"row pitch       : {row_pitch:.1f}px  ({pitch_source})")
    print(f"rows per page   : {ROWS_PER_PAGE}")
    print(f"slot tap ys     : {[slot_tap(s)[1] for s in range(ROWS_PER_PAGE)]}")
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
    client.tap(*champ_tap, jitter_px=args.tap_jitter_px)
    jittered_sleep(args.step_wait, args.time_jitter_ms)

    def do_swipe(rows: float) -> None:
        """Swipe up by `rows` row-pitches. Negative `rows` = swipe DOWN
        (scroll back to earlier ranks)."""
        if rows >= 0:
            start_y = int(round(rank_1_y + (ROWS_PER_PAGE - 1) * row_pitch))
            end_y = max(50, int(round(start_y - rows * row_pitch * args.swipe_scale)))
        else:
            start_y = rank_1_y
            end_y = min(840, int(round(start_y + abs(rows) * row_pitch * args.swipe_scale)))
        client.swipe(rank_1_x, start_y, rank_1_x, end_y, args.swipe_duration_ms)
        jittered_sleep(args.step_wait + args.scroll_wait, args.time_jitter_ms)

    def scroll_to_next_page() -> None:
        """Swipe up so the next ROWS_PER_PAGE ranks come into view."""
        start_y = int(round(rank_1_y + (ROWS_PER_PAGE - 1) * row_pitch))
        distance_px = int(round(ROWS_PER_PAGE * row_pitch * args.swipe_scale))
        end_y = max(50, start_y - distance_px)
        print(f"  swipe scroll      -> ({rank_1_x}, {start_y}) -> ({rank_1_x}, {end_y})  [{args.swipe_duration_ms}ms]")
        client.swipe(rank_1_x, start_y, rank_1_x, end_y, args.swipe_duration_ms)
        jittered_sleep(args.step_wait + args.scroll_wait, args.time_jitter_ms)

    def find_rank_entry(
        visible: dict[int, tuple[int, int, int]], target: int
    ) -> tuple[int, int, int, int] | None:
        """Return (slot, rank, y_top, y_bot) for the visible entry matching
        target. If target isn't in the visible set, try to *infer* its slot
        from neighbors assuming consecutive ranks; in that case y_top/y_bot
        come from the inferred slot's expected position."""
        if not visible:
            return None
        for slot, (rank, yt, yb) in visible.items():
            if rank == target:
                return (slot, rank, yt, yb)
        # Infer from lowest detected slot
        ref_slot = min(visible.keys())
        ref_rank, _, _ = visible[ref_slot]
        inferred_slot = ref_slot + (target - ref_rank)
        if 0 <= inferred_slot < ROWS_PER_PAGE:
            # Estimate y from slot position; mark as inferred
            est_cy = int(round(rank_1_y + inferred_slot * row_pitch))
            return (inferred_slot, target, est_cy - 35, est_cy + 35)
        return None

    def locate_target_rank(target: int, max_scrolls: int = 4) -> int | None:
        """Scroll/swipe screen 2 until `target` is visible AND fully in the
        safe y-zone [SAFE_Y_TOP, SAFE_Y_BOTTOM]. Returns the slot index where
        target lives, or None if we couldn't bring it fully on-screen within
        max_scrolls attempts.

        Two corrections happen here:
          - Off-screen: target rank isn't visible at all → page scroll
          - Partial visibility: target's badge top<SAFE_Y_TOP (cut off at top,
            scroll back) or badge bottom>SAFE_Y_BOTTOM (cut off at bottom,
            scroll forward) → micro-swipe by the exact pixel deficit.
        """
        for attempt in range(max_scrolls + 1):
            img = client.screenshot()
            visible = read_all_visible_ranks(img, rank_1_y, row_pitch, SCREEN_2_BADGE_X_RANGE)
            entry = find_rank_entry(visible, target)

            if entry is not None:
                slot, rank, y_top, y_bot = entry
                vis_str = ", ".join(f"s{s}=r{v[0]}(y={v[1]}..{v[2]})" for s, v in sorted(visible.items()))
                # Safe-zone check
                if y_top >= SCREEN_2_SAFE_Y_TOP and y_bot <= SCREEN_2_SAFE_Y_BOTTOM:
                    print(f"  visible: {{{vis_str}}}  -> rank {target} at slot {slot}, y=[{y_top},{y_bot}] OK")
                    return slot
                if attempt >= max_scrolls:
                    print(f"  rank {target} y=[{y_top},{y_bot}] partial after {attempt} scrolls; tapping anyway")
                    return slot
                # Partial visibility — micro-adjust
                if y_top < SCREEN_2_SAFE_Y_TOP:
                    deficit_px = SCREEN_2_SAFE_Y_TOP - y_top + 10
                    rows = deficit_px / row_pitch
                    print(f"  rank {target} y_top={y_top} < {SCREEN_2_SAFE_Y_TOP}; swipe back {rows:.2f}r")
                    do_swipe(-rows)
                else:  # y_bot > SCREEN_2_SAFE_Y_BOTTOM
                    deficit_px = y_bot - SCREEN_2_SAFE_Y_BOTTOM + 10
                    rows = deficit_px / row_pitch
                    print(f"  rank {target} y_bot={y_bot} > {SCREEN_2_SAFE_Y_BOTTOM}; swipe forward {rows:.2f}r")
                    do_swipe(rows)
                continue

            # Target not visible at all
            if attempt >= max_scrolls:
                print(f"  could not locate rank {target} after {attempt} scroll(s); visible={list(visible.values())}")
                return None
            if not visible:
                if target == 1:
                    print(f"  no badges read; assuming initial state (rank 1 = slot 0 gold trophy)")
                    return 0
                print(f"  no badges read; scrolling forward")
                scroll_to_next_page()
                continue
            visible_ranks = [v[0] for v in visible.values()]
            min_v = min(visible_ranks)
            max_v = max(visible_ranks)
            if target < min_v:
                rows_back = min_v - target
                print(f"  target {target} below visible (min={min_v}); swipe back ~{rows_back}r")
                do_swipe(-rows_back)
            else:  # target > max_v
                rows_fwd = target - max_v
                print(f"  target {target} above visible (max={max_v}); swipe forward ~{rows_fwd}r")
                if rows_fwd >= ROWS_PER_PAGE:
                    scroll_to_next_page()
                else:
                    do_swipe(rows_fwd)
        return None

    successes = 0
    profiles_since_reset = 0

    for rank in range(1, args.n + 1):
        print(f"\nrank {rank}:")
        slot = locate_target_rank(rank, max_scrolls=args.max_scroll_attempts)
        if slot is None:
            print(f"  skipping rank {rank} (not found)")
            writer.write(LeaderboardRow(
                champion=args.target,
                rank=rank,
                player_name="",
                winrate=None,
            ))
            continue

        try:
            px, py = slot_tap(slot)
            print(f"  tap player row    -> ({px}, {py})  [slot {slot}]")
            client.tap(px, py, jitter_px=args.tap_jitter_px)
            jittered_sleep(args.step_wait, args.time_jitter_ms)

            print(f"  tap view-profile  -> ({view_profile_tap[0]}, {view_profile_tap[1]})")
            client.tap(*view_profile_tap, jitter_px=args.tap_jitter_px)
            jittered_sleep(args.step_wait, args.time_jitter_ms)

            print(f"  tap champ-and-lane-> ({champ_and_lane_tap[0]}, {champ_and_lane_tap[1]})")
            client.tap(*champ_and_lane_tap, jitter_px=args.tap_jitter_px)
            jittered_sleep(args.step_wait, args.time_jitter_ms)

            target_wr, found, swipes_done, img = find_target_in_strip(
                client,
                args.target,
                max_swipes=args.max_strip_swipes,
                swipe_scale=args.strip_swipe_scale,
                swipe_duration_ms=args.strip_swipe_duration_ms,
            )
            if args.save_screenshots:
                path = data_dir / f"run_rank_{rank:03d}.png"
                cv2.imwrite(str(path), img)

            visible = ", ".join(found.keys()) if found else "(none)"
            swipe_note = f" (after {swipes_done} swipe{'s' if swipes_done != 1 else ''})" if swipes_done else ""
            print(f"  OCR visible       : {visible}{swipe_note}")
            print(f"  {args.target} winrate : {target_wr}")

            writer.write(LeaderboardRow(
                champion=args.target,
                rank=rank,
                player_name="",
                winrate=target_wr,
            ))
            if target_wr is not None:
                successes += 1

            print(f"  tap back          -> ({back_tap[0]}, {back_tap[1]})")
            client.tap(*back_tap, jitter_px=args.tap_jitter_px)
            jittered_sleep(args.step_wait, args.time_jitter_ms)

            # No reset bookkeeping needed — next iteration OCRs to find the
            # next target rank's slot, automatically handling Wild Rift's
            # reset-to-page-1 behavior.
        except Exception:
            print(f"\nrank {rank} crashed:")
            traceback.print_exc()
            print("aborting loop")
            return 1

    print(f"\ndone. {successes}/{args.n} winrates parsed. CSV -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
