"""Contract tests for the optional OCR backend selection and normalisation."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import ocr


def test_backend_selection_is_explicit(monkeypatch) -> None:
    monkeypatch.setenv("OCR_ENGINE", "paddle")
    assert ocr.ocr_engine() == "paddle"
    monkeypatch.setenv("OCR_ENGINE", "not-a-backend")
    assert ocr.ocr_engine() == "tesseract"


def test_paddle_old_result_normalises_to_words() -> None:
    words = ocr._paddle_words([[
        [[[10, 20], [50, 20], [50, 40], [10, 40]], ("53.7%", 0.97)],
    ]])
    assert len(words) == 1
    assert words[0].text == "53.7%"
    assert words[0].x == 30 and words[0].y == 30
    assert words[0].confidence == 0.97


def test_paddle_new_result_normalises_parallel_arrays() -> None:
    words = ocr._paddle_words({
        "rec_texts": ["Caitlyn", "61.2%"],
        "rec_scores": [0.91, 0.88],
        "dt_polys": [
            [[0, 0], [70, 0], [70, 20], [0, 20]],
            [[80, 0], [130, 0], [130, 20], [80, 20]],
        ],
    })
    assert [word.text for word in words] == ["Caitlyn", "61.2%"]
    assert words[1].x == 105 and words[1].confidence == 0.88


def test_auto_keeps_high_confidence_tesseract(monkeypatch) -> None:
    monkeypatch.setenv("OCR_ENGINE", "auto")
    monkeypatch.setattr(ocr, "_run_tesseract", lambda _img, _cfg: ("fast", 80.0))

    def paddle_must_not_run(_img):
        raise AssertionError("Paddle should not run for a confident Tesseract read")

    monkeypatch.setattr(ocr, "_run_paddle", paddle_must_not_run)
    result = ocr.read_text(np.zeros((20, 40), dtype=np.uint8), ocr.GENERAL_TESSERACT_CONFIG)
    assert result.text == "fast"


def test_auto_uses_paddle_for_low_confidence_tesseract(monkeypatch) -> None:
    monkeypatch.setenv("OCR_ENGINE", "auto")
    monkeypatch.setattr(ocr, "_run_tesseract", lambda _img, _cfg: ("", -1.0))
    monkeypatch.setattr(ocr, "_run_paddle", lambda _img: ("fallback", 0.9, []))
    result = ocr.read_text(np.zeros((20, 40), dtype=np.uint8), ocr.GENERAL_TESSERACT_CONFIG)
    assert result.text == "fallback"


def test_auto_uses_paddle_for_low_confidence_words(monkeypatch) -> None:
    monkeypatch.setenv("OCR_ENGINE", "auto")
    weak_tesseract = {
        "text": ["x"], "conf": ["20"],
        "left": [0], "top": [0], "width": [4], "height": [4],
    }
    monkeypatch.setattr(
        ocr.pytesseract, "image_to_data", lambda *_args, **_kwargs: weak_tesseract,
    )
    paddle_words = [ocr.OCRWord("fallback", 8, 8, 12, 4, 0.9)]
    monkeypatch.setattr(ocr, "_run_paddle", lambda _img: ("fallback", 0.9, paddle_words))
    result = ocr.read_words(np.zeros((20, 40), dtype=np.uint8), ocr.GENERAL_TESSERACT_CONFIG)
    assert result == paddle_words


def test_auto_rank_navigation_does_not_start_paddle(monkeypatch) -> None:
    """Fixed leaderboard digits stay on the fast live-navigation path.

    Paddle remains the hybrid fallback for offline text fields, but starting
    its models while returning from every profile made collection needlessly
    slow and did not improve the consecutive rank chain.
    """
    monkeypatch.setenv("OCR_ENGINE", "auto")
    monkeypatch.setattr(
        ocr.rank_digits,
        "read_column",
        lambda *_args, **_kwargs: {7: 180, 8: 340, 9: 500, 10: 660},
    )

    calls = []

    def paddle_must_not_run(*_args, **_kwargs):
        calls.append(True)
        return []

    monkeypatch.setattr(ocr, "read_words", paddle_must_not_run)
    ranks, pitch = ocr.scan_visible_ranks(
        np.zeros((1080, 1200, 3), dtype=np.uint8),
        (685, 855),
        hint=9,
        expected_pitch=160,
    )
    assert ranks == {7: 180, 8: 340, 9: 500, 10: 660}
    assert pitch == 160
    assert calls == []
