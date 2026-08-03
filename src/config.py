"""Loaders for the per-screen coordinate JSONs + OCR regions."""
from __future__ import annotations

import json
from pathlib import Path

# Force the path to resolve absolutely relative to this file's location on disk.
# This prevents background threads and GUIs from looking in the wrong execution directory.
COORDS_DIR = Path(__file__).resolve().parent.parent / "coords"

# Persistent calibration file. Stores values learned at runtime so subsequent
# runs can skip the OCR-based alignment.
CALIBRATION_FILE: Path = COORDS_DIR / "calibration.json"


def load_calibration() -> dict[str, float]:
    """Return the persisted calibration dict, or {} if file missing/invalid."""
    if not CALIBRATION_FILE.exists():
        return {}
    try:
        return json.loads(CALIBRATION_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_calibration(data: dict[str, float]) -> None:
    """Merge `data` into the existing calibration file and write back."""
    existing = load_calibration()
    existing.update(data)
    CALIBRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    CALIBRATION_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")

# OCR crop region for the champion-tiles strip on screen 5.
# Format: (x, y, w, h) in device-native pixels.
# History:
#   - (573, 601, 909, 167) on the 1600x900 emulator (CHAMPION AND LANE default tab)
#   - (779, 729, 1367, 192) on the 2340x1080 phone (CHAMPION AND LANE default tab)
#   - (779, 729, 1561, 201) on the 2340x1080 phone after switching to the
#     RECENT tab — the layout is wider so tiles span more horizontally.
SCREEN_5_OCR_REGION: tuple[int, int, int, int] = (779, 729, 1561, 201)

# Player-name OCR on screen 2 (the leaderboard). The name appears in a
# fixed position relative to each row, so we crop using the row's mapped
# y plus a fixed offset/height. Tune by mapping the name rect for row 1
# (rank 1) with `python -m src.region_picker`. The printed --crop is
# (x, y, w, h); plug them in here.
#
# Phone (2340x1080) example from row 1 with player_row_1.y = 246:
#   region (1341, 196, 345, 53)
#   -> X range:  (1341, 1341+345) = (1341, 1686)
#   -> Y offset: 196 - 246 = -50 (name top sits 50px above row tap-y)
#   -> Height:   53
SCREEN_2_NAME_X_RANGE: tuple[int, int] = (1341, 1686)
SCREEN_2_NAME_Y_OFFSET: int = -50
SCREEN_2_NAME_HEIGHT: int = 53

# OCR region for the big champion-name label at lower-left of screen 2
# (e.g. "AATROX") used to verify the bot didn't open the wrong leaderboard page.
SCREEN_2_LABEL_REGION: tuple[int, int, int, int] = (90, 890, 240, 60)

# How many player rows fit on screen 2 without scrolling.
ROWS_PER_PAGE = 5

# Strip swipe anchors on screen 5 (right-to-left swipe reveals more champion
# tiles). Derived from SCREEN_5_OCR_REGION with a margin on each side.
_x, _y, _w, _h = SCREEN_5_OCR_REGION
SCREEN_5_STRIP_CENTER_Y: int = _y + _h // 2
SCREEN_5_STRIP_LEFT_X: int = _x + 30
SCREEN_5_STRIP_RIGHT_X: int = _x + _w - 30

# Rank-badge x-range on screen 2 (used by rank-verification OCR). Each row
# has a banner-shaped badge at this x-range; vertical center comes from the
# row pitch.
SCREEN_2_BADGE_X_RANGE: tuple[int, int] = (575, 695)

# ---- extended-capture points (phone 2340x1080, measured from flow_*.png) ----
# Book icon at the right of every leaderboard row: opens the player's BUILD
# popup for this champion. Tap at (BOOK_X, detected row y).
SCREEN_2_BOOK_X: int = 2049
# The X that closes the build popup.
SCREEN_2_BUILD_CLOSE: tuple[int, int] = (1936, 178)
# STATS tab in the profile's bottom tab bar (same bar as CHAMPION AND LANE).
SCREEN_5_STATS_TAB: tuple[int, int] = (1178, 1028)
# Stats page controls: the list-view toggle (right of the radar/list switch),
# the queue dropdown, and the dropdown's option rows when open.
STATS_LIST_TOGGLE: tuple[int, int] = (2153, 45)
STATS_QUEUE_DROPDOWN: tuple[int, int] = (1702, 45)
# Champions page (screen 1, CHAMPION tab): rows carry the champion NAME as
# text (no number badges). Names live in this x-band; rows share the 146px
# pitch of the player list.
SCREEN_1_NAME_X_RANGE: tuple[int, int] = (1180, 1660)
SCREEN_1_ROW_TAP_X: int = 1220
# Screen 2's top-left back chevron (returns to the champions page) and the
# champion-name label at the bottom-left (authoritative identity check).
SCREEN_2_BACK_POINT: tuple[int, int] = (172, 47)
# Wide enough for the longest names ("NUNU & WILLUMP" clipped at 260px and a
# live run skipped him); verified against every flow frame + the main menu
# that no other screen shows matchable text in this band at width 700.
SCREEN_2_CHAMP_LABEL_REGION: tuple[int, int, int, int] = (230, 845, 700, 55)

# Main-menu recovery: climbing back into the leaderboard after a full
# ejection. Coordinates derived from owner-supplied screenshots
# (data/menu_01_mainmenu.png, data/menu_02.png, data/exit_game.png).
MAIN_MENU_PLAY_REGION: tuple[int, int, int, int] = (1950, 865, 245, 150)  # OCR: "PLAY"
MAIN_MENU_LEADERBOARD_BADGE: tuple[int, int] = (1331, 1016)  # last badge, bottom bar
LEADERBOARD_CHAMPION_TAB: tuple[int, int] = (698, 1028)      # bottom tab bar
QUIT_DIALOG_REGION: tuple[int, int, int, int] = (809, 369, 740, 330)  # OCR: NOTICE / Quit Game?
QUIT_DIALOG_CANCEL: tuple[int, int] = (1002, 631)

STATS_QUEUE_OPTIONS: dict[str, tuple[int, int]] = {
    "all": (1702, 109),
    "ranked": (1702, 181),
    "normal": (1702, 252),
    "legendary": (1702, 325),
}

# Safe-zone y-range on screen 2 — any rank badge whose top y is below this
# minimum (closer to the top of the screen) is partially cut off; any badge
# whose bottom y exceeds the maximum is partially cut off at the bottom.
# When a target badge isn't inside this zone, the bot does a micro-swipe to
# correct.
SCREEN_2_SAFE_Y_TOP: int = 170
SCREEN_2_SAFE_Y_BOTTOM: int = 710


def load_screen_points(n: int) -> dict[str, tuple[int, int]]:
    """Return name -> (x, y) coordinates for screen N with robust absolute pathing."""
    path = COORDS_DIR / f"screen_{n}.json"

    if not path.exists():
        print(f"\n❌ [CRITICAL CONFIG ERROR] Layout configuration file missing!")
        print(f"👉 Looked at absolute path: {path}")
        print("💡 Please verify that your JSON calibration profiles exist in your 'coords/' directory.\n")
        raise FileNotFoundError(f"Missing coordinate calibration map: {path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {name: (p["x"], p["y"]) for name, p in data["points"].items()}
    except Exception as e:
        print(f"\n❌ [CRITICAL READ ERROR] Failed parsing JSON contents at {path}")
        print(f"👉 System Error: {e}\n")
        raise


def first_point(points: dict[str, tuple[int, int]]) -> tuple[str, int, int]:
    """Return (name, x, y) of the first entry in a coordinates dict (insertion order)."""
    if not points:
        raise ValueError("Cannot extract coordinates from an empty points dictionary.")
    name, (x, y) = next(iter(points.items()))
    return name, x, y