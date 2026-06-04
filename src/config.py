"""Loaders for the per-screen coordinate JSONs + OCR regions."""
from __future__ import annotations

import json
from pathlib import Path

COORDS_DIR = Path(__file__).resolve().parent.parent / "coords"

# OCR crop region for the champion-tiles strip on screen 5 (CHAMPION AND LANE).
# Format: (x, y, w, h) in device-native pixels.
SCREEN_5_OCR_REGION: tuple[int, int, int, int] = (573, 601, 909, 167)


def load_screen_points(n: int) -> dict[str, tuple[int, int]]:
    """Return name -> (x, y) for coords/screen_N.json."""
    path = COORDS_DIR / f"screen_{n}.json"
    data = json.loads(path.read_text())
    return {name: (p["x"], p["y"]) for name, p in data["points"].items()}


def first_point(points: dict[str, tuple[int, int]]) -> tuple[str, int, int]:
    """Return (name, x, y) of the first entry in the dict (insertion order)."""
    name, (x, y) = next(iter(points.items()))
    return name, x, y
