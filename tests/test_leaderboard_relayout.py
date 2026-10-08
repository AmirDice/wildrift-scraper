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

from src.extract_frames import _BUILD_NAME_BOX, _PROFILE_NAME_BOX, _PROFILE_TAG_BOX
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


@pytest.mark.parametrize("shift", [10, 28])
def test_portrait_matcher_follows_a_vertically_shifted_carousel(shift):
    """The game moves the five-row strip while it settles or is mid-scroll.

    The October NA run produced both offsets in real frames.  A +/-4 search
    cropped adjacent portraits together, losing Rengar and reading Wukong as
    Warwick.  Circle-centre alignment must recover the actual row positions
    and keep both matching and selection tied to those positions.
    """
    import numpy as np

    source = _img(DETAIL)
    moved = np.zeros_like(source)
    moved[:-shift] = source[shift:]
    rows = read_champion_portraits(moved, "switcher")
    assert [r["champion"] for r in rows] == EXPECTED_COLUMN
    assert all(abs(r["y"] - (nominal - shift)) <= 3
               for r, nominal in zip(rows, (282, 440, 598, 756, 914)))
    assert selected_champion_row(moved) == 0
    assert read_selected_champion(moved) == "Xin Zhao"


# --- the badge column, after the 2026-10-05 NA run scanned almost nothing ---
#
# That run read "only 1 badge" on frame after frame and lost its position
# repeatedly. Three independent causes, all pinned below. The frames it
# rejected live in data/debug_scans/, which is gitignored, so these assert
# against screen2.jpg -- the tracked capture the layout was measured from,
# which happens to carry all three.


def test_badge_column_is_scanned_only_where_the_ranked_rows_are():
    """Outside the ranked rows the column holds digits that are not ranks.

    ABOVE it the relayout put a "Server" dropdown, and the digit bank matches
    that capital S as a 5 with margin to spare. BELOW it your own row reads
    "Top N%", which for most accounts puts a real digit in the badge font in
    the badge column. Neither is a rank, and nothing about either glyph says
    so -- only position does.
    """
    from src.config import SCREEN_2_BADGE_X_RANGE, SCREEN_LIST_Y_RANGE
    from src.rank_digits import read_column
    img = _img(DETAIL)

    lo, hi = SCREEN_LIST_Y_RANGE
    full = read_column(img, SCREEN_2_BADGE_X_RANGE, (0, img.shape[0]))
    phantoms = {r: y for r, y in full.items() if not lo <= y <= hi}
    assert phantoms, (
        "the unbounded scan found nothing outside the list, so this frame no "
        f"longer demonstrates why the bound exists: {full}")

    bounded = read_column(img, SCREEN_2_BADGE_X_RANGE, SCREEN_LIST_Y_RANGE)
    assert set(bounded) == {4}, f"expected just the plain-font rank 4: {bounded}"
    assert abs(bounded[4] - 758) <= 6
    # The phantom is not merely extra: it collides with a real rank, and the
    # scanner keeps one y per rank, so the fake position wins on sort order
    # and the real row loses its tap target.
    assert set(phantoms) & {1, 2, 3, 4, 5}, (
        f"phantoms no longer collide with a plausible rank: {phantoms}")


def test_avatar_ring_does_not_swallow_the_row_it_sits_beside():
    """The column is wide enough for a two-digit rank, so its right edge
    clips the gold ring of the portrait next to it. That arc segments as a
    tall thin sliver on the SAME row as the digit; the row then reads as a
    two-glyph number, the sliver matches no template, and the entire row is
    dropped. A legible "4" at 0.95 confidence yielded no rank at all."""
    from src.config import SCREEN_2_BADGE_X_RANGE, SCREEN_LIST_Y_RANGE
    from src.rank_digits import MAX_GLYPH_ASPECT, _bright_mask, read_column
    img = _img(DETAIL)
    assert 4 in read_column(img, SCREEN_2_BADGE_X_RANGE, SCREEN_LIST_Y_RANGE)

    # The sliver is really there -- this is not a frame that happens to lack it.
    y0, y1 = SCREEN_LIST_Y_RANGE
    gray = cv2.cvtColor(img[y0:y1, SCREEN_2_BADGE_X_RANGE[0]:SCREEN_2_BADGE_X_RANGE[1]],
                        cv2.COLOR_BGR2GRAY)
    mask = _bright_mask(gray).astype("uint8")
    n, _lbl, stats, _c = cv2.connectedComponentsWithStats(mask, connectivity=8)
    slivers = [i for i in range(1, n)
               if stats[i, cv2.CC_STAT_HEIGHT]
               > MAX_GLYPH_ASPECT * stats[i, cv2.CC_STAT_WIDTH]
               and stats[i, cv2.CC_STAT_HEIGHT] >= 18]
    assert slivers, "no sliver in this frame -- the test no longer proves anything"


