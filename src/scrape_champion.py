"""Manual-scroll scraper with automated UI reset recovery.

You scroll Wild Rift's leaderboard yourself or let the automated macro catch up
when the UI aggressively snaps back to ranks 1-5. The bot handles the per-player
tap chain safely by checking the rank badge via quick local Tesseract OCR before
clicking any row.
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
    load_screen_points, 
    SCREEN_2_BADGE_X_RANGE, 
    SCREEN_2_SAFE_Y_TOP, 
    SCREEN_2_SAFE_Y_BOTTOM
)
from .storage import CSVWriter, LeaderboardRow
from .strip import find_target_in_strip
from .ocr import read_text

# Non-blocking keyboard polling for the pause feature on Windows.
if os.name == "nt":
    import msvcrt

    def _key_pressed() -> str | None:
        if msvcrt.kbhit():
            ch = msvcrt.getch()
            if ch in (b"\x00", b"\xe0"):  # Function keys
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


def recover_scroll_position(
    client: ADBClient,
    target_x: int,
    rank_1_y: int,
    row_pitch: float,
) -> None:
    """Do ONE controlled page scroll forward (~5 rows). The caller re-verifies
    via OCR after this returns and calls recover again if more scroll is needed.

    Uses the proven swipe params from when full automation was working:
        - swipe scale 0.85 of one page worth of pitch
        - 1500ms duration (slow enough to be a controlled drag, not a fling)
        - 2s settle wait so the list animation finishes before OCR reads
    """
    start_y = int(round(rank_1_y + (ROWS_PER_PAGE - 1) * row_pitch))
    distance_px = int(round(ROWS_PER_PAGE * row_pitch * 0.85))
    end_y = max(50, start_y - distance_px)
    print(f"  [RECOVERY] page-scrolling: ({target_x}, {start_y}) -> ({target_x}, {end_y}) [1500ms]")
    client.swipe(target_x, start_y, target_x, end_y, duration_ms=1500)
    time.sleep(2.0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", default="Aatrox")
    parser.add_argument("--n", type=int, default=200)
    parser.add_argument("--start-rank", type=int, default=1)
    parser.add_argument("--device", default="127.0.0.1:7555")
    parser.add_argument("--no-connect", action="store_true")
    parser.add_argument("--step-wait", type=float, default=2.0)
    parser.add_argument("--output", type=Path, default=Path("data/winrates.csv"))
    parser.add_argument("--save-screenshots", action="store_true")
    parser.add_argument("--max-strip-swipes", type=int, default=3)
    parser.add_argument("--strip-swipe-scale", type=float, default=0.7)
    parser.add_argument("--strip-swipe-duration-ms", type=int, default=800)
    parser.add_argument("--max-retries-per-player", type=int, default=3)
    args = parser.parse_args()

    client = ADBClient(device=args.device)
    if not args.no_connect:
        try:
            client.connect()
        except ADBError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1

    s2_pts = load_screen_points(2)
    s3_pts = load_screen_points(3)
    s4_pts = load_screen_points(4)
    s5_pts = load_screen_points(5)

    missing = []
    # Existing schema: rank-1 row = "aatrox", rank-2 row = "player_row_2".
    if "aatrox" not in s2_pts: missing.append("screen_2.json:aatrox (rank 1 tap)")
    if "player_row_2" not in s2_pts: missing.append("screen_2.json:player_row_2 (rank 2 tap, for pitch)")
    if "aatrox" not in s3_pts: missing.append("screen_3.json:aatrox (view-profile button)")
    if "aatrox" not in s4_pts: missing.append("screen_4.json:aatrox (CHAMPION AND LANE tab)")
    if "back" not in s5_pts: missing.append("screen_5.json:back")

    if missing:
        print("error: missing required calibrated points:")
        for m in missing:
            print(f"  {m}")
        return 1

    target_x, start_y = s2_pts["aatrox"]
    # The rank-1 row has extra header padding, so deriving pitch only from
    # (player_row_2 - aatrox) inflates it. Prefer a wider span if mapped:
    # player_row_5 (4 spans) -> most accurate, then player_row_3, then row_2.
    if "player_row_5" in s2_pts:
        _, deep_y = s2_pts["player_row_5"]
        pitch_y = (deep_y - start_y) / 4
        pitch_source = "rank 1 -> rank 5"
    elif "player_row_3" in s2_pts:
        _, deep_y = s2_pts["player_row_3"]
        pitch_y = (deep_y - start_y) / 2
        pitch_source = "rank 1 -> rank 3"
    else:
        _, y1 = s2_pts["player_row_2"]
        pitch_y = y1 - start_y
        pitch_source = "rank 1 -> rank 2 (may be inflated by header padding)"
    print(f"row pitch       : {pitch_y:.1f}px  ({pitch_source})")

    s3_view = s3_pts["aatrox"]
    s4_lane = s4_pts["aatrox"]
    s5_back = s5_pts["back"]

    writer = CSVWriter(args.output)
    current_rank = args.start_rank
    end_rank = args.start_rank + args.n - 1
    successes = 0
    paused = False

    def _handle_pause():
        nonlocal paused
        paused = True
        print("\n=== scraper paused. Press Enter in this window to resume ===")
        input()
        paused = False
        print("=== resuming ===")

    print(f"starting scrape: {args.target}, ranks {current_rank} to {end_rank}")
    print("press 'p' at any time to pause after the current player loop concludes.")
    print("the bot auto-scrolls and auto-recovers from leaderboard snap-backs.")
    print()

    # If the guardrail keeps firing for the same rank, fall back to a manual prompt.
    consecutive_recoveries = 0
    MAX_AUTO_RECOVERIES = 4

    try:
        while current_rank <= end_rank:
            if _key_pressed() == "p":
                _handle_pause()

            idx = (current_rank - 1) % ROWS_PER_PAGE
            row_y = start_y + idx * pitch_y

            # --- 1. PRE-CLICK STATE VALIDATION GUARDRAIL ---
            # Validate before EVERY tap: OCR the current slot's rank badge
            # and check it matches `current_rank`. Recover if not.
            # Special handling for slot 0 when current_rank>=6: rank 1's
            # gold trophy doesn't OCR, so empty result at slot 0 isn't a
            # signal — fall back to checking slot 1's badge instead.
            try:
                img_check = client.screenshot()

                def _ocr_rank_at(yc: int) -> int | None:
                    crop = img_check[
                        int(yc - 22):int(yc + 22),
                        SCREEN_2_BADGE_X_RANGE[0]:SCREEN_2_BADGE_X_RANGE[1],
                    ]
                    text = read_text(crop).text
                    digits = re.sub(r"\D", "", text)
                    if not digits:
                        return None
                    try:
                        v = int(digits)
                    except ValueError:
                        return None
                    # Sanity bounds — reject garbage OCR (e.g. score-column bleed)
                    if 1 <= v <= 250:
                        return v
                    return None

                detected = _ocr_rank_at(row_y)
                needs_recovery = False

                if detected is not None:
                    if detected != current_rank:
                        print(f"  [GUARDRAIL] expected rank {current_rank} at slot {idx}, OCR detected {detected}")
                        needs_recovery = True
                elif current_rank >= 6 and idx == 0:
                    # Slot 0 OCR empty AND we're not in the initial top-5
                    # — could be rank 1's gold trophy after a reset. Check
                    # slot 1 (rank 2's badge is plain and OCRs reliably).
                    slot_1_y = start_y + pitch_y
                    det_s1 = _ocr_rank_at(slot_1_y)
                    if det_s1 is not None and det_s1 < current_rank:
                        print(f"  [GUARDRAIL] slot 0 didn't OCR (rank-1 trophy?), slot 1 shows rank {det_s1} but expected ~{current_rank + 1}")
                        needs_recovery = True

                if needs_recovery:
                    consecutive_recoveries += 1
                    if consecutive_recoveries > MAX_AUTO_RECOVERIES:
                        print(f"  [GUARDRAIL] auto-recovery failed {consecutive_recoveries-1}x in a row.")
                        input(f"  Manually scroll Wild Rift so rank {current_rank} is at slot 0, then press Enter: ")
                        consecutive_recoveries = 0
                        continue  # re-enter the loop to re-validate
                    recover_scroll_position(client, target_x, start_y, pitch_y)
                    continue  # re-enter the loop to re-validate after scroll
                else:
                    # Good: the rank we expected is at the slot we're about to tap.
                    consecutive_recoveries = 0
            except Exception:
                # Non-fatal: any OCR error -> skip guardrail, continue chain
                pass

            # --- 2. RUN ORIGINAL DATA EXTRACTION FLOW ---
            print(f"\n--- Rank {current_rank} (Slot {idx}) ---")
            print(f"  tap player row -> ({target_x}, {row_y})")

            winrate = None
            score = None
            games = None
            attempt = 0

            while attempt < args.max_retries_per_player:
                attempt += 1
                try:
                    # Double-tap the player row — first tap is sometimes
                    # eaten by scroll-settle animation right after a swipe.
                    # The second tap 0.4s later either opens the popup (if
                    # the first missed) or lands on the popup's avatar/banner
                    # area (if the first succeeded). The avatar is non-actionable
                    # on Wild Rift's popup so this is usually safe — but if you
                    # see the popup being dismissed instead of the profile
                    # opening, the second tap is hitting the dimmed background
                    # outside the popup, and we should remove this double-tap.
                    client.tap(target_x, row_y)
                    time.sleep(0.4)
                    client.tap(target_x, row_y)
                    time.sleep(args.step_wait)

                    if _key_pressed() == "p":
                        _handle_pause()

                    # Double-tap view-profile — first tap can be eaten by
                    # the popup-appearance animation; second tap 0.4s
                    # later reliably triggers the profile load. If the
                    # first one already loaded the full profile, the
                    # second tap lands at (1221, 239) on screen 4 — an
                    # empty area of the profile header, harmless no-op.
                    print(f"  tap view profile (x2) -> {s3_view}")
                    client.tap(*s3_view)
                    time.sleep(0.4)
                    client.tap(*s3_view)
                    time.sleep(args.step_wait)

                    # Double-tap CHAMPION AND LANE — the first tap is often
                    # eaten by the popup -> profile transition animation;
                    # the second one ~0.4s later reliably lands on the tab.
                    # If the first one DID register, the second is a no-op
                    # on an already-selected tab.
                    print(f"  tap champion and lane (x2) -> {s4_lane}")
                    client.tap(*s4_lane)
                    time.sleep(0.4)
                    client.tap(*s4_lane)
                    time.sleep(args.step_wait)

                    print(f"  searching champion strip for '{args.target}'...")
                    wr, sc, gm, _, swipes_done, last_img = find_target_in_strip(
                        client,
                        args.target,
                        max_swipes=args.max_strip_swipes,
                        swipe_scale=args.strip_swipe_scale,
                        swipe_duration_ms=args.strip_swipe_duration_ms,
                        wait_after_swipe=args.step_wait,
                    )

                    if wr is not None:
                        winrate = wr
                        score = sc
                        games = gm
                        print(f"    found: {winrate}% winrate over {games} games (score: {score})")
                    else:
                        print(f"    [failed] target '{args.target}' not found in player's catalog")

                    if args.save_screenshots:
                        out_p = Path(f"data/screenshots/{args.target.lower()}_{current_rank}.png")
                        out_p.parent.mkdir(parents=True, exist_ok=True)
                        cv2.imwrite(str(out_p), last_img)

                    print(f"  tap screen 5 back -> {s5_back}")
                    client.tap(*s5_back)
                    time.sleep(args.step_wait)
                    break

                except Exception:
                    print(f"  [exception] nested navigation chain failed on attempt {attempt}:")
                    traceback.print_exc()
                    print("  recovering system state via native device hardware back key sequence...")
                    
                    # System recovery block: issues back commands to reset application frame state back to Screen 2
                    for _ in range(4):
                        client.back()
                        time.sleep(0.5)

                    if attempt < args.max_retries_per_player:
                        print(f"  attempt {attempt}/{args.max_retries_per_player} failed; retrying slot")
                    else:
                        print(f"  giving up on rank {current_rank} after {attempt} attempts")

            writer.write(LeaderboardRow(
                champion=args.target,
                rank=current_rank,
                player_name="",
                score=score,
                games=games,
                winrate=winrate,
            ))
            
            if winrate is not None:
                successes += 1

            current_rank += 1
            # Next iteration: guardrail re-validates whatever's now visible
            # and auto-scrolls if we just crossed a page boundary.

    except KeyboardInterrupt:
        print("\n^C — stopping at user request")

    print(f"\ndone. {successes}/{current_rank - args.start_rank} winrates parsed. CSV -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())