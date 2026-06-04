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

from .adb_client import ADBClient, ADBError
from .config import SCREEN_5_OCR_REGION, load_screen_points
from .ocr import find_champion_winrates
from .storage import CSVWriter, LeaderboardRow


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", default="Aatrox", help="Champion to look up on each player's profile")
    parser.add_argument("--n", type=int, default=5, help="Number of top players to scrape (rank 1..N)")
    parser.add_argument("--device", default="127.0.0.1:7555")
    parser.add_argument("--no-connect", action="store_true")
    parser.add_argument("--step-wait", type=float, default=2.0, help="Seconds to wait after each tap")
    parser.add_argument("--output", type=Path, default=Path("data/winrates.csv"), help="CSV file to append to")
    parser.add_argument("--save-screenshots", action="store_true", help="Save the screen 5 screenshot for each rank")
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

    def player_tap(rank: int) -> tuple[int, int]:
        return (rank_1_x, int(round(rank_1_y + (rank - 1) * row_pitch)))

    print(f"target champion : {args.target}")
    print(f"ranks to scrape : 1..{args.n}")
    print(f"row pitch       : {row_pitch:.1f}px  ({pitch_source})")
    print(f"player tap ys   : {[player_tap(r)[1] for r in range(1, args.n + 1)]}")
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

    successes = 0
    for rank in range(1, args.n + 1):
        try:
            px, py = player_tap(rank)
            print(f"\nrank {rank}:")
            print(f"  tap player row    -> ({px}, {py})")
            client.tap(px, py)
            time.sleep(args.step_wait)

            print(f"  tap view-profile  -> ({view_profile_tap[0]}, {view_profile_tap[1]})")
            client.tap(*view_profile_tap)
            time.sleep(args.step_wait)

            print(f"  tap champ-and-lane-> ({champ_and_lane_tap[0]}, {champ_and_lane_tap[1]})")
            client.tap(*champ_and_lane_tap)
            time.sleep(args.step_wait)

            img = client.screenshot()
            if args.save_screenshots:
                path = data_dir / f"run_rank_{rank:03d}.png"
                cv2.imwrite(str(path), img)

            found = find_champion_winrates(img, SCREEN_5_OCR_REGION)
            target_wr = next(
                (wr for c, wr in found.items() if c.lower() == args.target.lower()),
                None,
            )
            visible = ", ".join(found.keys()) if found else "(none)"
            print(f"  OCR visible       : {visible}")
            print(f"  {args.target} winrate : {target_wr}")

            writer.write(LeaderboardRow(
                champion=args.target,
                rank=rank,
                player_name="",  # TODO: OCR from screen 2 or profile header
                winrate=target_wr,
            ))
            if target_wr is not None:
                successes += 1

            print(f"  tap back          -> ({back_tap[0]}, {back_tap[1]})")
            client.tap(*back_tap)
            time.sleep(args.step_wait)
        except Exception:
            print(f"\nrank {rank} crashed:")
            traceback.print_exc()
            print("aborting loop")
            break

    print(f"\ndone. {successes}/{args.n} winrates parsed. CSV -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