def test_one_bright_row_cannot_blind_the_others():
    """The list panel is translucent over the champion's splash art, so the
    background behind the column is not one surface: measured down a single
    frame it ran mean 40 behind one row and mean 148 behind another, with the
    numerals a flat ~190 throughout. A single threshold for the whole column
    is then set by whichever rows the art lit up, and the quiet rows fall
    under it."""
    from src.config import SCREEN_2_BADGE_X_RANGE as BAND, SCREEN_LIST_Y_RANGE
    img = _img(DETAIL)
    x0, x1 = BAND
    means = [cv2.cvtColor(img[cy - 45:cy + 45, x0:x1],
                          cv2.COLOR_BGR2GRAY).mean()
             for cy in (284, 442, 600, 758)]
    assert max(means) - min(means) > 40, (
        f"rows no longer differ enough to prove the point: {means}")

    from src.ocr import scan_visible_ranks
    ranks, pitch = scan_visible_ranks(img, BAND, y_range=SCREEN_LIST_Y_RANGE)
    assert {1, 2, 3, 4} <= set(ranks), f"lost rows to the gradient: {sorted(ranks)}"
    assert pitch and 150 <= pitch <= 170


# --- the selection border, after the 2026-10-05 carousel skipped champions ---


def _faded(img, alpha=0.15):
    """The frame as the game draws it mid-transition: every channel pulled
    toward white together.

    A uniform blend is HARSHER on the border than the real thing -- the game
    fades the background while the gold border stays saturated, so the two
    captured failures actually scored HIGHER than a clean frame (0.069 against
    0.056). This models only the mechanism that broke the old test: blue rises
    with everything else, so an absolute ceiling on blue stops holding.
    """
    import numpy as np
    return np.clip(img.astype("float32") * (1 - alpha) + 255.0 * alpha,
                   0, 255).astype("uint8")


def test_selection_survives_the_between_champion_fade():
    """The carousel's champion switch is gated on seeing the selection, and
    the game fades the whole screen white between champions. The old test
    required `b < 110`, which that fade breaks while the border is still
    plainly gold on screen: two frames from the 2026-10-05 run scored 0.0029
    and 0.0032 against a 0.0040 threshold, each the ONLY gold-bearing row of
    five, each rejected. The carousel read that as "the tap did not select",
    backed out, and skipped the champion."""
    from src.icon_match import selected_champion_row, read_selected_champion
    clean = _img(SWITCHED)
    row, champ = selected_champion_row(clean), read_selected_champion(clean)
    assert row is not None and champ

    faded = _faded(clean)
    assert selected_champion_row(faded) == row, "lost the selection to the fade"
    assert read_selected_champion(faded) == champ


def test_the_fade_does_not_invent_a_selection_on_the_overview():
    """Loosening the gold test must not cost the state test. The overview has
    no selection at all, and `leaderboard_state` tells the two apart purely by
    whether a row is highlighted -- so a false positive here would make the
    carousel think it is already on a champion."""
    from src.icon_match import leaderboard_state, selected_champion_row
    overview = _img(OVERVIEW)
    assert selected_champion_row(overview) is None
    assert leaderboard_state(overview) == "overview"
    assert selected_champion_row(_faded(overview)) is None
    assert leaderboard_state(_faded(overview)) == "overview"


def test_the_build_popup_still_reads_as_no_selection():
    """The popup covers the switcher and carries gold trim of its own. It is
    the only frame with non-zero gold outside a real selection, and under the
    OLD threshold it cleared the bar by 0.0002 -- a margin that was never
    real. The current threshold sits about 5x above it."""
    from src.icon_match import SELECTION_MIN_GOLD, selected_champion_row
    assert selected_champion_row(_img(BUILD)) is None
    assert SELECTION_MIN_GOLD >= 0.015


# --- the identity crops, after an extraction resolved 2 of 30 names ---


