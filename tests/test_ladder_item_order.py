"""The "most built by server" card claims a purchase order. These pin down how
that order is decided, because the obvious method -- average each item's slot
-- gives the wrong answer in exactly the case that matters."""
from __future__ import annotations

from scripts.ladder_item_order import purchase_order, shown_items


def test_the_pairwise_vote_beats_a_confounded_average():
    """Among players who bought BOTH, B always comes before A. A still has the
    lower average slot, because many players who skipped B bought A first.
    The average would put A first; the players who actually faced the choice
    say B, and B must win."""
    both = [["x", "y", "b", "a"]] * 6             # everyone with both: b then a
    only_a = [["a", "x", "y"]] * 10               # a first when b is absent
    order, slot = purchase_order(both + only_a, ["a", "b"])
    assert slot["a"] < slot["b"]                  # the average is fooled...
    assert order == ["b", "a"]                    # ...the vote is not


def test_absence_of_evidence_is_not_a_tie():
    """Two items nobody built together get no pairwise points at all; they are
    ordered by their mean slot instead of being called level."""
    seqs = [["early", "z"]] * 5 + [["q", "late"]] * 5
    order, _ = purchase_order(seqs, ["late", "early"])
    assert order == ["early", "late"]


def test_a_repeated_item_keeps_its_first_slot():
    """A second copy (two Dorans, a rebuilt item) must not move the item late."""
    order, slot = purchase_order([["a", "b", "a"]] * 4, ["a", "b"])
    assert slot["a"] == 1.0
    assert order == ["a", "b"]


def test_the_six_shown_match_the_card_rule():
    """Five most-built non-boot items plus the top boots, as ladderConsensusBuild
    picks them -- the order is only ever claimed over what is on screen."""
    counted = [("trinity-force", 40), ("plated-steelcaps", 38), ("eclipse", 35),
               ("mercurys-treads", 30), ("deaths-dance", 30), ("steraks-gage", 20),
               ("black-cleaver", 18), ("guardian-angel", 10)]
    shown = shown_items(counted)
    assert shown is not None and len(shown) == 6
    assert shown[-1] == "plated-steelcaps"        # the first boots only
    assert "mercurys-treads" not in shown


def test_no_order_without_five_items():
    assert shown_items([("trinity-force", 40), ("eclipse", 35)]) is None
