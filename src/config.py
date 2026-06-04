"""Loaders for the per-screen coordinate JSONs + OCR regions."""
from __future__ import annotations

import json
from pathlib import Path

COORDS_DIR = Path(__file__).resolve().parent.parent / "coords"

# Persistent calibration file. Stores values learned at runtime so subsequent
# runs can skip the OCR-based alignment.
CALIBRATION_FILE: Path = COORDS_DIR / "calibration.json"


def load_calibration() -> dict[str, float]:
    """Return the persisted calibration dict, or {} if file missing/invalid."""
    if not CALIBRATION_FILE.exists():
        return {}
    try:
        return json.loads(CALIBRATION_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def save_calibration(data: dict[str, float]) -> None:
    """Merge `data` into the existing calibration file and write back."""
    existing = load_calibration()
    existing.update(data)
    CALIBRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    CALIBRATION_FILE.write_text(json.dumps(existing, indent=2))

# OCR crop region for the champion-tiles strip on screen 5 (CHAMPION AND LANE).
# Format: (x, y, w, h) in device-native pixels.
SCREEN_5_OCR_REGION: tuple[int, int, int, int] = (573, 601, 909, 167)

# OCR region for the big champion-name label at lower-left of screen 2
# (e.g. "AATROX") — used to identify which champion we're currently on.
SCREEN_2_CHAMP_NAME_REGION: tuple[int, int, int, int] = (100, 700, 240, 60)

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

# Safe-zone y-range on screen 2 — any rank badge whose top y is below this
# minimum (closer to the top of the screen) is partially cut off; any badge
# whose bottom y exceeds the maximum is partially cut off at the bottom.
# When a target badge isn't inside this zone, the bot does a micro-swipe to
# correct.
SCREEN_2_SAFE_Y_TOP: int = 170
SCREEN_2_SAFE_Y_BOTTOM: int = 710


def load_screen_points(n: int) -> dict[str, tuple[int, int]]:
    """Return name -> (x, y) for coords/screen_N.json."""
    path = COORDS_DIR / f"screen_{n}.json"
    data = json.loads(path.read_text())
    return {name: (p["x"], p["y"]) for name, p in data["points"].items()}


def first_point(points: dict[str, tuple[int, int]]) -> tuple[str, int, int]:
    """Return (name, x, y) of the first entry in the dict (insertion order)."""
    name, (x, y) = next(iter(points.items()))
    return name, x, y