def _ink_band(img, x0, x1, y0, y1):
    """(first, last) row of the DOMINANT line of text in the window.

    Not "every row with ink": the build card sits on splash art and carries a
    "Rank: N" line below the name, so a plain ink test returns the whole
    window. Growing out from the peak row while ink holds above a quarter of
    it isolates the one bright line the crop is aimed at.
    """
    import numpy as np
    g = cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY).astype("float32")
    bg = cv2.GaussianBlur(g, (0, 0), sigmaX=15)
    ink = ((g - bg) > 10).sum(axis=1).astype("float32")
    if not ink.max():
        return None
    peak = int(ink.argmax())
    cut = ink[peak] * 0.25
    a = b = peak
    while a > 0 and ink[a - 1] >= cut:
        a -= 1
    while b < len(ink) - 1 and ink[b + 1] >= cut:
        b += 1
    return y0 + a, y0 + b


def test_build_name_box_contains_the_whole_glyph():
    """It used to end 3px into the bottom of the text.

    Clipping the foot of a glyph is not a small error: it turns the OCR into
    a read of the TOP HALF of each letter, which collapses whole confusion
    sets. On this fixture the old box read the name's "D" as an "N"; across a
    30-rank extraction it produced l->i, g->c, y->v, z->7, J->l, B->p and
    2->?, and the build card resolved 4 of 30 names.
    """
    img = _img(BUILD)
    x0, y0, x1, y1 = _BUILD_NAME_BOX
    band = _ink_band(img, x0, x1, y0 - 60, y1 + 60)
    assert band is not None, "no text found near the build name box"
    assert y0 <= band[0] + 2, (
        f"box starts at {y0}, below the glyph tops at {band[0]}")
    # The foot is the part that matters. 6px of slack because this fixture's
    # name is CJK, which sits taller than the Latin caps the box is sized for
    # (measured 845-848 across the captures) -- the old box ended at 845 and
    # fails this.
    assert y1 >= band[1] - 6, (
        f"box ends at {y1}, cutting the glyph feet at {band[1]}")


def test_build_name_reads_off_the_tracked_capture():
    """The Latin half of this fixture's name, as a guard on the crop above.
    The CJK half is expected to garble; that is what the model fallback is
    for, and asserting it would pin a failure rather than a behaviour."""
    from src.extract_frames import _read_build_name
    got = (_read_build_name(_img(BUILD)) or "").upper()
    assert "DADDY" in got, f"build name did not survive the crop: {got!r}"


def test_profile_name_and_tag_crops_do_not_overlap():
    """They used to: name y 100-158 against tag y 148-202, so the tag read
    was fed the bottom of the name. The tag box is deliberately TALL because
    the tag's row is not fixed -- y~171 for most players, y~213 for others --
    but it must still start below the name."""
    assert _PROFILE_NAME_BOX[3] <= _PROFILE_TAG_BOX[1], (
        f"name box {_PROFILE_NAME_BOX} overlaps tag box {_PROFILE_TAG_BOX}")
    # Both crops stop short of the panel's gold right border, which OCRs as a
    # trailing "|" and was the junk on "ColoneliMustang |" and "ALGAGoD |".
    assert _PROFILE_NAME_BOX[2] <= 470 and _PROFILE_TAG_BOX[2] <= 470


def test_paddle_warning_is_not_repeated_per_crop():
    """One extraction run printed the identical "PaddleOCR unavailable" line
    50+ times, burying the identity output under it. A missing package does
    not appear mid-process, so it is established once."""
    import src.ocr as ocr_mod
    seen = set(ocr_mod._PADDLE_WARNED)
    try:
        for _ in range(5):
            ocr_mod._warn_once("[ocr] test-only message")
        assert len(ocr_mod._PADDLE_WARNED) == len(seen) + 1
    finally:
        ocr_mod._PADDLE_WARNED.discard("[ocr] test-only message")


# --- which of the two name crops to believe ---


def test_a_weaker_second_witness_cannot_overrule_the_better_engine():
    """When the two crops are read by DIFFERENT engines they stop being two
    views of the same question.

    The build card is on Tesseract, which cannot read Korean at all. Asked to
    arbitrate it produced "LHT- Cj AroH" against PaddleOCR's correct reading,
    and because that garbage is ASCII it PASSED the usability heuristic while
    the right answer failed it -- so the wrong name was stored. Measured, the
    corroborating path scored 21/30 against 27/30 for trusting the better
    engine outright.
    """
    from src.extract_frames import pick_identity
    korean = "내가 더 잘해"
    assert pick_identity(korean, "LHT- Cj AroH",
                         profile_engine="paddle") == (korean, "profile")
    # The build card still answers when the profile crop yields nothing.
    assert pick_identity(None, "DARKDRAGON",
                         profile_engine="paddle") == ("DARKDRAGON", "build")
    # ...and the same-engine path keeps corroborating, so the change is scoped.
    assert pick_identity(korean, "LHT- Cj AroH")[0] != korean


