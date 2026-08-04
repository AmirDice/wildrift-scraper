"""Build-popup slot geometry must stay aligned to the pixel.

Cross-correlation is unforgiving about alignment, and the failure is silent:
the item row sat 4px high, which took Blade of the Ruined King from 0.805 to
0.121 on a frame whose art is otherwise near-identical to the catalogue. The
slot then failed the confidence gate and returned "?" -- and because an
unresolved TRAILING slot is read as an empty one, sixth items were dropped
from the build entirely rather than flagged.

Nothing downstream could notice. The names that DID resolve were correct, the
builds looked plausible, and the only symptom was Vayne quietly owning Blade
of the Ruined King in 14 builds instead of 47.

So the geometry is pinned here against real popups: if a constant drifts, or
a future UI change moves a row, this fails loudly instead of thinning the
data.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import pytest

import numpy as np

from src.icon_match import _align

# (frame, row, expected names in slot order)
POPUPS = [
    ("data/captures/vayne_20260803_1635/004_build.jpg", "items", [
        "Kraken Slayer", "Guinsoo's Rageblade", "Gunmetal Greaves",
        "Blade of the Ruined King", "Terminus", "Amaranth's Twinguard"]),
    ("data/captures/vayne_20260803_1635/004_build.jpg", "runes", [
        "Lethal Tempo", "Brutal", "Cut Down", "Legend: Alacrity", "Bone Plating"]),
    ("data/captures/vayne_20260803_1635/004_build.jpg", "spells", ["Ghost", "Flash"]),
]


@pytest.mark.parametrize("frame,row,expected", POPUPS)
def test_every_slot_resolves(frame: str, row: str, expected: list[str]):
    """A real popup, read end to end. Confirmed against the frame by eye."""
    path = Path(frame)
    if not path.exists():
        pytest.skip(f"{frame} not present")
    from src.icon_match import read_build_icons
    got = read_build_icons(cv2.imread(str(path)))[row]
    assert got == expected, f"{row}: read {got}"


@pytest.mark.parametrize("row", ["spells", "runes", "items"])
def test_the_nominal_geometry_stays_within_alignment_range(row: str):
    """The constants must stay close enough for the refinement to reach the
    true offset. The search spans +/-3px, so a row that has drifted further
    than that is out of reach and would fail silently -- which is the mode
    this whole file exists to prevent."""
    path = Path("data/captures/vayne_20260803_1635/004_build.jpg")
    if not path.exists():
        pytest.skip("popup frame not present")
    img = cv2.imread(str(path))
    h, w = img.shape[:2]
    dy, dx = _align(img, row, h / 1080.0, w / 2340.0)
    assert abs(dy) <= 2 and abs(dx) <= 2, (
        f"{row} needed dy={dy} dx={dx}: the nominal geometry has drifted to "
        f"the edge of the search window, correct GEOMETRY rather than rely on it")


@pytest.mark.parametrize("row", ["runes", "items"])
def test_confidence_does_not_decay_along_the_row(row: str):
    """A PITCH error fails differently from an origin error, and worse.

    An origin error shifts every slot equally, so runtime alignment absorbs
    it. A pitch error accumulates: with the item pitch at 104 instead of 105,
    slot 1 was exact and slot 6 sat five pixels out, and the confidences fell
    away along the row -- 0.81, 0.83, 0.86, 0.65, 0.64, 0.40. No single
    offset can correct a row whose slots disagree about where they are.

    The last slot scoring far below the first IS that signature, so assert
    against it rather than against any particular pitch constant.
    """
    path = Path("data/captures/vayne_20260803_1635/004_build.jpg")
    if not path.exists():
        pytest.skip("popup frame not present")
    from src.icon_match import read_build_icons
    conf = read_build_icons(cv2.imread(str(path)))["_confidence"][row]
    scores = [s for _n, s, _g in conf]
    assert len(scores) >= 4, f"{row}: only {len(scores)} slots read"
    assert scores[-1] >= scores[0] - 0.25, (
        f"{row} confidence decays along the row ({scores[0]:.2f} -> "
        f"{scores[-1]:.2f}): the pitch is wrong, not the origin")


def test_a_shifted_popup_still_reads_correctly():
    """The refinement earns its cost here. Shift a real popup by 2px and the
    build must come back identical: alignment is recovered at runtime, not
    assumed. Without this, a UI nudge of a few pixels silently thins the data
    instead of failing."""
    path = Path("data/captures/vayne_20260803_1635/004_build.jpg")
    if not path.exists():
        pytest.skip("popup frame not present")
    from src.icon_match import read_build_icons
    img = cv2.imread(str(path))
    truth = read_build_icons(img)["items"]
    assert "?" not in truth and len(truth) == 6, f"baseline is not clean: {truth}"

    shifted = np.roll(np.roll(img, 2, axis=0), -2, axis=1)
    got = read_build_icons(shifted)["items"]
    assert got == truth, f"a 2px shift changed the build:\n  {truth}\n  {got}"


class TestSupportItemBank:
    """The overlay bank for art the catalogue does not carry.

    The catalogue holds only the FINAL support income items, while the game
    draws whatever upgrade stage the player had -- so the sickle and shield
    stages matched nothing and 8 of 50 Lux support builds lost their support
    item to an honest "?". The templates in data/icon_bank/items.npz are
    averaged from 363 captured tiles, assigned by CHAMPION evidence (every
    Braum game carries the shield, every Yuumi game the sickle), not by
    eyeballing icons.
    """

    def test_bank_exists_with_both_lines(self):
        import numpy as np
        bank = Path("data/icon_bank/items.npz")
        if not bank.exists():
            pytest.skip("items.npz not built")
        with np.load(bank) as z:
            bases = {n.split("#")[0] for n in z.files}
        assert bases == {"Black Mist Scythe", "Bulwark of the Mountain"}

    @pytest.mark.parametrize("frame,expected", [
        ("data/captures/lux_20260803_0608/010_build.jpg", "Black Mist Scythe"),
        ("data/captures/braum_20260803_2138/001_build.jpg", "Bulwark of the Mountain"),
    ])
    def test_support_income_item_resolves_in_slot_one(self, frame, expected):
        path = Path(frame)
        if not path.exists():
            pytest.skip(f"{frame} not present")
        from src.icon_match import read_build_icons
        got = read_build_icons(cv2.imread(str(path)))["items"]
        assert got and got[0] == expected, f"slot 1 read {got[:1]}, want {expected}"

    def test_stage_templates_fold_to_one_name(self):
        """Two templates of the SAME item must not occupy first and second
        place and destroy each other's runner-up gap -- that would reject an
        item precisely because the bank knows it too well. match_slot folds
        "#stage" keys to the base name before ranking."""
        import numpy as np
        from src.icon_match import templates, match_slot, MIN_SCORE
        bank = Path("data/icon_bank/items.npz")
        if not bank.exists():
            pytest.skip("items.npz not built")
        with np.load(bank) as z:
            name = z.files[0]
            tpl = z[name]
        # feed the bank's own template back: identical match, so any gap
        # collapse could only come from a sibling stage of the same item
        v = (tpl - tpl.min()) / max(float(tpl.max() - tpl.min()), 1e-6)
        fake_slot = (v * 255).astype("uint8")
        got, score, gap, _ru = match_slot(fake_slot, "items")
        assert got == name.split("#")[0]
        assert score >= MIN_SCORE
