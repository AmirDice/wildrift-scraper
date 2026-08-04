"""The CHAMPION tab must stay readable: the carousel navigates by these names.

Pinned against a live capture of the current layout. The previous fixture went
stale (a different row pitch, and only 4 of 6 names readable), which is exactly
the kind of drift that turns into "the carousel skipped a champion" at 3am.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import pytest

from src.config import (
    MAIN_MENU_PLAY_REGION,
    MAIN_MENU_PLAY_WORDS,
    QUIT_DIALOG_REGION,
    SCREEN_1_NAME_X_RANGE,
    SCREEN_2_CHAMP_LABEL_REGION,
)
from src.ocr import (
    GENERAL_TESSERACT_CONFIG,
    read_champion_name,
    read_text,
    scan_champion_rows,
)

FRAME = Path("data/champions_page.png")


@pytest.mark.skipif(not FRAME.exists(), reason="champions page capture not present")
def test_every_visible_champion_row_is_read():
    img = cv2.imread(str(FRAME))
    slots = scan_champion_rows(img, SCREEN_1_NAME_X_RANGE)
    names = [n for _, n in slots if n]
    assert len(slots) >= 5, f"too few rows detected: {slots}"
    assert len(names) == len(slots), f"unread rows: {slots}"
    ys = [y for y, _ in slots]
    pitch = [b - a for a, b in zip(ys, ys[1:])]
    assert all(130 <= p <= 165 for p in pitch), f"row pitch drifted: {pitch}"


@pytest.mark.skipif(not FRAME.exists(), reason="champions page capture not present")
def test_champions_page_is_not_mistaken_for_another_screen():
    """The carousel decides what to tap from these three probes, so a false
    positive here sends it somewhere else entirely."""
    img = cv2.imread(str(FRAME))
    assert read_champion_name(img, SCREEN_2_CHAMP_LABEL_REGION) is None

    def region(box):
        x, y, w, h = box
        crop = img[y:y + h, x:x + w]
        return (read_text(crop, GENERAL_TESSERACT_CONFIG).text or "").lower()

    quit_txt = region(QUIT_DIALOG_REGION)
    assert "quit" not in quit_txt and "notice" not in quit_txt
    play = region(MAIN_MENU_PLAY_REGION)
    assert not any(w in play for w in MAIN_MENU_PLAY_WORDS)