def test_corroborated_non_latin_names_are_not_thrown_away():
    """Two crops agreeing beats the single-read ASCII heuristic.

    _usable_ocr_name rejects a low ASCII share because TESSERACT garbles CJK.
    Once PaddleOCR is configured for the script both crops read the Korean
    names exactly, and that rule was discarding two perfect reads that agreed
    with each other: a live extraction returned them as unresolved.
    """
    from src.extract_frames import pick_identity, _usable_ocr_name
    for name in ("\uB0B4\uAC00 \uB354 \uC798\uD574", "\uBC18\uC9C0\uD558\uC758 \uC81C\uC655"):
        assert not _usable_ocr_name(name), (
            "this name is supposed to fail the single-read heuristic, "
            "otherwise the test proves nothing")
        assert pick_identity(name, name) == (name, "profile")


def test_a_lone_unreadable_script_still_goes_to_the_model():
    """Corroboration is the whole licence here. One crop reading a script the
    other could not is NOT enough, because nothing else distinguishes it from
    a confident misread."""
    from src.extract_frames import pick_identity
    assert pick_identity("\u4F18\u96C5\u6C38\u4E0D\u8FC7\u65F6", "qr HE SK AN TT AY")[1] == "none"


def test_genuine_disagreement_still_escalates():
    """The corroboration override must not turn into "accept anything". The
    build card dropping a letter is exactly what the second witness is for."""
    from src.extract_frames import pick_identity
    assert pick_identity("Lokij88", "LOKI88") == (None, "disagree")


def test_agreement_keeps_the_profile_capitalisation():
    """The build card uppercases, so the profile is the one worth storing."""
    from src.extract_frames import pick_identity
    assert pick_identity("ColonellMustang", "COLONELLMUSTANG") == (
        "ColonellMustang", "profile")
    assert pick_identity(None, "DARKDRAGON") == ("DARKDRAGON", "build")


def test_profile_name_crop_prefers_the_better_engine():
    """The per-crop split: the name crop asks PaddleOCR first, the stats strip
    does not.

    Reading it as a low-confidence FALLBACK cannot work, because Tesseract
    does not flag its own errors here. Over 60 captured name crops its
    confidence was 46-96 when right and 8-92 when wrong, and 10 of 16 wrong
    reads cleared the threshold -- it catches script failure (CJK scored
    8-32) and is blind to character failure ("Dartanan" at 92). No threshold
    separates those, so the only way to get the better engine onto this crop
    is to ask it first.
    """
    from src.extract_frames import IDENTITY_ENGINE
    assert IDENTITY_ENGINE in ("paddle", "tesseract")


def test_a_missing_paddle_degrades_the_name_read_instead_of_failing():
    """The optional backend is optional. With it absent the name crop has to
    fall back to Tesseract, not take the extraction down with it."""
    import numpy as np
    import src.ocr as ocr_mod
    from src.extract_frames import _PROFILE_NAME_BOX, _scaled_region
    img = np.zeros((1080, 2340, 3), dtype="uint8")
    img[:] = 30
    cv2.putText(img, "Testname", (200, 160), cv2.FONT_HERSHEY_SIMPLEX,
                1.2, (240, 240, 240), 3)
    broken = dict(ocr_mod._PADDLE_ENGINES)
    missing = ocr_mod._PADDLE_MISSING
    try:
        ocr_mod._PADDLE_ENGINES.clear()
        ocr_mod._PADDLE_MISSING = "simulated: backend not installed"
        got = ocr_mod.read_player_name(
            img, _scaled_region(img, _PROFILE_NAME_BOX), prefer="paddle")
    finally:
        ocr_mod._PADDLE_ENGINES.update(broken)
        ocr_mod._PADDLE_MISSING = missing
        ocr_mod._PADDLE_WARNED.discard(
            "[ocr] PaddleOCR unavailable (simulated: backend not installed); "
            "reading names with Tesseract for this run")
    assert got and "est" in got, f"Tesseract fallback produced {got!r}"


