"""Manual-scroll scraper.

You scroll Wild Rift's leaderboard yourself; the bot only does the per-player
tap chain (player row -> view profile -> CHAMPION AND LANE -> OCR -> back).
After each batch of 5 it asks you to scroll and press Enter for the next 5.

No Gemini, no auto-scroll, no reset recovery. The mastery score AND winrate
are both extracted from the screen-5 champion strip (via Tesseract); the
leaderboard "score" column isn't read at all.

Pause: press the `p` key at any time. The bot finishes the current player
tap chain, then waits for you to press Enter to resume.

Prereq: In MuMu, you are on screen 2 (the champion's leaderboard) with rank
--start-rank visible at slot 0 (the topmost row).

Run:
    python -m src.scrape_champion --target Aatrox --n 200 --start-rank 1
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
from pathlib import Path

import cv2

from .adb_client import ADBClient, ADBError
from .config import ROWS_PER_PAGE, load_screen_points
from .storage import CSVWriter, LeaderboardRow
from .strip import find_target_in_strip


# Non-blocking keyboard polling for the pause feature. Windows has msvcrt
# built in; on Unix we fall through to no-op (pause is just not available).
if os.name == "nt":
    import msvcrt

    def _key_pressed() -> str | None:
        if msvcrt.kbhit():
            ch = msvcrt.getch()
            try:
                return ch.decode("utf-8", errors="ignore").lower()
            except Exception:
                return ""
        return None

    def _drain_keys() -> None:
        while msvcrt.kbhit():
            msvcrt.getch()
else:
    def _key_pressed() -> str | None:
        return None

    def _drain_keys() -> None:
        return None


def _check_for_pause() -> bool:
    """Returns True if the user has pressed 'p' since the last check."""
    while True:
        k = _key_pressed()
        if k is None:
            return False
        if k == "p":
            return True
        # Some other key — drain and keep looking


def _handle_pause() -> None:
    print("\n=== PAUSED ===  (fix Wild Rift state, then press Enter to resume)")
    _drain_keys()
    input()
    _drain_keys()
    print("=== RESUMED ===\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", default="Aatrox", help="Champion whose winrate to look up on each player's profile")
    parser.add_argument("--n", type=int, default=20, help="Total number of ranks to scrape (starting at --start-rank)")
    parser.add_argument("--start-rank", type=int, default=1, help="First rank to scrape (must be at slot 0 of screen 2 when you press Enter)")
    parser.add_argument("--device", default="127.0.0.1:7555")
    parser.add_argument("--no-connect", action="store_true")
    parser.add_argument("--step-wait", type=float, default=2.0, help="Seconds to wait after each tap")
    parser.add_argument("--output", type=Path, default=Path("data/winrates.csv"), help="CSV file to append to")
    parser.add_argument("--save-screenshots", action="store_true", help="Save the screen 5 screenshot for each rank")
    parser.add_argument("--max-strip-swipes", type=int, default=3, help="If the target champion isn't in the first 4 visible tiles, swipe the strip up to N times")
    parser.add_argument("--strip-swipe-scale", type=float, default=0.7)
    parser.add_argument("--strip-swipe-duration-ms", type=int, default=800)
    parser.add_argument("--max-retries-per-player", type=int, default=3, help="If a tap chain fails (winrate not found), retry up to this many times before recording None and moving on")
    args = parser.parse_args()

    try:
        s2 = load_screen_points(2)
        s3 = load_screen_points(3)
        s4 = load_screen_points(4)
        s5 = load_screen_points(5)
    except FileNotFoundError as e:
        print(f"error: missing coord file: {e}", file=sys.stderr)
        return 1

    if "aatrox" not in s2:
        print("error: screen_2.json needs 'aatrox' (rank 1 tap point)", file=sys.stderr)
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
        print("error: screen_2.json needs player_row_2/3/5", file=sys.stderr)
        return 1
    if row_pitch <= 0:
        print(f"error: invalid row pitch {row_pitch}", file=sys.stderr)
        return 1
    if "back" not in s5:
        print("error: screen_5.json needs a 'back' point", file=sys.stderr)
        return 1

    view_profile_tap = s3["aatrox"]
    champ_and_lane_tap = s4["aatrox"]
    back_tap = s5["back"]

    def slot_tap_coords(slot: int) -> tuple[int, int]:
        return (rank_1_x, int(round(rank_1_y + slot * row_pitch)))

    print(f"target champion : {args.target}")
    print(f"ranks           : {args.start_rank} .. {args.start_rank + args.n - 1}  ({args.n} players)")
    print(f"row pitch       : {row_pitch:.1f}px  ({pitch_source})")
    print(f"CSV output      : {args.output}")
    print(f"pause           : press 'p' (then Enter at the prompt to resume)")
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

    def scrape_one_player(rank: int, slot: int) -> tuple[float | None, int | None]:
        """Tap chain into the slot's player profile, OCR (winrate, score), back."""
        px, py = slot_tap_coords(slot)
        print(f"  rank {rank} (slot {slot}): tap player ({px}, {py})")
        client.tap(px, py)
        time.sleep(args.step_wait)

        client.tap(*view_profile_tap)
        time.sleep(args.step_wait)

        if args.save_screenshots:
            cv2.imwrite(str(data_dir / f"run_rank_{rank:03d}_pre_cnl.png"), client.screenshot())
        # Double-tap CHAMPION AND LANE — first one can be eaten by a transition.
        client.tap(*champ_and_lane_tap)
        time.sleep(0.4)
        client.tap(*champ_and_lane_tap)
        time.sleep(args.step_wait)

        winrate, score, found, swipes_done, img = find_target_in_strip(
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
        print(f"    winrate   : {winrate}  score: {score}")

        client.tap(*back_tap)
        time.sleep(args.step_wait)
        return winrate, score

    print(f"Open MuMu, scroll the leaderboard so rank {args.start_rank} is at slot 0 (top).")
    input("Press Enter when ready to start: ")

    end_rank = args.start_rank + args.n - 1
    current_rank = args.start_rank
    successes = 0

    try:
        while current_rank <= end_rank:
            print(f"\n=== batch starting at rank {current_rank} ===")
            ranks_in_batch = 0
            for slot in range(ROWS_PER_PAGE):
                if current_rank > end_rank:
                    break

                # Pause check between players
                if _check_for_pause():
                    _handle_pause()

                # Retry the tap chain up to N times if it fails
                winrate: float | None = None
                score: int | None = None
                for attempt in range(1, args.max_retries_per_player + 1):
                    try:
                        winrate, score = scrape_one_player(current_rank, slot)
                    except Exception:
                        print(f"  exception at rank {current_rank}:")
                        traceback.print_exc()
                        winrate, score = None, None
                    if winrate is not None:
                        break
                    if attempt < args.max_retries_per_player:
                        print(f"  attempt {attempt}/{args.max_retries_per_player} failed; retrying")
                    else:
                        print(f"  giving up on rank {current_rank} after {attempt} attempts")

                writer.write(LeaderboardRow(
                    champion=args.target,
                    rank=current_rank,
                    player_name="",
                    score=score,
                    winrate=winrate,
                ))
                if winrate is not None:
                    successes += 1
                ranks_in_batch += 1
                current_rank += 1

            # Batch complete — ask user to scroll (or pause)
            if current_rank > end_rank:
                break
            next_batch_start = current_rank
            next_batch_end = min(current_rank + ROWS_PER_PAGE - 1, end_rank)
            print(f"\n=== batch done. Next: ranks {next_batch_start}-{next_batch_end} ===")
            response = input("  Scroll the leaderboard so this batch's first rank is at slot 0, then press Enter (or 'p' Enter to pause now): ").strip().lower()
            if response.startswith("p"):
                _handle_pause()
    except KeyboardInterrupt:
        print("\n^C — stopping at user request")

    print(f"\ndone. {successes}/{current_rank - args.start_rank} winrates parsed. CSV -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
