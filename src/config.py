"""Loaders for the per-screen coordinate JSONs + OCR regions."""
from __future__ import annotations

import json
from pathlib import Path

COORDS_DIR = Path(__file__).resolve().parent.parent / "coords"

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


def load_screen_points(n: int) -> dict[str, tuple[int, int]]:
    """Return name -> (x, y) for coords/screen_N.json."""
    path = COORDS_DIR / f"screen_{n}.json"
    data = json.loads(path.read_text())
    return {name: (p["x"], p["y"]) for name, p in data["points"].items()}


def first_point(points: dict[str, tuple[int, int]]) -> tuple[str, int, int]:
    """Return (name, x, y) of the first entry in the dict (insertion order)."""
    name, (x, y) = next(iter(points.items()))
    return name, x, y
