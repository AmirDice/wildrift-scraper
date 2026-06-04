"""End-to-end test: navigate the 5-step flow and read one champion's winrate.

Prereq: in MuMu, you must already be on screen 1 (the main "CHAMPION" tab of
the Leaderboard) with the target champion visible in the same screen position
as your mapped `screen_1.json` point. For Aatrox with the captured coords,
the screen should match `data/1_champion_leaderboard.png`.

The script:
    1. Taps screen_1 point   -> screen 2 (champion's top players)
    2. Taps screen_2 point   -> screen 3 (small profile popup)
    3. Taps screen_3 point   -> screen 4 (full profile)
    4. Taps screen_4 point   -> screen 5 (CHAMPION AND LANE)
    5. Screenshots, OCRs the champion-tiles strip, prints results
    6. Presses Android BACK 4 times to return to screen 1

Run:
    python -m src.scrape_one --target Aatrox
    python -m src.scrape_one --target Aatrox --save-screenshots --step-wait 2.5
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2

from .adb_client import ADBClient, ADBError
from .config import SCREEN_5_OCR_REGION, first_point, load_screen_points
from .ocr import find_champion_winrates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", default="Aatrox", help="Champion to look up on screen 5")
    parser.add_argument("--device", default="127.0.0.1:7555")
    parser.add_argument("--no-connect", action="store_true")
    parser.add_argument("--step-wait", type=float, default=2.0, help="Seconds to wait after each tap for the next screen to load")
    parser.add_argument("--save-screenshots", action="store_true", help="Save the screen after each step into data/")
    parser.add_argument("--no-back", action="store_true", help="Skip the back-navigation at the end (useful for debugging)")
    args = parser.parse_args()

    # Load tap points for all 5 screens before doing anything destructive
    taps: list[tuple[int, str, int, int]] = []
    for n in (1, 2, 3, 4):
        try:
            pts = load_screen_points(n)
        except FileNotFoundError:
            print(f"error: coords/screen_{n}.json missing", file=sys.stderr)
            return 1
        if not pts:
            print(f"error: coords/screen_{n}.json has no points", file=sys.stderr)
            return 1
        name, x, y = first_point(pts)
        taps.append((n, name, x, y))

    print("loaded tap points:")
    for n, name, x, y in taps:
        print(f"  screen {n}: '{name}' -> ({x}, {y})")
    print(f"OCR region on screen 5: {SCREEN_5_OCR_REGION}")

    client = ADBClient(device=args.device)
    if not args.no_connect:
        try:
            client.connect()
        except ADBError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1

    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)

    def maybe_save(img, label: str) -> None:
        if args.save_screenshots:
            path = data_dir / f"run_{label}.png"
            cv2.imwrite(str(path), img)
            print(f"    -> {path}")

    # Steps 1-4: tap each saved point, wait, optional screenshot
    try:
        for n, name, x, y in taps:
            print(f"step {n}: tap ({x}, {y}) [{name}]")
            client.tap(x, y)
            time.sleep(args.step_wait)
            if args.save_screenshots:
                img = client.screenshot()
                maybe_save(img, f"after_step_{n}")

        # Step 5: screenshot screen 5 and OCR the champion-tile strip
        print("step 5: screenshot + OCR")
        img = client.screenshot()
        maybe_save(img, "screen_5_for_ocr")

        found = find_champion_winrates(img, SCREEN_5_OCR_REGION)
        if not found:
            print("  OCR found no recognized champions in the region.")
        else:
            print(f"  OCR found {len(found)} champion(s):")
            for champ, wr in found.items():
                marker = "  <-- TARGET" if champ.lower() == args.target.lower() else ""
                print(f"    {champ:<15} {wr}%{marker}")

        target_wr = next(
            (wr for champ, wr in found.items() if champ.lower() == args.target.lower()),
            None,
        )
        print()
        if target_wr is not None:
            print(f">>> {args.target} winrate = {target_wr}% <<<")
        else:
            print(f"WARNING: target '{args.target}' not visible in the current strip.")
            print("         (Likely need to swipe the strip to find it.)")
    finally:
        if not args.no_back:
            screen_5_pts = load_screen_points(5)
            if "back" in screen_5_pts:
                bx, by = screen_5_pts["back"]
                print(f"tap back on screen 5 -> ({bx}, {by})")
                client.tap(bx, by)
                time.sleep(args.step_wait)
            else:
                print("no 'back' point in screen_5.json; using Android BACK once")
                client.back()
                time.sleep(1.0)
            print("done")

    return 0


if __name__ == "__main__":
    sys.exit(main())
