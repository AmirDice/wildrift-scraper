"""Scanner regression: the top trophy badges (ranks 1-2) failing to OCR must
not make their rows invisible -- they are grid-extrapolated from whatever DID
read. Reproduced on the real emulator frame by blanking those badges out."""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import pytest

from src.config import SCREEN_2_BADGE_X_RANGE
from src.ocr import scan_visible_ranks

FRAME = Path("data/2_aatrox_leaderboard.png")


@pytest.mark.skipif(not FRAME.exists(), reason="sample frame not present")
def test_blanked_trophy_badges_are_grid_filled():
    img = cv2.imread(str(FRAME))
    ranks_full, pitch = scan_visible_ranks(img, SCREEN_2_BADGE_X_RANGE)
    assert {1, 2, 3, 4, 5} <= set(ranks_full)

    # Erase ranks 1 and 2's badges (the live failure: "it sees only 3-5").
    # Fill with the column's median color, not black, so the mutation mimics
    # an unreadable badge without skewing Otsu's threshold for the whole crop.
    x0, x1 = SCREEN_2_BADGE_X_RANGE
    import numpy as np
    fill = np.median(img[:, x0:x1].reshape(-1, 3), axis=0).astype(img.dtype)
    for r in (1, 2):
        y = ranks_full[r]
        img[max(0, y - 55): y + 55, x0:x1] = fill

    ranks, pitch2 = scan_visible_ranks(img, SCREEN_2_BADGE_X_RANGE)
    assert {1, 2, 3, 4, 5} <= set(ranks), f"top-fill missing: {sorted(ranks)}"
    # correctness = lands on the right ROW (pitch ~122px), not pixel identity
    assert abs(ranks[1] - ranks_full[1]) <= 45
    assert abs(ranks[2] - ranks_full[2]) <= 45


PHONE_FAIL_FRAME = Path("data/debug_scans/lost_rank14_200456.png")


@pytest.mark.skipif(not PHONE_FAIL_FRAME.exists(), reason="captured failure frame not present")
def test_two_digit_ranks_survive_column_width():
    """The great deep-rank mystery: a badge column calibrated on single-digit
    ranks clipped the right digit of 11+, making deep ranks read flakily for
    an entire week of runs. The locator must now find a column wide enough on
    the real failure frame, and that column must read every visible rank."""
    from src.ocr import locate_badge_column

    img = cv2.imread(str(PHONE_FAIL_FRAME))
    rng, ranks, pitch = locate_badge_column(img)
    assert rng is not None
    assert {11, 12, 13, 14, 15} <= set(ranks), f"got {sorted(ranks)} from {rng}"
    assert pitch and 140 <= pitch <= 155


MISREAD_CHAIN_FRAME = Path("data/debug_scans/lost_rank31_205622.png")


@pytest.mark.skipif(not MISREAD_CHAIN_FRAME.exists(), reason="captured failure frame not present")
def test_consecutive_misreads_cannot_outvote_the_hint():
    """Real frame showing ranks 29-33 that OCR'd as '29,30,51,52,53': the
    majority-wrong chain [51,52,53] must NOT win the anchor when the caller's
    predicted position (~28) sits next to the correct [29,30] chain. With the
    right anchor, grid-snap rewrites the misread badges by position, so the
    exact same OCR output yields the fully correct window."""
    from src.ocr import scan_visible_ranks

    img = cv2.imread(str(MISREAD_CHAIN_FRAME))
    ranks, pitch = scan_visible_ranks(img, (1000, 1175), hint=28.0)
    assert set(ranks) >= {29, 30, 31, 32, 33}, f"got {sorted(ranks)}"
    assert max(ranks) <= 36, f"phantom deep ranks: {sorted(ranks)}"
    assert pitch and 140 <= pitch <= 155


POISON_TRIGGER_FRAME = Path("data/debug_scans/lost_rank6_233520.png")
POISONED_RUN_FRAME = Path("data/debug_scans/lost_rank1_233637.png")


