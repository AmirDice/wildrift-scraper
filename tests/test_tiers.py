"""Ranked tier: trust the reading, or publish nothing.

Two failures, both invisible on the page because a wrong tier renders exactly
like a right one.

The popup card animates in, so a screenshot taken a beat early catches it
before the tier line paints: 71 of 686 captured players had no tier at all.
The profile's stats page prints the same tier and is already captured, so the
fallback answers from there.

And a player with no current ranked placement shows their ADVENTURE-mode rank
in the same slot. That produced Iron IV and Gold II on champion leaderboards
-- 26 of 686 -- which cannot be real: these are the top 50 players on a
champion and nobody below Diamond is on that list. So a sub-Diamond reading is
evidence the game showed a different ladder, not evidence of a Gold player.
"""
from __future__ import annotations

import pytest

from src.tiers import canonical_tier, resolve_tier


@pytest.mark.parametrize("raw", [
    "Grandmaster III", "Master I", "Challenger", "Sovereign", "Diamond II",
])
def test_credible_tiers_pass_through(raw: str):
    assert canonical_tier(raw) == raw


@pytest.mark.parametrize("raw", ["Iron IV", "Bronze I", "Silver II", "Gold II",
                                 "Platinum IV", "Emerald II"])
def test_adventure_ranks_are_dropped(raw: str):
    """Every one of these was really in the captured data."""
    assert canonical_tier(raw) is None


@pytest.mark.parametrize("raw,want", [
    ("Challenger: Peer...", "Challenger"),
    ("Challenger: Lege...", "Challenger"),
    ("Sovereign: Ragn...", "Sovereign"),
    ("Challenger: Rift ", "Challenger"),
])
def test_truncated_titles_keep_their_tier(raw: str, want: str):
    """High tiers carry a title after a colon and a narrow crop truncates it.
    Without stripping the title these fail to parse, and the sub-Diamond
    floor would then discard real Challengers -- the fix eating the data it
    was meant to protect."""
    assert canonical_tier(raw) == want


@pytest.mark.parametrize("raw", [
    "Legendary Grandmaster IV", "Legendary Master III", "Legendary Commander II",
    "Legendary Challenger IV",
])
def test_the_legendary_ladder_is_never_floored(raw: str):
    """The Legendary queue runs its own ladder above the main one. Its names
    must survive whatever follows 'Legendary'."""
    assert canonical_tier(raw) == raw


@pytest.mark.parametrize("raw", [None, "", "   ", "II", "error", "..."])
def test_unreadable_values_become_nothing(raw):
    """A bare division names no ladder: unreadable, not low. None means 'we
    do not know', which the site renders as a blank."""
    assert canonical_tier(raw) is None


def test_stats_page_answers_when_the_popup_had_not_painted():
    assert resolve_tier(None, "Grandmaster II") == "Grandmaster II"
    assert resolve_tier("", None, "Master I") == "Master I"


def test_the_popup_wins_when_it_has_an_answer():
    assert resolve_tier("Challenger", "Master I") == "Challenger"


def test_the_fallback_cannot_smuggle_in_an_adventure_rank():
    """Each source is canonicalised on its own. A stats page showing Gold
    behind a blank popup must still yield nothing, or the fallback would
    reintroduce exactly what the floor exists to remove."""
    assert resolve_tier(None, "Gold II") is None
    assert resolve_tier(None, "Gold II", "Grandmaster I") == "Grandmaster I"
