"""Exercise the between-champion maintenance restart on demand.

The real one is nested inside the carousel and only fires on a timer after a
champion finishes, so testing it meant waiting out a full champion scrape.
This drives the SAME sequence against the same constants, one step at a time,
and says which step failed instead of just "stopping safely".

    python -m scripts.check_maintenance_restart --device RFCX20KTG7K --dry-run
    python -m scripts.check_maintenance_restart --device RFCX20KTG7K

Start it from a champion leaderboard, which is where the carousel is when the
restart triggers. --dry-run reads the screen and reports what it sees without
pressing anything, which is the safe way to confirm detection before letting
it quit the game.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.adb_client import ADBClient  # noqa: E402
from src.config import (  # noqa: E402
    MAIN_MENU_NAME_REGION,
    MAIN_MENU_PANEL_REGION,
    MAIN_MENU_PANEL_WORDS,
    MAIN_MENU_PLAY_REGION,
    MAIN_MENU_PLAY_WORDS,
    QUIT_DIALOG_CONFIRM,
    QUIT_DIALOG_REGION,
    load_calibration,
)
from src.ocr import GENERAL_TESSERACT_CONFIG, read_text  # noqa: E402
from src.scrape_timed import looks_like_power_saving  # noqa: E402


def region_text(img, region) -> str:
    x, y, w, h = region
    crop = img[y:y + h, x:x + w]
    if crop.size == 0:
        return ""
    return (read_text(crop, GENERAL_TESSERACT_CONFIG).text or "").lower()


def looks_like_main_menu(img, profile_name: str) -> tuple[bool, str]:
    """(verdict, why) so a failure says which signal was missing."""
    panel = region_text(img, MAIN_MENU_PANEL_REGION)
    if any(w in panel for w in MAIN_MENU_PANEL_WORDS):
        return True, f"panel matched: {panel.strip()[:40]!r}"
    if profile_name:
        chip = region_text(img, MAIN_MENU_NAME_REGION)
        if profile_name in chip:
            return True, f"name chip matched: {chip.strip()[:40]!r}"
    play = region_text(img, MAIN_MENU_PLAY_REGION)
    if any(w in play for w in MAIN_MENU_PLAY_WORDS):
        return True, f"PLAY matched: {play.strip()[:40]!r}"
    return False, (f"panel={panel.strip()[:30]!r} play={play.strip()[:30]!r}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--device", default=None, help="adb serial")
    ap.add_argument("--dry-run", action="store_true",
                    help="read the screen and report; press nothing")
    ap.add_argument("--app-package", default="com.riotgames.league.wildrift")
    args = ap.parse_args()

    client = ADBClient(device=args.device)
    profile = str(load_calibration().get("profile_name", "")).lower().strip()
    print(f"device: {args.device or '(default)'}   profile name: {profile or '(unset)'}")

    img = client.screenshot()
    print(f"\n[0] current screen  {img.shape[1]}x{img.shape[0]}")
    if looks_like_power_saving(img):
        print("    POWER-SAVING overlay detected")
        if args.dry_run:
            print("    (dry run: would tap centre to wake)")
        else:
            h, w = img.shape[:2]
            client.tap(w // 2, h // 2)
            time.sleep(0.6)
            img = client.screenshot()
            print("    tapped to wake; re-read the screen")
    else:
        print("    not power-saving")

    ok, why = looks_like_main_menu(img, profile)
    print(f"    main menu? {ok}  ({why})")

    if args.dry_run:
        print("\n[dry run] stopping here. Re-run without --dry-run to drive the "
              "full restart: BACK -> main menu -> BACK -> Quit dialog -> confirm "
              "-> force-stop -> relaunch.")
        return 0

    print("\n[1] BACK, then wait up to 10s for the main menu")
    client.back()
    deadline, seen, why = time.time() + 10.0, False, ""
    while time.time() < deadline:
        img = client.screenshot()
        if looks_like_power_saving(img):
            print("    power-saving appeared mid-poll -- tapping to wake")
            h, w = img.shape[:2]
            client.tap(w // 2, h // 2)
            time.sleep(0.6)
            continue
        seen, why = looks_like_main_menu(img, profile)
        if seen:
            break
        time.sleep(0.6)
    print(f"    main menu seen: {seen}  ({why})")
    if not seen:
        print("    FAILED here. This is the step that aborted your run.")
        return 1

    print("\n[2] BACK again, then look for the Quit Game dialog")
    client.back()
    time.sleep(1.0)
    dialog, text = False, ""
    for _ in range(8):
        text = region_text(client.screenshot(), QUIT_DIALOG_REGION)
        if "quit" in text or "notice" in text:
            dialog = True
            break
        time.sleep(0.5)
    print(f"    quit dialog seen: {dialog}  (read {text.strip()[:50]!r})")
    if not dialog:
        print("    FAILED here, before any confirm was pressed.")
        return 1

    print(f"\n[3] confirm at {QUIT_DIALOG_CONFIRM}, force-stop, relaunch")
    client.tap(*QUIT_DIALOG_CONFIRM)
    time.sleep(2.0)
    text = region_text(client.screenshot(), QUIT_DIALOG_REGION)
    if "quit" in text or "notice" in text:
        print("    dialog still up; confirming once more")
        client.tap(*QUIT_DIALOG_CONFIRM)
        time.sleep(2.0)
    client.force_stop(args.app_package)
    time.sleep(0.8)
    client.launch_app(args.app_package)

    print("\n[4] waiting for the game to come back")
    deadline, seen, why = time.time() + 90.0, False, ""
    while time.time() < deadline:
        img = client.screenshot()
        if looks_like_power_saving(img):
            h, w = img.shape[:2]
            client.tap(w // 2, h // 2)
            time.sleep(0.6)
            continue
        seen, why = looks_like_main_menu(img, profile)
        if seen:
            break
        time.sleep(1.5)
    print(f"    main menu after relaunch: {seen}  ({why})")
    print("\nRESULT:", "restart works end to end" if seen else "relaunch did not reach the menu")
    return 0 if seen else 1


if __name__ == "__main__":
    raise SystemExit(main())