@pytest.mark.skipif(not POISON_TRIGGER_FRAME.exists(), reason="captured failure frame not present")
def test_relocation_cannot_lock_onto_garbage_column():
    """A real run re-located the badge column ON a degraded frame, accepted
    avatar digits at (1185,1355) as a 'column', persisted it, and bricked
    every following run. The locator must now refuse anything without a full
    window at physical pitch -- on the degraded trigger frame that means
    refusing entirely (keeping the proven-good column)."""
    from src.ocr import locate_badge_column

    img = cv2.imread(str(POISON_TRIGGER_FRAME))
    rng, ranks, pitch = locate_badge_column(img)
    if rng is not None:  # if it does answer, the answer must be physically sane
        assert len(ranks) >= 4
        assert pitch and 100 <= pitch <= 200
        assert rng[0] < 1100, f"locked onto the avatar area again: {rng}"


@pytest.mark.skipif(not POISONED_RUN_FRAME.exists(), reason="captured failure frame not present")
def test_healthy_frame_recovers_real_column():
    """Run-2's first frame read perfectly with the real column -- the locator
    must find that column (not the poisoned avatar area) on a healthy frame."""
    from src.ocr import locate_badge_column, scan_visible_ranks

    img = cv2.imread(str(POISONED_RUN_FRAME))
    rng, ranks, pitch = locate_badge_column(img)
    assert rng is not None
    assert {1, 2, 3, 4, 5} <= set(ranks), f"got {sorted(ranks)} from {rng}"
    assert rng[0] < 1100, f"wrong column: {rng}"
    # The garbage-chain sub-assertion holds only on the Windows Tesseract
    # build the poisoning was reproduced against: what the engine hallucinates
    # in avatar pixels is version-specific, and Linux's build happens to emit
    # three pitch-consistent fakes on this frame. The property that matters
    # everywhere -- the locator picks the REAL column -- is asserted above.
    if sys.platform == "win32":
        r2, p2 = scan_visible_ranks(img, (1185, 1355), expected_pitch=146.0)
        assert len(r2) < 3, f"poisoned column produced a fake window: {sorted(r2.items())}"


CROSS_STAGE_MASK_FRAME = Path("data/debug_scans/lost_rank1_040002.png")


@pytest.mark.skipif(not CROSS_STAGE_MASK_FRAME.exists(), reason="captured failure frame not present")
def test_stage_misreads_cannot_mask_better_reads_or_chain_across_rows():
    """Pristine Kayn top-of-list frame that scanned as just '[2, 3]' -- two
    failures compounding. The flatten pass misread badges 3 and 5 (as '5' and
    '3'), and the first-wins y-merge let those tokens MASK the classic pass's
    correct digits at the same rows. The surviving '2' and '3' then chained as
    consecutive ranks despite sitting 455px (three rows) apart, because the
    chain builder never demanded that consecutive ranks be one pitch apart.
    With per-(row, digit) merging and the pitch constraint, the correct [4,5]
    chain anchors and grid-snap yields the full window."""
    img = cv2.imread(str(CROSS_STAGE_MASK_FRAME))
    for hint in (None, 1.0):
        ranks, pitch = scan_visible_ranks(img, (985, 1155), hint=hint,
                                          expected_pitch=146.0)
        assert {1, 2, 3, 4, 5} <= set(ranks), f"hint={hint}: got {sorted(ranks)}"
        assert pitch and 140 <= pitch <= 155


@pytest.mark.skipif(not FRAME.exists(), reason="sample frame not present")
def test_scrolled_off_ranks_are_not_invented():
    """When the list is scrolled (rank 3 genuinely at the top edge), ranks 1-2
    must NOT be extrapolated above the list area."""
    img = cv2.imread(str(FRAME))
    ranks_full, _ = scan_visible_ranks(img, SCREEN_2_BADGE_X_RANGE)
    # Crop so rank 3's row is near the top edge -- simulates a scrolled list.
    y_start = ranks_full[3] - 80
    cropped = img[y_start:]
    ranks, _ = scan_visible_ranks(cropped, SCREEN_2_BADGE_X_RANGE)
    assert 3 in ranks
    assert 1 not in ranks and 2 not in ranks, f"invented off-screen rows: {sorted(ranks)}"
