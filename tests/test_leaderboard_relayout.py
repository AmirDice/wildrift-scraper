"""The 2026-09-25 leaderboard relayout, pinned against real captures.

These are the frames the new geometry was measured from, so they are the only
thing standing between a future edit and silently re-breaking champion
identity. The old champions-page tests could not cover this: they assert OCR
behaviour on frames whose champion NAME text the game has since removed.

Fixtures: data/new leaderboard/ (2340x1080, the resolution the coords are
measured at).
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import pytest

from src.icon_match import (
    _align_champions,
    leaderboard_state,
    champion_templates,
    read_build_icons,
    read_champion_portraits,
    read_selected_champion,
    scan_champion_rows_by_portrait,
    selected_champion_row,
)

FRAMES = Path("data/new leaderboard")
OVERVIEW = FRAMES / "screen1.jpg"
DETAIL = FRAMES / "screen2.jpg"
SWITCHED = FRAMES / "switchchampion.jpg"
BUILD = FRAMES / "build.jpg"


def test_new_rank_column_and_offline_tap_verification():
    from src.config import LEADERBOARD_LAYOUT, SCREEN_2_BADGE_X_RANGE
    from src.ocr import scan_visible_ranks
    from src.extract_frames import verify_taps
    ranks, pitch = scan_visible_ranks(_img(DETAIL), SCREEN_2_BADGE_X_RANGE)
    assert set(ranks) == {1, 2, 3, 4}
    assert 155 <= pitch <= 165
    entries = [{"rank": rank, "tap_y": y, "lb_frame": DETAIL.name,
                "leaderboard_layout": LEADERBOARD_LAYOUT}
               for rank, y in ranks.items()]
    statuses, anomalies = verify_taps(FRAMES, entries)
    assert statuses == {rank: "ok" for rank in ranks}
    assert not anomalies


def test_new_name_crop_reads_ascii_player():
    from src.config import LEADERBOARD_LAYOUT, player_name_region
    from src.ocr import read_player_name
    assert read_player_name(_img(DETAIL), player_name_region(442, LEADERBOARD_LAYOUT)) == "TruffleKid"

#: What a human reads off the captures, top to bottom.
EXPECTED_COLUMN = ["Xin Zhao", "Hecarim", "Kayn", "Graves", "Pantheon"]

pytestmark = pytest.mark.skipif(
    not OVERVIEW.exists(), reason="new-layout capture frames not present")


def _img(p: Path):
    im = cv2.imread(str(p))
    assert im is not None, f"could not read {p}"
    return im


# --- champion identity -----------------------------------------------------

def test_every_champion_icon_maps_to_a_canonical_name():
    """All 141 shipped icons must be reachable.

    Seven were not, and silently: the filenames drop apostrophes (kaisa,
    khazix, chogath, ksante, kogmaw, velkoz) while a hyphenating slug produces
    kai-sa, so those champions had no template at all and could never be
    identified. Nunu carries an HTML-escaped ampersand on top of that.
    """
    files = [f for f in (Path("web-next/public/champions")).iterdir()
             if f.suffix.lower() in (".png", ".webp", ".jpg", ".jpeg")]
    tpl = champion_templates()
    assert len(tpl) == len(files), (
        f"{len(files) - len(tpl)} icons did not map to a canonical name")
    for awkward in ("Kai'Sa", "Kha'Zix", "Cho'Gath", "K'Sante",
                    "Kog'Maw", "Vel'Koz", "Nunu & Willump"):
        assert awkward in tpl, f"{awkward} has no template"


@pytest.mark.parametrize("frame", [OVERVIEW, DETAIL, SWITCHED])
def test_all_five_champion_portraits_resolve(frame):
    rows = read_champion_portraits(_img(frame), "switcher")
    got = [r["champion"] for r in rows]
    assert got == EXPECTED_COLUMN, f"{frame.name}: {got}"


@pytest.mark.parametrize("frame", [OVERVIEW, DETAIL, SWITCHED])
def test_portrait_matches_are_confident_not_lucky(frame):
    """A match that wins by a hair is the failure mode worth guarding.

    A naive 16x16 correlation got Kayn and Graves wrong at gaps of 0.03 and
    0.06. The masked circular comparison this module already used for runes
    separates every row by more than 0.30.
    """
    for r in read_champion_portraits(_img(frame), "switcher"):
        assert r["score"] >= 0.80, r
        assert r["gap"] >= 0.30, r


def test_scan_returns_the_shape_the_old_ocr_scan_returned():
    """Drop-in contract: [(row_centre_y, name_or_None)] top to bottom."""
    slots = scan_champion_rows_by_portrait(_img(OVERVIEW), "overview")
    assert [n for _y, n in slots] == EXPECTED_COLUMN
    ys = [y for y, _n in slots]
    assert ys == sorted(ys)
    pitches = {ys[i + 1] - ys[i] for i in range(len(ys) - 1)}
    assert pitches == {158}, f"row pitch drifted: {pitches}"


# --- selection and screen state --------------------------------------------

def test_overview_has_no_selection():
    assert selected_champion_row(_img(OVERVIEW)) is None
    assert read_selected_champion(_img(OVERVIEW)) is None


def test_detail_reports_the_highlighted_champion():
    assert selected_champion_row(_img(DETAIL)) == 0
    assert read_selected_champion(_img(DETAIL)) == "Xin Zhao"


def test_switching_champion_moves_the_selection():
    """The switcher column changes champion in place, without backing out."""
    assert selected_champion_row(_img(SWITCHED)) == 1
    assert read_selected_champion(_img(SWITCHED)) == "Hecarim"


@pytest.mark.parametrize("frame,expected", [
    (OVERVIEW, "overview"),
    (DETAIL, "detail"),
    (SWITCHED, "detail"),
    (BUILD, None),          # the build popup is not a leaderboard
])
def test_leaderboard_state(frame, expected):
    assert leaderboard_state(_img(frame)) == expected, frame.name


def test_build_popup_is_not_mistaken_for_a_leaderboard():
    """The page test must reject non-leaderboard screens outright.

    This is the direction that actually hurts: a false positive tells the
    recovery loop it has arrived, and it then taps a champion row that is not
    there.
    """
    assert leaderboard_state(_img(BUILD)) is None


# --- the build popup, which the relayout did NOT move ----------------------

def test_build_popup_geometry_survived_the_relayout():
    """Spells, runes and items all still read, at full confidence."""
    r = read_build_icons(_img(BUILD))
    assert r["spells"] == ["Smite", "Flash"]
    assert r["runes"] == ["Phase Rush", "Triumph", "Cut Down",
                          "Legend: Bloodline", "Sudden Impact"]
    assert r["items"] == ["Immortal Treads", "Trinity Force", "Serpent's Fang",
                          "Serylda's Grudge", "Sundered Sky",
                          "Maw of Malmortius"]
    for kind in ("spells", "runes", "items"):
        for name, score, _gap in r["_confidence"][kind]:
            assert name != "?", f"{kind}: unresolved slot"
            assert score >= 0.60, f"{kind}: {name} scored {score}"


# --- coordinates -----------------------------------------------------------

def test_coordinate_files_match_the_measured_geometry():
    rows = [284, 442, 600, 758, 916]
    s1 = json.loads(Path("coords/screen_1.json").read_text("utf-8"))["points"]
    assert [s1[f"row_{i + 1}"]["y"] for i in range(5)] == rows
    s2 = json.loads(Path("coords/screen_2.json").read_text("utf-8"))["points"]
    assert [s2[f"player_row_{i + 1}"]["y"] for i in range(4)] == rows[:4]
    assert [s2[f"champion_col_{i + 1}"]["y"] for i in range(5)] == rows
    s3 = json.loads(Path("coords/screen_3.json").read_text("utf-8"))["points"]
    # The rail replaced the mini profile popup; all three share an x.
    assert {s3[k]["x"] for k in ("like", "build", "profile")} == {2165}
    assert s3["profile"]["y"] > s3["build"]["y"] > s3["like"]["y"]


def test_champion_tap_points_land_on_the_portraits_they_name():
    """The coordinates and the matcher must agree about which row is which.

    If they drift apart the scraper taps row 4 believing it is Graves while
    the matcher reads row 4 as someone else, and every build after that is
    filed under the wrong champion. Compared through the real pipeline, not a
    hand crop: a hand crop skips the alignment pass, and on this very frame
    four pixels took Graves from 0.411 with a 0.054 gap (an honest "?") to
    0.939 with a 0.635 gap.
    """
    rows = read_champion_portraits(_img(DETAIL), "switcher")
    pts = json.loads(Path("coords/screen_2.json").read_text("utf-8"))["points"]
    for i, expected in enumerate(EXPECTED_COLUMN, 1):
        tap_y = pts[f"champion_col_{i}"]["y"]
        row = rows[i - 1]
        assert row["champion"] == expected, f"champion_col_{i}: {row}"
        # The tap must land inside the row the matcher just identified.
        assert abs(row["y"] - tap_y) <= 45, (
            f"champion_col_{i} taps y={tap_y} but row centre is {row['y']}")


def test_portrait_geometry_needs_no_large_runtime_correction():
    """Alignment should be polishing, not rescuing.

    A large residual means the nominal constants are wrong, and the search
    only spans +/-4, so a drift past that stops being recoverable at all.
    """
    for frame, layout in ((OVERVIEW, "overview"), (DETAIL, "switcher"),
                          (SWITCHED, "switcher")):
        dy, dx = _align_champions(_img(frame), layout, 1.0, 1.0)
        assert abs(dy) <= 2 and abs(dx) <= 2, f"{frame.name}: ({dy}, {dx})"
