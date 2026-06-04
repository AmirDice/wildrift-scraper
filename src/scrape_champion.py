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
    parser.add_argument("--reset-every", type=int, default=6, help="Wild Rift resets the scroll position after this many profile views; bot tracks this and re-scrolls accordingly")
    parser.add_argument("--max-align-adjustments", type=int, default=3, help="Max micro-swipes to align the page-top rank into the safe y-zone after a page scroll")
    parser.add_argument("--no-learn-alignment", action="store_true", help="Disable caching of the first alignment correction; re-OCR on every page boundary")
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

    # Cached correction (in row pitches) learned during the first successful
    # alignment. On subsequent page scrolls we apply this directly instead of
    # re-OCR'ing. None until learned.
    learned: dict[str, float | None] = {"correction_rows": None}

    def align_slot_0_to(target_rank: int) -> bool:
        """After a page scroll, ensure `target_rank`'s badge sits at slot 0
        with bbox_top close to SCREEN_2_SAFE_Y_TOP. Micro-swipes by the exact
        pixel deficit to push it into place. Returns True if aligned, False
        if max attempts exhausted.

        Tracks the cumulative correction applied across attempts; on first
        successful alignment, stores that into `learned` so subsequent page
        scrolls can apply the same correction directly without OCR.

        Only run after a fresh page scroll — never per-rank.
        """
        # Acceptable range for the top of slot 0's digit bbox
        SLOT_0_TOP_LO = SCREEN_2_SAFE_Y_TOP - 5    # 165
        SLOT_0_TOP_HI = SCREEN_2_SAFE_Y_TOP + 25   # 195

        accumulated_correction = 0.0

        for attempt in range(args.max_align_adjustments + 1):
            img = client.screenshot()
            visible = read_all_visible_ranks(img, rank_1_y, row_pitch, SCREEN_2_BADGE_X_RANGE)

            # Find target's actual y position
            actual: tuple[int, int, int] | None = None  # (slot, y_top, y_bot)
            for slot, (rank, yt, yb) in visible.items():
                if rank == target_rank:
                    actual = (slot, yt, yb)
                    break
            if actual is None:
                # Infer position from a visible neighbor (assume consecutive ranks)
                if not visible:
                    print(f"  align: no OCR; assuming OK")
                    return True
                ref_slot = min(visible.keys())
                ref_rank, ref_yt, _ = visible[ref_slot]
                inferred_slot = ref_slot + (target_rank - ref_rank)
                if 0 <= inferred_slot < ROWS_PER_PAGE:
                    est_yt = ref_yt + int(round((inferred_slot - ref_slot) * row_pitch))
                    actual = (inferred_slot, est_yt, est_yt + 35)
                else:
                    print(f"  align[{attempt}]: target rank {target_rank} off-screen; visible={[v[0] for v in visible.values()]}")
                    if attempt >= args.max_align_adjustments:
                        return False
                    # Try a coarse page swipe in the right direction
                    visible_ranks_only = [v[0] for v in visible.values()]
                    if target_rank > max(visible_ranks_only):
                        scroll_to_next_page()
                    else:
                        do_swipe(-(min(visible_ranks_only) - target_rank))
                    continue

            slot, y_top, y_bot = actual
            vis_str = ", ".join(f"s{s}=r{v[0]}(y={v[1]})" for s, v in sorted(visible.items()))
            if slot == 0 and SLOT_0_TOP_LO <= y_top <= SLOT_0_TOP_HI:
                print(f"  align[{attempt}]: visible={{{vis_str}}}  -> rank {target_rank} at slot 0, y_top={y_top} OK")
                # Persist what we learned (only on first successful calibration)
                if not args.no_learn_alignment and learned["correction_rows"] is None:
                    learned["correction_rows"] = accumulated_correction
                    print(f"  [calibration learned: {accumulated_correction:+.3f}r post-scroll correction — will skip OCR alignment on subsequent pages]")
                return True

            if attempt >= args.max_align_adjustments:
                print(f"  align: stopped after {attempt} adjustments (slot {slot}, y_top={y_top}); tapping anyway")
                return False

            # Compute pixel deficit and swipe to correct
            target_y_top = (SLOT_0_TOP_LO + SLOT_0_TOP_HI) // 2  # aim for 180
            actual_y_top_at_slot_0 = y_top - int(round(slot * row_pitch))
            deficit_px = actual_y_top_at_slot_0 - target_y_top
            # deficit_px > 0  -> slot 0 currently shows something whose y_top is below 180,
            #                    meaning we undershot the page scroll. Swipe forward.
            # deficit_px < 0  -> slot 0's content is above 180, we overshot. Swipe back.
            rows = deficit_px / row_pitch
            print(f"  align[{attempt}]: visible={{{vis_str}}}  rank {target_rank} at slot {slot}, "
                  f"effective y_top@s0={actual_y_top_at_slot_0}, deficit={deficit_px:+d}px ({rows:+.2f}r)")
            do_swipe(rows)
            accumulated_correction += rows
        return False

    successes = 0
    current_page = 0  # which screen-2 page (0-indexed) is currently visible
    profiles_since_reset = 0

    for rank in range(1, args.n + 1):
        target_page = (rank - 1) // ROWS_PER_PAGE
        target_slot = (rank - 1) % ROWS_PER_PAGE
        print(f"\nrank {rank} (page {target_page + 1}, slot {target_slot}):")

        # Page-scroll if not on the right page (first time, or after reset).
        # Apply the cached correction after EACH page scroll — so the
        # post-scroll slot layout is the same whether we're targeting slot 0
        # or any other slot. Critical for handling resets that fire mid-page.
        while current_page < target_page:
            print(f"  --- scrolling from page {current_page + 1} to {current_page + 2} ---")
            scroll_to_next_page()
            current_page += 1
            cached = learned["correction_rows"]
            if cached is not None and not args.no_learn_alignment and abs(cached) > 0.03:
                print(f"  applying cached correction: {cached:+.3f}r (no OCR)")
                do_swipe(cached)

        # OCR alignment runs ONLY to learn the correction the first time —
        # only for first-rank-of-page (rank 6, 11, 16, ...) and only if we
        # don't already have a cached value.
        if target_slot == 0 and target_page > 0 and (learned["correction_rows"] is None or args.no_learn_alignment):
            align_slot_0_to(rank)

        try:
            slot = target_slot
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

            profiles_since_reset += 1
            if profiles_since_reset >= args.reset_every:
                print(f"  [Wild Rift resets list after {args.reset_every} profile views — current_page = 0]")
                current_page = 0
                profiles_since_reset = 0
        except Exception:
            print(f"\nrank {rank} crashed:")
            traceback.print_exc()
            print("aborting loop")
            return 1

    print(f"\ndone. {successes}/{args.n} winrates parsed. CSV -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