def test_a_scrolled_switcher_column_still_resolves():
    """The column is not pinned to the calibrated grid.

    While the list settles, and after a partial scroll, the same five rows sit
    10-28px above it. A +/-4 template search cannot reach that, so it crops
    two portraits together -- which is the WORST failure mode, because it
    yields a confident wrong champion rather than an honest miss: a live run
    read Wukong as Warwick and started capturing under the wrong name.
    """
    from src.icon_match import _align_champions, read_champion_portraits
    frame = Path("data/debug_scans/lost_rank0_113542.png")
    if not frame.exists():
        pytest.skip(f"{frame} not present")
    image = cv2.imread(str(frame))
    h, w = image.shape[:2]
    dy, _dx = _align_champions(image, "switcher", h / 1080.0, w / 2340.0)
    assert dy <= -15, f"this frame is supposed to be badly scrolled, got dy={dy}"
    rows = read_champion_portraits(image, "switcher")
    named = [r["champion"] for r in rows]
    assert named == ["Rengar", "Karma", "Nunu & Willump", "Wukong", "Vayne"], named
    assert min(r["score"] for r in rows) >= 0.80


def test_circle_detection_only_seeds_the_search_it_does_not_replace_it():
    """A ring centre is accurate to a pixel or two and this column does not
    tolerate that. Returning Hough's answer directly measured (-1, -2) on a
    settled capture where the truth was (0, 0), and Graves fell from 0.939 to
    0.655 -- the right champion on a margin thin enough that the confidence
    gate exists to refuse it. Hough finds the row, the template finds the
    pixel, so a SETTLED frame must still land exactly on the grid."""
    from src.icon_match import _align_champions
    image = _img(OVERVIEW)
    h, w = image.shape[:2]
    assert _align_champions(image, "switcher", h / 1080.0, w / 2340.0) == (0, 0)


def test_the_configured_badge_column_reads_the_frames_a_relocation_rejected():
    """A proven column must not lose to a couple of bad frames.

    On 2026-10-05 two degraded scans persisted x=(685,855) to
    calibration.json, which outlives the run. On the very frames that
    triggered it the CONFIGURED band read ranks 22-25 correctly while the new
    one read "92, 94, 95"; the scanner then refused its own reading as an
    impossible downward teleport, and every run afterwards started poisoned.
    """
    from src.config import SCREEN_2_BADGE_X_RANGE, SCREEN_LIST_Y_RANGE
    from src.ocr import scan_visible_ranks
    frame = Path("data/debug_scans/lost_rank24_133544.png")
    if not frame.exists():
        pytest.skip(f"{frame} not present")
    image = cv2.imread(str(frame))
    good, _pitch = scan_visible_ranks(image, SCREEN_2_BADGE_X_RANGE,
                                      y_range=SCREEN_LIST_Y_RANGE)
    assert {22, 23, 24, 25} <= set(good), f"configured band read {sorted(good)}"
    # The band that was persisted over it, on the same frame.
    bad, _p = scan_visible_ranks(image, (685, 855), y_range=SCREEN_LIST_Y_RANGE)
    assert not ({22, 23, 24, 25} & set(bad)), (
        f"(685,855) is supposed to be the WRONG column; it read {sorted(bad)}")


def test_calibration_is_not_sitting_on_a_relocated_column():
    """calibration.json wins over the constant, so a bad value there is
    invisible in the source and ruins every run until someone notices. It
    carries its own reference; they should agree unless a device genuinely
    needed re-measuring."""
    import json
    path = Path("coords/calibration.json")
    if not path.exists():
        pytest.skip("no calibration on this machine")
    cal = json.loads(path.read_text(encoding="utf-8"))
    ref = cal.get("badge_x_ref")
    if not ref:
        pytest.skip("calibration carries no reference")
    assert [cal.get("badge_x0"), cal.get("badge_x1")] == list(ref), (
        f"calibration {cal.get('badge_x0')},{cal.get('badge_x1')} has drifted "
        f"from its own reference {ref}")


