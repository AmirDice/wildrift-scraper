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
