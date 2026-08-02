"""Search-and-swipe on screen 5's champion-tile strip.

Used when the target champion isn't visible in the first 4 tiles of a player's
Champion and Lane page. Swipes right-to-left to reveal more tiles, OCRs after
each swipe, stops as soon as the target is found (or no new tiles appeared).
"""
from __future__ import annotations

import time

import numpy as np

from .adb_client import ADBClient
from .config import (
    SCREEN_5_OCR_REGION,
    SCREEN_5_STRIP_CENTER_Y,
    SCREEN_5_STRIP_LEFT_X,
    SCREEN_5_STRIP_RIGHT_X,
)
from .ocr import find_champion_winrates, find_target_data


def _read_frame_tesseract(
    img: np.ndarray, target: str,
) -> tuple[dict[str, float], tuple[float | None, int | None, int | None] | None]:
    """(found_dict, target_data_or_None) for one screenshot via Tesseract."""
    found = find_champion_winrates(img, SCREEN_5_OCR_REGION)
    target_lower = target.lower()
    if any(c.lower() == target_lower for c in found.keys()):
        return found, find_target_data(img, SCREEN_5_OCR_REGION, target)
    return found, None


def _read_frame_gemini(
    img: np.ndarray, target: str, model: str,
) -> tuple[dict[str, float], tuple[float | None, int | None, int | None] | None]:
    """Same contract via ONE structured Gemini call (vs ~4 Tesseract passes).
    Raises on API errors — the caller falls back to Tesseract for the frame."""
    from . import champions as champ_module
    from .gemini_ocr import read_strip

    x, y, w, h = SCREEN_5_OCR_REGION
    tiles = read_strip(img[y:y + h, x:x + w], model=model)
    found: dict[str, float] = {}
    data: dict[str, tuple[float | None, int | None, int | None]] = {}
    for t in tiles:
        canonical = champ_module.match(t.champion.split())
        if canonical is None:
            continue
        if t.win_rate is not None:
            found[canonical] = t.win_rate
        data[canonical] = (t.win_rate, t.score, t.games)
    target_lower = target.lower()
    for name, triple in data.items():
        if name.lower() == target_lower:
            return found, triple
    return found, None


def find_target_in_strip(
    client: ADBClient,
    target: str,
    *,
    max_swipes: int = 3,
    swipe_scale: float = 0.7,
    swipe_duration_ms: int = 800,
    wait_after_swipe: float = 1.2,
    use_gemini: bool = False,
    gemini_model: str = "gemini-3.5-flash-lite",
) -> tuple[float | None, int | None, int | None, dict[str, float], int, np.ndarray]:
    """Look for `target` champion on screen 5 and return its
    (winrate, score, games), swiping the strip right-to-left up to
    `max_swipes` times if not found.

    Returns: (winrate, score, games, last_found_dict, num_swipes, last_image).
    Each of winrate/score/games may be None if not found. Stops early when a
    swipe reveals no new champions (end of strip reached).

    use_gemini=True reads each frame with one structured vision-LLM call
    instead of multiple Tesseract passes; any API failure falls back to
    Tesseract for that frame, so the flag can never make a run worse.
    """
    gemini_ok = use_gemini

    def read_frame(img: np.ndarray):
        nonlocal gemini_ok
        if gemini_ok:
            try:
                return _read_frame_gemini(img, target, gemini_model)
            except Exception as e:  # noqa: BLE001 -- network/API: degrade, don't die
                print(f"    [gemini-strip] {e} — falling back to Tesseract for this run")
                gemini_ok = False
        return _read_frame_tesseract(img, target)

    img = client.screenshot()
    found, hit = read_frame(img)
    if hit is not None:
        wr, score, games = hit
        return wr, score, games, found, 0, img

    seen: set[str] = {c.lower() for c in found.keys()}
    swipes_done = 0

    for swipe_idx in range(1, max_swipes + 1):
        distance = int(round((SCREEN_5_STRIP_RIGHT_X - SCREEN_5_STRIP_LEFT_X) * swipe_scale))
        start_x = SCREEN_5_STRIP_RIGHT_X
        end_x = max(0, start_x - distance)
        client.swipe(start_x, SCREEN_5_STRIP_CENTER_Y, end_x, SCREEN_5_STRIP_CENTER_Y, swipe_duration_ms)
        time.sleep(wait_after_swipe)
        swipes_done = swipe_idx

        img = client.screenshot()
        found, hit = read_frame(img)
        if hit is not None:
            wr, score, games = hit
            return wr, score, games, found, swipes_done, img

        # End-of-strip detection: if this swipe revealed nothing new, stop.
        current = {c.lower() for c in found.keys()}
        if current and current.issubset(seen):
            break
        seen |= current

    return None, None, None, found, swipes_done, img