class TestBadgeColumnCannotBePoisoned:
    """Three different bands have been auto-saved to calibration.json and each
    silently ruined every run after it. The file wins over the source
    constant, so a wrong value there is invisible in the code.

    The guard kept being a narrower version of the same question -- "does it
    overlap the reference enough" -- and kept being defeated, because the
    sweep window that proposes a band is 170px against a 75px reference and
    can clear 70% overlap while sitting 110px off centre.
    """

    REFERENCE = (795, 870)
    POISONED = [(985, 1155), (735, 905), (685, 855)]

    @pytest.mark.parametrize("band", POISONED)
    def test_every_band_that_has_poisoned_a_run_is_refused(self, band):
        from src.config import badge_band_plausible
        assert not badge_band_plausible(band, self.REFERENCE)

    @pytest.mark.parametrize("band", [(795, 870), (800, 865), (790, 872)])
    def test_a_genuine_re_measure_is_still_accepted(self, band):
        """The guard must not be so tight that a real device recalibration is
        impossible; a true re-measure shifts slightly and keeps its width."""
        from src.config import badge_band_plausible
        assert badge_band_plausible(band, self.REFERENCE)

    @pytest.mark.parametrize("band", POISONED)
    def test_a_poisoned_file_is_repaired_on_load(self, band):
        """Self-healing matters more than the write guard: whatever wrote the
        bad value, the next run must not inherit it."""
        from src.config import resolve_badge_calibration
        cal = {"badge_x0": band[0], "badge_x1": band[1],
               "badge_x_ref": list(self.REFERENCE),
               "leaderboard_layout": "2026-09-25"}
        current, _ref, geometry = resolve_badge_calibration(cal)
        assert current == self.REFERENCE
        assert (geometry["badge_x0"], geometry["badge_x1"]) == self.REFERENCE

    def test_runtime_never_writes_the_badge_column(self):
        """The structural fix. Runtime may TRY another column for one scan,
        but persisting it is what turns one bad frame into a ruined night, and
        no auto-relocation has ever been recorded as helping."""
        source = Path("src/scrape_timed.py").read_text(encoding="utf-8")
        for line in source.splitlines():
            if "save_calibration(" in line and "def " not in line:
                assert "badge_x0" not in line, (
                    f"runtime writes the badge column again: {line.strip()}")


class TestPowerSavingOverlay:
    """The phone dims the game to a near-black overlay when it sits idle, and
    a slow retry loop is exactly how the scraper goes idle. Every frame after
    that is the overlay, so an unattended run can spend its remaining hours
    reading a black screen and recording nothing."""

    FRAME = Path("data/device_states/power_saving.jpg")

    def test_the_overlay_is_recognised(self):
        from src.scrape_timed import looks_like_power_saving
        if not self.FRAME.exists():
            pytest.skip(f"{self.FRAME} not present")
        assert looks_like_power_saving(cv2.imread(str(self.FRAME)))

    @pytest.mark.parametrize("frame", [OVERVIEW, DETAIL, SWITCHED, BUILD])
    def test_real_game_screens_are_not_mistaken_for_it(self, frame):
        from src.scrape_timed import looks_like_power_saving
        assert not looks_like_power_saving(_img(frame))

    def test_darkness_alone_does_not_trigger_a_tap(self):
        """Brightness is only the cheap gate. A black loading frame carries no
        text, and tapping blindly on an unknown screen is how a scraper ends
        up somewhere it cannot navigate back from."""
        import numpy as np
        from src.scrape_timed import looks_like_power_saving
        assert not looks_like_power_saving(np.zeros((1080, 2340, 3), dtype="uint8"))

    def test_the_thresholds_leave_room_above_the_real_screens(self):
        """Measured: overlay mean 16.7, real leaderboard frames 42-54. The gate
        must sit between them with margin, not hug either side."""
        import numpy as np
        from src.scrape_timed import POWER_SAVING_MAX_MEAN
        overlay = cv2.imread(str(self.FRAME)) if self.FRAME.exists() else None
        if overlay is None:
            pytest.skip("overlay frame not present")
        om = cv2.cvtColor(overlay, cv2.COLOR_BGR2GRAY).mean()
        rm = min(cv2.cvtColor(_img(f), cv2.COLOR_BGR2GRAY).mean()
                 for f in (OVERVIEW, DETAIL, SWITCHED))
        assert om < POWER_SAVING_MAX_MEAN < rm, (
            f"overlay {om:.1f}, gate {POWER_SAVING_MAX_MEAN}, dimmest real {rm:.1f}")


