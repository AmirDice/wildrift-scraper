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


class TestPatch73Items:
    """The nine items patch 7.3 added or redrew, against the game's own art.

    Worth pinning because the SOURCES differ and that is easy to forget.
    Runes are harvested from captured popups, so a new rune is invisible to
    the matcher until someone harvests it -- Legend: Haste sat unresolved in
    dozens of frames for exactly that reason. Items come from data/items.json
    plus its shipped art, which patch 7.3 already updated, so these needed no
    bank work at all. A future catalogue refresh could silently undo that.

    Fixtures are champion-select RECOMMENDED build screens (1256x1080), not
    leaderboard build popups, so the row geometry below is local to them.
    """

    FIXTURES = Path("data/patch_7_3_items")
    #: y, tile size, first x, pitch -- measured on these two screenshots.
    ROW = (296, 94, 285, 103)
    EXPECTED = {
        "recommended_marksman.jpg": ["Fiendhunter Bolts", "Rapid Firecannon",
                                     "Statikk Shiv", "Hexoptics C44",
                                     "Yun Tal Wildarrows"],
        "recommended_fighter.jpg": ["Immortal Shieldbow", "Echoes of Helia",
                                    "Stormrazor", "Essence Reaver"],
    }

    def _slots(self, name):
        path = self.FIXTURES / name
        if not path.exists():
            pytest.skip(f"{path} not present")
        image = cv2.imread(str(path))
        y0, size, x0, pitch = self.ROW
        return [image[y0:y0 + size, x0 + i * pitch: x0 + i * pitch + size]
                for i in range(len(self.EXPECTED[name]))]

    @pytest.mark.parametrize("frame", list(EXPECTED))
    def test_every_patch_73_item_resolves(self, frame):
        from src.icon_match import match_slot
        for tile, want in zip(self._slots(frame), self.EXPECTED[frame]):
            got, score, gap, runner = match_slot(tile, "items")
            assert got == want, (
                f"{frame}: read {got!r} (score {score:.3f}, runner-up "
                f"{runner!r}), want {want!r}")

    @pytest.mark.parametrize("frame", list(EXPECTED))
    def test_the_margins_are_not_marginal(self, frame):
        """Resolving is not enough: an item one bad pixel from its runner-up
        would flip on the next capture. Essence Reaver is the tight one, at a
        measured 0.11 -- its art was REDRAWN in 7.3 while the catalogue still
        ships the previous style."""
        from src.icon_match import match_slot, MIN_GAP
        for tile, want in zip(self._slots(frame), self.EXPECTED[frame]):
            _got, _score, gap, _runner = match_slot(tile, "items")
            assert gap >= MIN_GAP * 1.5, f"{frame}: {want} gap only {gap:.3f}"

    def test_the_badge_mask_is_not_widened_to_cover_the_new_pips(self):
        """7.3 stamps "N" (new) and a refresh pip over the bottom CENTRE of a
        tile, while mask_badge only covers the bottom LEFT, so the obvious
        move is to widen it. Measured over these nine, widening collapses the
        worst runner-up gap from 0.114 to 0.004: the extra strip carries more
        discriminative art than badge. Left alone deliberately."""
        from src.icon_match import _weights, N, MARGIN
        w = _weights(True, False)
        bottom_right = w[int(N * 0.70):, int(N * 0.60):]
        assert bottom_right.sum() > 0, (
            "the bottom-right of the tile is being masked; measured worse")
