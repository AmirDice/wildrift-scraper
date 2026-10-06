from pathlib import Path
import cv2
import pytest
from src.profile_rank import parse_reference_name
from src.tiers import canonical_profile_rank, canonical_tier


def test_profile_reference_filename_carries_both_badges_and_counts():
    parsed = parse_reference_name("13x grandmaster, 2x sovereign.jpg")
    assert parsed is not None
    assert parsed.current == "Grandmaster"
    assert parsed.current_count == 13
    assert parsed.historical == "Sovereign"
    assert parsed.historical_count == 2


def test_profile_reference_allows_missing_current_count():
    parsed = parse_reference_name("diamond, 5x challenger.jpg")
    assert parsed is not None
    assert parsed.current == "Diamond"
    assert parsed.current_count is None
    assert parsed.historical == "Challenger"
    assert parsed.historical_count == 5


def test_profile_rank_does_not_apply_champion_board_floor():
    assert canonical_profile_rank("Emerald") == "Emerald"
    assert canonical_profile_rank("Platinum II") == "Platinum II"
    assert canonical_tier("Emerald") is None


def test_profile_rank_distinguishes_sovereign_and_challenger():
    assert canonical_profile_rank("Sovereign") == "Sovereign"
    assert canonical_profile_rank("Challenger") == "Challenger"


class TestBadgeSeasonCount:
    """The number stamped on each profile rank badge.

    A live extraction reported `current=Master (?)` for all 30 players while
    the figure was perfectly legible on screen. Two independent causes, both
    measured over 24 captured badges (0/20 correct before, 19/20 after).
    """

    FRAMES = Path("data/captures_na/garen_20261005_0809")

    def _frame(self, rank):
        path = self.FRAMES / f"{rank:03d}_profile.jpg"
        if not path.exists():
            pytest.skip(f"{path} not present")
        return cv2.imread(str(path))

    def test_the_token_crop_is_not_half_the_badge(self):
        """It used to take x .25-.78 and y .58-1.06 of the badge, so the one
        small disc sat in a field of ornate artwork and a digits-whitelisted
        Tesseract found nothing it trusted."""
        from src.profile_rank import _TOKEN_BOX
        ax0, ax1, ay0, ay1 = _TOKEN_BOX
        assert (ax1 - ax0) <= 0.50, "token crop is too wide"
        assert (ay1 - ay0) <= 0.40, "token crop is too tall"
        assert ay0 >= 0.70, "token crop starts too high up the badge"

    def test_both_polarities_are_tried(self):
        """THE bug, and it is invisible from one badge. Otsu picks one global
        threshold and the two badges sit on different grounds: the historical
        digit comes out white on black, while on the larger current badge the
        disc goes white and the digit is a black hole inside it. Searching
        only for bright glyphs read every historical count and not one
        current count."""
        import inspect
        from src import profile_rank
        src = inspect.getsource(profile_rank._badge_count)
        assert "for invert in (False, True)" in src

    def test_counts_read_off_the_captured_badges(self):
        """Hand-read off the badges themselves. `current` is 1 for every one
        of these players; `historical` varies, which is what makes it a real
        test rather than a constant."""
        from src.profile_rank import _badge_count, _candidate
        expected_historical = {1: 2, 2: 2, 4: 2, 6: 1, 7: 1, 8: 2, 11: 3}
        got = {}
        for rank, want in expected_historical.items():
            frame = self._frame(rank)
            found = _candidate(frame, historical=True)
            assert found is not None, f"rank {rank}: no historical badge"
            got[rank] = _badge_count(frame, found[2])
        assert got == expected_historical

    def test_the_current_badge_count_is_read_at_all(self):
        """The regression that started this: every current badge read "?"."""
        from src.profile_rank import _badge_count, _candidate
        reads = []
        for rank in (1, 2, 3, 4):
            frame = self._frame(rank)
            found = _candidate(frame, historical=False)
            assert found is not None, f"rank {rank}: no current badge"
            reads.append(_badge_count(frame, found[2]))
        assert reads == [1, 1, 1, 1], f"current counts read {reads}"
