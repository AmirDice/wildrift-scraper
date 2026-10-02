"""Contract tests for the optional OCR backend selection and normalisation."""
from __future__ import annotations

import os
import sys
from pathlib import Path

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