class TestEveryChampionHasATemplate:
    """A champion with no icon file cannot fail to match -- it is not in the
    matcher at all, which looks identical to a bad match from the log.

    Hwei shipped in patch 7.3 with abilities, builds and archetypes all
    present, and no icon: `champion_templates()` held 141 entries against a
    142-champion roster, so the carousel met a row it could never name and
    fell through to the skip path.
    """

    def test_the_roster_and_the_templates_agree(self):
        import json
        from src.icon_match import champion_templates
        roster = json.loads(
            Path("web-next/src/data/roster.json").read_text(encoding="utf-8"))
        champion_templates.cache_clear()
        templates = champion_templates()
        missing = sorted(set(roster) - set(templates))
        assert not missing, f"roster champions with no icon template: {missing}"

    def test_every_roster_entry_points_at_a_local_icon(self):
        """iconLocal is what the second-screen reader and the overlay load.
        A remote-only entry is a champion the matcher cannot see."""
        import json
        roster = json.loads(
            Path("web-next/src/data/roster.json").read_text(encoding="utf-8"))
        bad = sorted(name for name, row in roster.items()
                     if not row.get("iconLocal"))
        assert not bad, f"roster entries with no iconLocal: {bad}"

    @pytest.mark.parametrize("champion", ["Cho'Gath", "Hwei"])
    def test_the_hand_added_icons_are_distinctive(self, champion):
        """Both were shipped with PC League art rather than the Wild Rift head
        icon, and PC art is drawn differently enough to match badly -- Cho'Gath
        was the ONE champion a full 141-champion run never captured. These two
        were replaced with the game's own art, so each must now be clearly
        itself and not merely the best of a bad set."""
        from src.icon_match import champion_templates, _norm_tile, _score, _weights
        bank = champion_templates()
        assert champion in bank
        weights = _weights(False, True)
        ranked = sorted(((_score(bank[champion], weights, t), n)
                         for n, t in bank.items()), reverse=True)
        assert ranked[0][1] == champion
        assert ranked[0][0] - ranked[1][0] >= 0.30, (
            f"{champion} only beats {ranked[1][1]} by "
            f"{ranked[0][0] - ranked[1][0]:.3f}")


class TestStripLifetimeGuard:
    """A strip frame captured before the season toggle took holds career
    totals, not season ones. It extracts perfectly cleanly, so nothing
    downstream notices -- one board reached us with 4,298 games on a ladder
    whose median was 35. The tiles label their own lifetime, so the frame
    carries the evidence; these pin that we read it."""

    SEASON = Path("data/captures_na/zyra_20261005_2242/001_strip.jpg")
    ALL_TIME = Path("data/captures_na/evelynn_20261005_1449/015_strip.jpg")

    @pytest.mark.skipif(not ALL_TIME.exists(), reason="capture not on this machine")
    def test_the_known_all_time_frame_is_rejected(self):
        from src.config import SCREEN_5_OCR_REGION
        from src.extract_frames import strip_is_all_time
        img = cv2.imread(str(self.ALL_TIME))
        assert strip_is_all_time(img, SCREEN_5_OCR_REGION) is True

    @pytest.mark.skipif(not SEASON.exists(), reason="capture not on this machine")
    def test_an_ordinary_season_frame_is_not(self):
        from src.config import SCREEN_5_OCR_REGION
        from src.extract_frames import strip_is_all_time
        img = cv2.imread(str(self.SEASON))
        assert strip_is_all_time(img, SCREEN_5_OCR_REGION) is False

    def test_an_unreadable_band_is_undecided_not_rejected(self):
        """None, not True. An unreadable label is not evidence of the wrong
        tab, and rejecting on it would throw away good rows."""
        import numpy as np
        from src.extract_frames import strip_is_all_time
        blank = np.zeros((1080, 2340, 3), dtype=np.uint8)
        assert strip_is_all_time(blank, (779, 729, 1561, 201)) is None


