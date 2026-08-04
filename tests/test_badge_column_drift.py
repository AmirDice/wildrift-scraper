"""The badge column must never walk away from the device reference.

A live overnight run lost eleven champions to this: the relocation guard
compared each proposal against the CURRENT column, so the column ratcheted
(985,1155) -> (1060,1230) -> (1135,1305) in two hops that each overlapped
their predecessor by 95px. The final value sat on the player avatars, was
saved to calibration, and every champion afterwards read "only 1 badge".
"""
from __future__ import annotations

import json

import pytest


def overlap(a: tuple[int, int], b: tuple[int, int]) -> int:
    return min(a[1], b[1]) - max(a[0], b[0])


def accepted(proposal: tuple[int, int], reference: tuple[int, int]) -> bool:
    """The guard as shipped: judged against the immutable reference."""
    return overlap(proposal, reference) >= 0.7 * (reference[1] - reference[0])


REF = (985, 1155)


def test_the_live_ratchet_is_refused_at_every_step():
    """Both hops of the real failure must be blocked, not just the endpoint."""
    assert not accepted((1060, 1230), REF), "first hop would restart the ratchet"
    assert not accepted((1135, 1305), REF), "the avatar column must be refused"


def test_genuine_drift_is_still_allowed():
    """The real fix for clipped two-digit ranks moved the column ~30px; that
    kind of correction must still be possible or the scanner cannot self-heal."""
    assert accepted((1005, 1175), REF)
    assert accepted((965, 1135), REF)


def test_reference_is_present_and_sane_in_calibration():
    cal = json.loads(open("coords/calibration.json", encoding="utf-8").read())
    ref = cal.get("badge_x_ref")
    assert ref, "calibration must carry an immutable badge_x_ref"
    assert 100 <= ref[1] - ref[0] <= 260, f"implausible column width: {ref}"
    cur = (cal["badge_x0"], cal["badge_x1"])
    assert accepted(cur, tuple(ref)), (
        f"stored column {cur} has drifted from the reference {ref}")


@pytest.mark.parametrize("bogus", [(835, 1005), (1135, 1305), (1600, 1770), (0, 170)])
def test_other_screens_columns_are_refused(bogus):
    """Avatar digits, score column, and off-screen candidates all fail."""
    assert not accepted(bogus, REF)
