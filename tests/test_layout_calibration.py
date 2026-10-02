"""Calibration migration and backwards-compatible capture geometry."""
import pytest

from src.config import (
    LEADERBOARD_LAYOUT, player_name_region, resolve_badge_calibration,
)


def test_stale_geometry_is_replaced_without_mutating_other_settings():
    cal = {"badge_x0": 985, "badge_x1": 1155,
           "badge_x_ref": [985, 1155], "fling_rows": 11.9,
           "profile_name": "wrtruemeta"}
    current, ref, update = resolve_badge_calibration(cal)
    assert current == ref == (795, 870)
    assert update["leaderboard_layout"] == LEADERBOARD_LAYOUT
    assert cal["badge_x_ref"] == [985, 1155]
    merged = {**cal, **update}
    assert merged["fling_rows"] == 11.9
    assert merged["profile_name"] == "wrtruemeta"


def test_explicit_override_replaces_stale_reference():
    cal = {"badge_x_ref": [985, 1155], "leaderboard_layout": LEADERBOARD_LAYOUT}
    current, ref, _ = resolve_badge_calibration(cal, "790,875")
    assert current == ref == (790, 875)


def test_drift_cannot_move_trusted_reference():
    current, ref, _ = resolve_badge_calibration({
        "leaderboard_layout": LEADERBOARD_LAYOUT,
        "badge_x0": 1060, "badge_x1": 1230, "badge_x_ref": [795, 870],
    })
    assert current == ref == (795, 870)


@pytest.mark.parametrize("value", ["oops", "10", "20,10", "-1,50", "0,9999", "1,2,3"])
def test_invalid_override_rejected(value):
    with pytest.raises(ValueError):
        resolve_badge_calibration({}, value)


def test_name_regions_preserve_archived_captures():
    assert player_name_region(284, LEADERBOARD_LAYOUT) == (1020, 244, 275, 40)
    assert player_name_region(246) == (1328, 196, 358, 53)
