"""The player's own rank changes the advice, in both directions or not at all.

Dark Harvest is a different rune at Emerald than at Grandmaster: stacking it
requires winning skirmishes that are not guaranteed wins at lower ranks. The
site cannot verify a rank claim, so the middle option deliberately sends
NOTHING -- only the two ends are statements worth making to the model.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from web.build_advisor import SKILL_LEVEL  # noqa: E402


def test_the_default_is_silence():
    assert SKILL_LEVEL["average"] == ""


def test_high_skill_unlocks_execution_gated_choices_by_name():
    text = SKILL_LEVEL["high"]
    assert "Dark Harvest" in text
    assert "MASTER OR ABOVE" in text
    # the guard that keeps "high skill" from meaning "anything goes"
    assert "Incoherent picks are still wrong" in text


def test_developing_forbids_stack_or_nothing_patterns_by_name():
    text = SKILL_LEVEL["developing"]
    assert "no Dark Harvest" in text
    assert "EMERALD OR BELOW" in text


def test_unknown_values_fall_back_to_silence():
    """advise() clamps; the dict itself only holds the three real levels."""
    assert set(SKILL_LEVEL) == {"developing", "average", "high"}
