"""Exact ladder rune-page aggregation."""

from scripts.build_ladder_pulse import _canonical_rune_page, _rune_page_key


def test_captured_runes_become_one_legal_complete_page():
    page = _canonical_rune_page([
        "Lethal Tempo", "Bone Plating", "Legend: Alacrity",
        "Brutal", "Cut Down",
    ])

    assert page == {
        "keystone": "Lethal Tempo",
        "primaryTree": "Precision",
        "minors": ["Brutal", "Cut Down", "Legend: Alacrity"],
        "flex": "Bone Plating",
    }
    assert _rune_page_key(page) == (
        "Lethal Tempo", "Precision", "Brutal", "Cut Down",
        "Legend: Alacrity", "Bone Plating")


def test_partial_or_structurally_invalid_page_is_not_counted():
    assert _canonical_rune_page([
        "Lethal Tempo", "Brutal", "Cut Down", "Legend: Alacrity",
    ]) is None
    assert _canonical_rune_page([
        "Brutal", "Lethal Tempo", "Cut Down", "Legend: Alacrity",
        "Bone Plating",
    ]) is None
