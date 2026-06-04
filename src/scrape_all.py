"""Multi-champion scraper.

Iterates the first M champions in screen 1's order, scrapes top N players for
each, writes everything to CSV.

Prereq: in MuMu, you are on screen 1 (CHAMPION tab of the Leaderboard) with
the champion list at the top (rank 1 of champions visible).

Per champion:
    1. Tap the champion's row on screen 1   -> screen 2
    2. Screenshot screen 2, OCR the bottom-left champion-name label so we
       know which champion we're scraping
    3. Run the per-player loop (taps + view profile + champ&lane + OCR + back)
    4. Tap screen 2's back chevron          -> back to screen 1
    5. Move to next champion row

Coord requirements (in addition to those already used by scrape_champion):
    screen_1.json must contain:
        aatrox              - row 1 (rank 1 champion) tap point
        champion_row_2      - row 2 tap point (to derive screen-1 pitch)
    screen_2.json must contain:
        back                - top-left back chevron (returns to screen 1)
    (Optional)
        screen_1.json can also have champion_row_5 for a more accurate pitch.

Run:
    python -m src.scrape_all --champions 5 --players 5
    python -m src.scrape_all --champions 3 --players 10 --save-screenshots
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
    SCREEN_2_CHAMP_NAME_REGION,
    SCREEN_5_OCR_REGION,
    load_screen_points,
)
from .ocr import find_champion_winrates, read_champion_name
from .storage import CSVWriter, LeaderboardRow
from .strip import find_target_in_strip


def derive_pitch(points: dict[str, tuple[int, int]], base_key: str) -> tuple[int, int, float, str]:
    """Return (base_x, base_y, pitch, source_description) using the widest
    explicitly-mapped span. Falls back to base_key + 'row_2' if no deeper row
    is mapped."""
    if base_key not in points:
        raise ValueError(f"missing '{base_key}' in points")
    base_x, base_y = points[base_key]
    for span_key, divisor, label in (
        ("champion_row_5", 4, "row 1 -> row 5"),
        ("champion_row_3", 2, "row 1 -> row 3"),
        ("champion_row_2", 1, "row 1 -> row 2"),
    ):
        if span_key in points:
            _, deep_y = points[span_key]
            return base_x, base_y, (deep_y - base_y) / divisor, label
    raise ValueError("need at least 'champion_row_2' (preferably 'champion_row_5')")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--champions", type=int, default=5, help="How many champions (rows 1..M) to scrape")
    parser.add_argument("--players", type=int, default=5, help="How many players per champion (ranks 1..N)")
    parser.add_argument("--device", default="127.0.0.1:7555")
    parser.add_argument("--no-connect", action="store_true")
    parser.add_argument("--step-wait", type=float, default=2.0)
    parser.add_argument("--scroll-wait", type=float, default=1.5)
    parser.add_argument("--swipe-scale", type=float, default=0.8)
    parser.add_argument("--swipe-duration-ms", type=int, default=1500)
    parser.add_argument("--reset-every", type=int, default=6, help="Wild Rift resets the screen-2 scroll after this many profile views")
    parser.add_argument("--max-strip-swipes", type=int, default=3)
    parser.add_argument("--strip-swipe-scale", type=float, default=0.7)
    parser.add_argument("--strip-swipe-duration-ms", type=int, default=800)
    parser.add_argument("--tap-jitter-px", type=int, default=8)
    parser.add_argument("--time-jitter-ms", type=int, default=200)
    parser.add_argument("--output", type=Path, default=Path("data/winrates.csv"))
    parser.add_argument("--save-screenshots", action="store_true")
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

    # Screen 1 pitch (champion rows). Prefer aatrox + champion_row_2 (or _5).
    try:
        champ_x, champ_1_y, champ_pitch, champ_pitch_src = derive_pitch(s1, "aatrox")
    except ValueError as e:
        print(f"error: screen 1: {e}", file=sys.stderr)
        return 1

    # Screen 2 player pitch — reuse the same approach with player_row_* keys.
    if "aatrox" not in s2:
        print("error: screen_2.json needs 'aatrox' (rank 1 tap)", file=sys.stderr)
        return 1
    rank_1_x, rank_1_y = s2["aatrox"]
    if "player_row_5" in s2:
        _, deep_y = s2["player_row_5"]
        row_pitch = (deep_y - rank_1_y) / 4
        row_pitch_src = "rank 1 -> rank 5"
    elif "player_row_3" in s2:
        _, deep_y = s2["player_row_3"]
        row_pitch = (deep_y - rank_1_y) / 2
        row_pitch_src = "rank 1 -> rank 3"
    elif "player_row_2" in s2:
        _, deep_y = s2["player_row_2"]
        row_pitch = deep_y - rank_1_y
        row_pitch_src = "rank 1 -> rank 2"
    else:
        print("error: screen_2.json needs at least 'player_row_2'", file=sys.stderr)
        return 1

    if "back" not in s2:
        print("error: screen_2.json needs 'back' (top-left chevron)", file=sys.stderr)
        return 1
    if "back" not in s5:
        print("error: screen_5.json needs 'back'", file=sys.stderr)
        return 1

    s2_back = s2["back"]
    view_profile_tap = s3["aatrox"]
    champ_and_lane_tap = s4["aatrox"]
    s5_back = s5["back"]

    def champ_tap(slot: int) -> tuple[int, int]:
        return (champ_x, int(round(champ_1_y + slot * champ_pitch)))

    def player_slot_tap(slot: int) -> tuple[int, int]:
        return (rank_1_x, int(round(rank_1_y + slot * row_pitch)))

    print(f"champions to scrape : {args.champions}")
    print(f"players per champion: {args.players}")
    print(f"screen 1 pitch      : {champ_pitch:.1f}px  ({champ_pitch_src})")
    print(f"champion tap ys     : {[champ_tap(s)[1] for s in range(min(args.champions, ROWS_PER_PAGE))]}")
    print(f"screen 2 pitch      : {row_pitch:.1f}px  ({row_pitch_src})")
    print(f"player slot tap ys  : {[player_slot_tap(s)[1] for s in range(ROWS_PER_PAGE)]}")
    print(f"CSV output          : {args.output}")
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

    def screen2_scroll() -> None:
        start_y = int(round(rank_1_y + (ROWS_PER_PAGE - 1) * row_pitch))
        distance_px = int(round(ROWS_PER_PAGE * row_pitch * args.swipe_scale))
        end_y = max(50, start_y - distance_px)
        print(f"    swipe -> ({rank_1_x}, {start_y}) -> ({rank_1_x}, {end_y})  [{args.swipe_duration_ms}ms]")
        client.swipe(rank_1_x, start_y, rank_1_x, end_y, args.swipe_duration_ms)
        jittered_sleep(args.step_wait + args.scroll_wait, args.time_jitter_ms)

    # NOTE: this version assumes args.champions <= ROWS_PER_PAGE. Scrolling
    # screen 1 (for more champions than fit on one screen) is not implemented
    # yet — same pattern as screen 2, but we don't have a "champion_row_5"
    # check below; safe with --champions <= 5.
    if args.champions > ROWS_PER_PAGE:
        print(f"warning: screen 1 scrolling not implemented; capping --champions at {ROWS_PER_PAGE}")
        args.champions = ROWS_PER_PAGE

    total_success = 0
    total_attempts = 0

    for champ_slot in range(args.champions):
        cx, cy = champ_tap(champ_slot)
        print(f"\n========== champion slot {champ_slot + 1}: tap ({cx}, {cy}) ==========")
        client.tap(cx, cy, jitter_px=args.tap_jitter_px)
        jittered_sleep(args.step_wait, args.time_jitter_ms)

        # Identify which champion we just entered by OCRing the label
        screen2_img = client.screenshot()
        if args.save_screenshots:
            cv2.imwrite(str(data_dir / f"run_champ_{champ_slot + 1}_screen2.png"), screen2_img)

        champ_name = read_champion_name(screen2_img, SCREEN_2_CHAMP_NAME_REGION)
        if champ_name is None:
            print("  WARNING: could not OCR champion name; using slot index")
            champ_name = f"slot_{champ_slot + 1}"
        print(f"  -> identified as: {champ_name}")

        # Player loop (top N for this champion) — rank-driven with auto re-scroll
        current_page = 0
        profiles_since_reset = 0
        for rank in range(1, args.players + 1):
            target_page = (rank - 1) // ROWS_PER_PAGE
            while current_page < target_page:
                print(f"  --- scrolling screen 2 to page {current_page + 2} ---")
                screen2_scroll()
                current_page += 1
                if args.save_screenshots:
                    cv2.imwrite(str(data_dir / f"run_{champ_name}_p{current_page + 1}.png"), client.screenshot())

            total_attempts += 1
            try:
                slot = (rank - 1) % ROWS_PER_PAGE
                px, py = player_slot_tap(slot)
                print(f"  rank {rank} (page {current_page + 1}, slot {slot}): tap ({px}, {py})")
                client.tap(px, py, jitter_px=args.tap_jitter_px)
                jittered_sleep(args.step_wait, args.time_jitter_ms)
                client.tap(*view_profile_tap, jitter_px=args.tap_jitter_px)
                jittered_sleep(args.step_wait, args.time_jitter_ms)
                client.tap(*champ_and_lane_tap, jitter_px=args.tap_jitter_px)
                jittered_sleep(args.step_wait, args.time_jitter_ms)

                target_wr, found, swipes_done, img = find_target_in_strip(
                    client,
                    champ_name,
                    max_swipes=args.max_strip_swipes,
                    swipe_scale=args.strip_swipe_scale,
                    swipe_duration_ms=args.strip_swipe_duration_ms,
                )
                if args.save_screenshots:
                    cv2.imwrite(str(data_dir / f"run_{champ_name}_rank_{rank:03d}.png"), img)

                visible = ", ".join(found.keys()) if found else "(none)"
                swipe_note = f" (after {swipes_done} swipe{'s' if swipes_done != 1 else ''})" if swipes_done else ""
                print(f"    OCR visible : {visible}{swipe_note}")
                print(f"    {champ_name} winrate : {target_wr}")

                writer.write(LeaderboardRow(
                    champion=champ_name,
                    rank=rank,
                    player_name="",
                    winrate=target_wr,
                ))
                if target_wr is not None:
                    total_success += 1

                client.tap(*s5_back, jitter_px=args.tap_jitter_px)
                jittered_sleep(args.step_wait, args.time_jitter_ms)

                profiles_since_reset += 1
                if profiles_since_reset >= args.reset_every:
                    print(f"    [list reset expected — back to page 1]")
                    current_page = 0
                    profiles_since_reset = 0
            except Exception:
                print(f"\n  rank {rank} crashed:")
                traceback.print_exc()
                print("  skipping rest of this champion")
                break

        # Back to screen 1 for the next champion
        print(f"  tap screen 2 back -> ({s2_back[0]}, {s2_back[1]})")
        client.tap(*s2_back, jitter_px=args.tap_jitter_px)
        jittered_sleep(args.step_wait, args.time_jitter_ms)

    print(f"\ndone. {total_success}/{total_attempts} winrates parsed across {args.champions} champion(s). CSV -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
