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


def find_target_in_strip(
    client: ADBClient,
    target: str,
    *,
    max_swipes: int = 3,
    swipe_scale: float = 0.7,
    swipe_duration_ms: int = 800,
    wait_after_swipe: float = 1.2,
) -> tuple[float | None, int | None, int | None, dict[str, float], int, np.ndarray]:
    """Look for `target` champion on screen 5 and return its
    (winrate, score, games), swiping the strip right-to-left up to
    `max_swipes` times if not found.

    Returns: (winrate, score, games, last_found_dict, num_swipes, last_image).
    Each of winrate/score/games may be None if not found. Stops early when a
    swipe reveals no new champions (end of strip reached).
    """
    target_lower = target.lower()

    img = client.screenshot()
    found = find_champion_winrates(img, SCREEN_5_OCR_REGION)
    if any(c.lower() == target_lower for c in found.keys()):
        wr, score, games = find_target_data(img, SCREEN_5_OCR_REGION, target)
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
        found = find_champion_winrates(img, SCREEN_5_OCR_REGION)
        if any(c.lower() == target_lower for c in found.keys()):
            wr, score, games = find_target_data(img, SCREEN_5_OCR_REGION, target)
            return wr, score, games, found, swipes_done, img

        # End-of-strip detection: if this swipe revealed nothing new, stop.
        current = {c.lower() for c in found.keys()}
        if current and current.issubset(seen):
            break
        seen |= current

    return None, None, None, found, swipes_done, img