class TestChampionNearMatch:
    """Tesseract drops a whole tile over one bad character: "ZYRA" reads as
    "LYRA", "HWEI" as "HWEIl". Both canonicalise to nothing, so the row goes
    out blank -- 24 rows across two boards. The fallback only ever resolves
    toward the champion the caller is already looking for."""

    def test_a_single_corrupted_character_still_resolves(self):
        from src.ocr import resolve_champion
        assert resolve_champion(["LYRA"], "Zyra") == "Zyra"      # Z read as L
        assert resolve_champion(["HWEIl"], "Hwei") == "Hwei"     # spurious trailing l

    def test_it_does_nothing_without_a_target(self):
        from src.ocr import resolve_champion
        assert resolve_champion(["LYRA"]) is None

    def test_an_exact_match_always_wins_over_the_target(self):
        """Otherwise a neighbouring tile could be dragged onto the target."""
        from src.ocr import resolve_champion
        assert resolve_champion(["Ahri"], "Zyra") == "Ahri"

    def test_short_names_keep_exact_matching(self):
        """No two CANONICAL names are within one edit of each other, but
        "Master Yi" contributes the token "YI", which is one edit from the
        champion "Vi". The length floor is what keeps that pair apart."""
        from src.ocr import resolve_champion
        assert resolve_champion(["YI"], "Vi") is None

    def test_no_two_roster_names_are_within_one_edit(self):
        """The assumption the fallback rests on. If a future champion breaks
        it, the fallback has to be narrowed, not the floor raised."""
        from src.ocr import _within_one_edit
        from src import champions as champ_module
        names = sorted({str(n) for n in champ_module.CHAMPIONS})
        clashes = [(a, b) for i, a in enumerate(names) for b in names[i + 1:]
                   if _within_one_edit(a, b)]
        assert not clashes, f"names within one edit: {clashes}"


class TestCnHiddenProfiles:
    """CN lets a player hide their profile. The row keeps a real rank and
    score, but there is nothing behind it: tapping shows a brief toast and a
    "shy" panel. The tap chain never confirms a profile opened, so without
    this it would screenshot the ranking screen as a profile and then fire the
    next two taps into it."""

    def test_the_anonymous_name_is_recognised(self):
        from src.scrape_timed import looks_anonymous_cn
        assert looks_anonymous_cn("匿名玩家")
        # OCR rarely returns a bare phrase; substrings must still match.
        assert looks_anonymous_cn("  匿名玩家 ")
        assert looks_anonymous_cn("匿名玩家.")

    def test_real_names_are_not(self):
        from src.scrape_timed import looks_anonymous_cn
        for name in ("神王、Galun", "Moonveil、", "七海丶丶", "WrTrueMeta", "saltedpeanut"):
            assert not looks_anonymous_cn(name), name

    def test_a_missing_name_is_not_anonymous(self):
        """None means the read failed, which is worth retrying. Treating it as
        anonymous would silently drop every row whose name would not OCR."""
        from src.scrape_timed import looks_anonymous_cn
        assert not looks_anonymous_cn(None)
        assert not looks_anonymous_cn("")

    def test_the_skip_sentinel_is_not_a_name(self):
        """It travels in the player-name slot, so it must be distinguishable
        from a real name by identity, not equality: the row write, the counters
        and the retry loop all branch on it."""
        from src.scrape_timed import ANONYMOUS_CN, looks_anonymous_cn
        assert isinstance(ANONYMOUS_CN, str)
        assert not looks_anonymous_cn(ANONYMOUS_CN)

    def test_the_shy_panel_is_recognised_and_a_failed_read_is_not(self):
        """The safety net for a hidden profile the name check missed. A read
        that raises must return False: unreadable is not evidence of hiding,
        and treating it as such would drop good players."""
        import numpy as np
        from src.scrape_timed import looks_hidden_profile_cn
        # A uniform frame OCRs to nothing, which is "no evidence", not "hidden".
        assert looks_hidden_profile_cn(np.zeros((80, 300, 3), dtype=np.uint8)) is False

    def test_only_cn_pays_for_the_check(self):
        """The gate is the region, not a heuristic: EU and NA have no hidden
        profiles and must not pay an extra on-device name read per rank."""
        import inspect
        from src import scrape_timed
        src = inspect.getsource(scrape_timed)
        assert 'is_cn = (getattr(args, "region", None) or "").upper() == "CN"' in src
        assert "if is_cn:" in src

    def test_a_skipped_rank_extends_the_window(self):
        """Skipping must not shorten the board. --n is a number of PLAYERS, so
        a rank that yields nobody has to be replaced by going one deeper."""
        import inspect
        from src import scrape_timed
        src = inspect.getsource(scrape_timed)
        assert "anonymous_skipped += 1" in src
        assert "end_rank += 1" in src

    def test_the_skip_happens_before_the_row_is_written(self):
        """The first version of this guard sat after the row write, so a
        skipped rank was written to the CSV with the sentinel as its name and
        counted toward successes."""
        import inspect
        from src import scrape_timed
        src = inspect.getsource(scrape_timed)
        guard = src.index("if player_name is ANONYMOUS_CN:")
        write = src.index("writer.write(LeaderboardRow(")
        assert guard < write, "the skip guard must precede the row write"
