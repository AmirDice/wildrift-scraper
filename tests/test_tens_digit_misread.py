"""The tens-digit misread: 3 reads as 5, 2 reads as 4, and a whole window
goes wrong together.

An overnight run of 50 champions lost position twice and churned three more
times, and every incident was this one bug. The rejected frames are on disk
and show a perfectly clean leaderboard; the scanner read them 20 ranks deep.

    lost_rank34_135448  screen 31-35  ->  scan 51-55
    lost_rank34_144350  screen 29-33  ->  scan 49-53

Cause: in this font a 3 and a 5 differ only by whether the glyph's top stroke
reads as closed, and the illumination flattening biases the LEADING digit --
the tens digit sits against ~90px of dark gutter, its local background
estimate comes out low, the glyph binarizes thicker, and the open top closes.
The units digit, flanked by the other glyph, survives: on one frame "33" read
as "53", the same glyph right and wrong in the same row.

Why the existing defences did not catch it: the whole window shares one
binarization, so it misreads TOGETHER and stays internally consecutive.
51,52,53 passes the chain filter exactly as well as 31,32,33 does. The hint
then correctly refuses the impossible window, which leaves the one badge that
happened to read right -- the "only 1 badge(s) read" in the logs -- and the
journey dies waiting for a list that was never loading.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import pytest

from src.ocr import scan_visible_ranks

BADGE_X = (985, 1155)
PITCH = 146.0
FRAMES = Path("data/debug_scans")

# (frame, hint the navigator held, true window on screen)
#
# One frame per incident. Each incident dumped two or three frames 45s apart
# and they scan identically -- that determinism is the point of the nudge in
# the navigator, and it is tested there rather than by carrying near-copies
# of a 1.8MB screenshot in the repo.
LIVE_FAILURES = [
    ("lost_rank34_135448.png", 34.0, (31, 35)),   # Kayle
    ("lost_rank34_144350.png", 34.0, (29, 33)),   # Leona
    # The frame that proved corroboration must accept a rival reading of a
    # row the chain already uses: y=740 read as "54" (which the chain took)
    # and as "34" (which the flattened pass got right). Screen shows 31-35;
    # rank 30's row is partially visible at the top and gets grid-filled.
    ("lost_rank34_044532.png", 34.0, (30, 34)),
]


@pytest.mark.parametrize("name,hint,truth", LIVE_FAILURES)
def test_misread_window_is_rescued(name: str, hint: float, truth: tuple[int, int]):
    """Every frame that cost a lost position must now read correctly."""
    path = FRAMES / name
    if not path.exists():
        pytest.skip(f"captured failure frame {name} not present")
    ranks, _pitch = scan_visible_ranks(
        cv2.imread(str(path)), BADGE_X, hint=hint, expected_pitch=PITCH)
    assert ranks, "scan returned nothing"
    assert (min(ranks), max(ranks)) == truth, (
        f"{name}: read {min(ranks)}-{max(ranks)}, screen shows {truth[0]}-{truth[1]}")


# The frame that proves the rescue must not be eager. Lucian rank 45: the
# scan read 32-36 and was RIGHT (the frame shows 33 Balance1, 34 Don,
# 35 hansel, 36), while the navigator's prediction had drifted to ~45 and
# Gemini "arbitration" answered 52-57. Nothing here may be rewritten.
RIGHT_ALL_ALONG = FRAMES / "lost_rank45_142447.png"


@pytest.mark.skipif(not RIGHT_ALL_ALONG.exists(), reason="failure frame not present")
def test_a_correct_scan_survives_a_stale_hint():
    ranks, _ = scan_visible_ranks(
        cv2.imread(str(RIGHT_ALL_ALONG)), BADGE_X, hint=45.0, expected_pitch=PITCH)
    assert (min(ranks), max(ranks)) == (32, 36), (
        f"rewrote a correct scan to {min(ranks)}-{max(ranks)}")


@pytest.mark.skipif(not RIGHT_ALL_ALONG.exists(), reason="failure frame not present")
def test_the_rescue_only_ever_reads_downward():
    """Same frame, but with a hint that a naive rescue would love: 54 sits
    exactly 20 above the true window, so a symmetric +/-20 rescue would
    happily rewrite 33-36 into 53-56 and land the run 20 rows away.

    It must not, because the misread has a direction. Thickening closes an
    open top (3 -> 5, 2 -> 4); nothing thins a 5 back into a 3. Of two
    readings 20 apart the lower one is always the true one."""
    ranks, _ = scan_visible_ranks(
        cv2.imread(str(RIGHT_ALL_ALONG)), BADGE_X, hint=54.0, expected_pitch=PITCH)
    assert max(ranks) < 45, f"shifted a window UPWARD to {min(ranks)}-{max(ranks)}"


@pytest.mark.skipif(not (FRAMES / LIVE_FAILURES[0][0]).exists(), reason="frame not present")
def test_templates_make_the_prediction_unnecessary():
    """With a digit bank the frame reads correctly with NO hint at all: the
    misread never happens, so there is nothing to rescue. This is the layer
    that matters -- the rescue below only exists for when the bank cannot
    answer."""
    ranks, _ = scan_visible_ranks(
        cv2.imread(str(FRAMES / LIVE_FAILURES[0][0])), BADGE_X, expected_pitch=PITCH)
    assert (min(ranks), max(ranks)) == (31, 35), f"unhinted read {sorted(ranks)}"


@pytest.mark.skipif(not (FRAMES / LIVE_FAILURES[0][0]).exists(), reason="frame not present")
def test_the_rescue_still_covers_a_missing_bank(monkeypatch):
    """Fall back to the OCR path (no bank on disk, an unbuilt device, a glyph
    the bank declines) and the tens-digit rescue must still stand behind it.
    Without a hint the raw misread shows through; with one it is corrected."""
    monkeypatch.setattr("src.rank_digits.templates", lambda: {})
    frame = cv2.imread(str(FRAMES / LIVE_FAILURES[0][0]))
    raw, _ = scan_visible_ranks(frame, BADGE_X, expected_pitch=PITCH)
    assert min(raw) >= 50, f"expected the raw OCR misread, got {sorted(raw)}"
    fixed, _ = scan_visible_ranks(frame, BADGE_X, hint=34.0, expected_pitch=PITCH)
    assert (min(fixed), max(fixed)) == (31, 35), f"rescue failed: {sorted(fixed)}"
