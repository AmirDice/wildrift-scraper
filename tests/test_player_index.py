"""The cross-board player index behind /player.

The per-champion files answer "who is best at Vayne". This answers the other
direction -- "what is this player good at" -- which only exists once the
boards are joined, because a strong player appears on several.

The join key is the display NAME. There is no account id anywhere in this
data: the boards print a name and sometimes a riot tag, nothing else. That is
a real limitation (two people sharing a name would merge) and the reason the
tag is carried through and shown.
"""
from __future__ import annotations

import json

import pytest

from scripts.export_captures import build_player_index, tag_hash


def payload(slug: str, players: list[dict]) -> dict:
    return {"champion": slug.title(), "slug": slug, "capturedAt": "2026-08-04",
            "players": players}


def row(rank: int, name: str, **kw) -> dict:
    base = {"r": rank, "p": name, "hidden": None, "s": 9000, "g": 100, "w": 55.0,
            "tag": None, "tier": None, "level": None, "build": None, "stats": None}
    base.update(kw)
    return base


def test_a_player_on_two_boards_becomes_one_record():
    idx = build_player_index([
        payload("vayne", [row(3, "Shenron", w=61.0)]),
        payload("jinx", [row(11, "Shenron", w=57.5)]),
    ])
    assert len(idx["players"]) == 1
    rec = idx["players"][0]
    assert rec["n"] == "Shenron"
    assert [e["s"] for e in rec["c"]] == ["vayne", "jinx"]
    assert [e["w"] for e in rec["c"]] == [61.0, 57.5]


def test_boosting_adverts_are_not_searchable():
    """The champion boards KEEP these rows, so the ladder stays a faithful
    mirror of the game, but the name is the advertisement -- making it
    findable is the exact thing the policy exists to prevent. They are absent
    from the index entirely rather than listed as "Name hidden"."""
    idx = build_player_index([
        payload("vayne", [
            row(1, "Name hidden", hidden=True),
            row(2, "Real Player"),
        ]),
    ])
    assert [p["n"] for p in idx["players"]] == ["Real Player"]


def test_champion_entries_are_ordered_by_rank():
    idx = build_player_index([
        payload("lux", [row(40, "Ranger")]),
        payload("zoe", [row(2, "Ranger")]),
        payload("amumu", [row(17, "Ranger")]),
    ])
    assert [e["r"] for e in idx["players"][0]["c"]] == [2, 17, 40]


def test_identity_is_carried_and_level_takes_the_highest():
    """Identity repeats per board and the boards were captured on different
    days, so the level differs between them. It only ever goes up, so the
    highest reading is the most recent truth."""
    idx = build_player_index([
        payload("vayne", [row(3, "Nova", tag="EUW", tier=None, level=210)]),
        payload("jinx", [row(9, "Nova", tag=None, tier="Challenger", level=237)]),
    ])
    rec = idx["players"][0]
    assert rec["th"] == tag_hash("EUW")
    assert rec["tier"] == "Challenger"
    assert rec["lv"] == 237


def test_no_plaintext_tag_is_ever_written():
    """Tags are a search key, not a published field.

    Hiding them in the UI is not enough: the index is a public JSON file, so
    shipping the tag would make it a downloadable, machine-readable tag
    directory -- worse than showing it on the page. Only the hash is stored,
    which keeps "search by #tag if you already know it" working while the file
    reveals nothing.
    """
    idx = build_player_index([
        payload("vayne", [row(3, "Nova", tag="SECRETTAG")]),
    ])
    rec = idx["players"][0]
    assert "t" not in rec, "a plaintext tag field came back"
    assert "SECRETTAG" not in json.dumps(idx), "the tag survived into the index"
    assert rec["th"] == tag_hash("SECRETTAG")


def test_tag_hash_folds_case_and_spacing():
    """Whatever someone types has to reach the same hash the export wrote."""
    assert tag_hash("EUW") == tag_hash(" euw ") == tag_hash("e u w")
    assert tag_hash("") is None and tag_hash(None) is None
    assert tag_hash("EUW") != tag_hash("NA1")


@pytest.mark.parametrize("tag,expected", [
    ("euw", "799fd668"),
    ("EUW", "799fd668"),
    ("alpha", "5d8b6dab"),
    ("NA1", "528f4ad3"),
    ("4893", "398369c1"),
])
def test_tag_hash_matches_the_client_implementation(tag: str, expected: str):
    """FNV-1a 32-bit, pinned to values verified against the browser side.

    The client recomputes this from whatever the user typed (tagHash in
    web-next/src/lib/player-index.ts). The two implementations are the only
    thing making tag search work, and if either drifts the failure is silent:
    every tagged search simply stops matching. So the constants are pinned
    here rather than asserted to be merely well-formed.
    """
    assert tag_hash(tag) == expected


def test_case_and_spacing_do_not_split_a_player():
    """Names are styled inconsistently between captures; folding the key stops
    one person becoming two records."""
    idx = build_player_index([
        payload("vayne", [row(3, "Alpha Rengo")]),
        payload("rengar", [row(35, "alpha rengo")]),
    ])
    assert len(idx["players"]) == 1
    assert len(idx["players"][0]["c"]) == 2


def test_unnamed_rows_are_skipped():
    idx = build_player_index([payload("vayne", [row(3, ""), row(4, "   ")])])
    assert idx["players"] == []


def test_players_on_more_boards_come_first():
    idx = build_player_index([
        payload("vayne", [row(3, "Multi"), row(4, "Single")]),
        payload("jinx", [row(9, "Multi")]),
    ])
    assert [p["n"] for p in idx["players"]] == ["Multi", "Single"]
