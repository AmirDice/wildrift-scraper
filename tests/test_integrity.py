"""Booster policy: catch the self-declared adverts, never a real player.

A false positive publicly implies a named human cheats, so the real-player
cases here are as important as the detection cases. Every name below is one
the scraper actually captured from the EU boards.
"""
from __future__ import annotations

from web.integrity import HIDDEN_LABEL, display_name, is_advertising_account


def test_flags_self_declared_boost_adverts():
    """Captured from live boards; each name sells the service in the name."""
    for name in ("Insta wrboost25", "Insta peaceboost", "Instawrboost011",
                 "Insta YushinWR", "insta jwlakdemir"):
        assert is_advertising_account(name), name


def test_never_flags_ordinary_players():
    """All captured from live boards. 'Carry' is a playstyle word, and
    'Instalock' is ordinary slang -- flagging either would accuse a real
    player of cheating on a public page."""
    for name in ("LetMeCarry", "Support Carry", "Instalock Yasuo", "Insight",
                 "Constantine", "The Last One", "Your Angel", "SKT T1 Mika",
                 "GarenForTheWin", "instinct"):
        assert not is_advertising_account(name), name


def test_blank_and_missing_names_are_safe():
    """Unreadable names (the OCR drops some CJK) must not trip the filter.
    Whitespace is left as-is here; data_loader owns name cleanup."""
    for name in (None, "", "   "):
        assert not is_advertising_account(name)
    assert display_name(None) == ""


def test_display_name_hides_only_adverts():
    assert display_name("Insta wrboost25") == HIDDEN_LABEL
    assert display_name("LetMeCarry") == "LetMeCarry"


def test_statistics_exclude_boosters_but_the_board_keeps_the_row():
    """The two surfaces differ on purpose: stats drop the account, the
    leaderboard keeps its rank with the name hidden so ranks stay
    contiguous."""
    from web.data_loader import load_leaderboard

    stats_df = load_leaderboard()
    board_df = load_leaderboard(include_boosters=True)
    if board_df.empty:
        return  # no scraped CSV in this checkout
    flagged = board_df["player_name"].apply(is_advertising_account)
    assert not stats_df["player_name"].apply(is_advertising_account).any()
    if flagged.any():
        assert len(board_df) > len(stats_df)
