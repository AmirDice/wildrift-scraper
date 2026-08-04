"""The rank-digit template bank: read the badges instead of interpreting them.

Tesseract reads this font's "3" as a "5", deterministically, and a whole
window misreads together (see test_tens_digit_misread). Templates remove the
question: it is one font at one size, so a glyph is compared against the
game's own pixels. Measured on held-out capture sessions, the rows under the
verified tap read 0 errors.

The bank is built by scripts/build_digit_bank.py and labelled from the capture
manifests -- never from OCR output, which would bake the very error being
fixed into the templates.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from src.rank_digits import BANK, N, read_column, read_row, templates

BADGE_X = (985, 1155)
FRAMES = Path("data/debug_scans")

pytestmark = pytest.mark.skipif(not BANK.exists(), reason="digit bank not built")


def test_bank_carries_every_digit():
    bank = templates()
    assert set(bank) == set(range(10)), f"bank is missing digits: {sorted(bank)}"
    for d, t in bank.items():
        assert t.shape == (N, N), f"digit {d} has shape {t.shape}"
        assert abs(float(np.linalg.norm(t)) - 1.0) < 1e-3, f"digit {d} is not unit-norm"


# Windows confirmed by reading the saved frames directly, NOT by any scanner.
# Only the fully-visible rows are listed: the clipped top and bottom rows are
# expected to decline, and the scanner's grid inference places those.
CONFIRMED = [
    ("lost_rank34_135448.png", [32, 33, 34, 35]),   # screen 31-35, 31 clipped
    ("lost_rank34_144350.png", [30, 31, 32, 33]),   # screen 29-33, 29 clipped
    ("lost_rank34_044532.png", [31, 32, 33, 34]),   # screen 31-35, 35 clipped
    ("lost_rank45_142447.png", [33, 34, 35, 36]),   # screen 32-37, both clipped
]


@pytest.mark.parametrize("name,expected", CONFIRMED)
def test_reads_the_frames_tesseract_got_wrong(name: str, expected: list[int]):
    path = FRAMES / name
    if not path.exists():
        pytest.skip(f"{name} not present")
    got = read_column(cv2.imread(str(path)), BADGE_X)
    assert sorted(got) == expected, f"read {sorted(got)}, screen shows {expected}"


def test_trophy_rows_are_never_claimed():
    """Ranks 1-3 wear ornate banners that seat the numeral ~20px above the
    row centre, so their glyph centroid is not a safe tap target. The reader
    must leave them to grid extrapolation rather than return a y that would
    tap between rows."""
    frame = Path("data/2_aatrox_leaderboard.png")
    if not frame.exists():
        pytest.skip("emulator frame not present")
    from src.config import SCREEN_2_BADGE_X_RANGE
    got = read_column(cv2.imread(str(frame)), SCREEN_2_BADGE_X_RANGE)
    assert not ({1, 2, 3} & set(got)), f"claimed a trophy row: {sorted(got)}"


def test_noise_is_declined_not_guessed():
    """The point of templates over OCR is that "I am not sure" is
    expressible. Random pixels must yield nothing rather than a confident
    digit -- a wrong rank is far more expensive than a missing one, because
    the caller acts on it."""
    rng = np.random.default_rng(0)
    noise = rng.integers(0, 255, (1080, 2340, 3), dtype=np.uint8)
    assert read_column(noise, BADGE_X) == {}


def test_a_clipped_row_declines_rather_than_inventing():
    """The row half-hidden under the header on a real frame: the bank must
    say nothing about it. Grid inference owns rows it cannot see properly."""
    path = FRAMES / "lost_rank34_135448.png"
    if not path.exists():
        pytest.skip("frame not present")
    img = cv2.imread(str(path))
    rank, _conf = read_row(img, 168, BADGE_X)   # rank 31, clipped by the header
    assert rank is None, f"invented {rank} from a clipped row"
