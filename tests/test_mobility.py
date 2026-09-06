"""Who can actually move, which decides who counts as a diver.

`dash` feeds the diver count, the mobile-enemy count, and through them the
dive and backline-access numbers the whole draft ranker is built on. The
scrape tagged 96 of 141 champions by scanning for dash / blink / leap / lunge
/ vault / teleport / charge.

Unlike `cc`, most of that was right -- Wild Rift champions really are mobile --
so this pins the narrow failures rather than the breadth, and it pins them in
both directions: the champions who were wrongly mobile decide whether a comp
reads as a dive comp, and the champions who were wrongly immobile decide
whether a carry can survive one.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from web.advisor import mobility, profiles  # noqa: E402

ROSTER = json.loads((ROOT / "web-next" / "src" / "data" / "roster.json")
                    .read_text(encoding="utf-8"))


def dash(name: str) -> bool:
    record = profiles.CHAMPIONS.get(name) or {}
    return mobility.has_dash(record.get("abilities"), name)


class TestTheWordChargeIsUsuallyNotMovement:
    def test_stored_ability_charges_are_not_a_dash(self):
        # "Bandage Toss charges are stored every 13 seconds".
        assert not dash("Amumu")

    def test_an_ability_named_charge_is_not_a_dash(self):
        # Nautilus fires a Depth Charge; Viktor has Turbocharge.
        assert not dash("Nautilus")
        assert not dash("Viktor")

    def test_charging_TOWARD_something_is(self):
        # Malphite's ultimate "charges to the target area".
        assert dash("Malphite")


class TestTheMovementHasToBeYours:
    def test_interrupting_a_dash_is_not_having_one(self):
        # Jinx's Flame Chompers "interrupt their dashes". She is the most
        # immobile marksman in the game and being told otherwise is exactly
        # backwards for deciding whether she survives a dive.
        assert not dash("Jinx")

    def test_a_pet_moving_is_not_the_champion_moving(self):
        # Annie orders Tibbers to pounce.
        assert not dash("Annie")


class TestVocabulary:
    def test_champions_describe_movement_in_their_own_words(self):
        # Alistar rams, Poppy tackles, Kindred rolls, Evelynn warps, Corki
        # flies a short distance, Kha'Zix leaps. A list built from the word
        # "dash" reads only the champions who happen to use it.
        for name in ("Alistar", "Poppy", "Kindred", "Evelynn", "Corki",
                     "Kha'Zix", "Nidalee"):
            assert dash(name), name

    def test_an_ability_named_leap_still_leaps(self):
        # Blanking the champion's own skill names is right for "Depth Charge",
        # and wrong for Kha'Zix's "Leap" -- it turned "Leaps to target area"
        # into " s to target area".
        assert dash("Kha'Zix")

    def test_the_genuinely_immobile_stay_immobile(self):
        for name in ("Sona", "Ashe", "Caitlyn", "Veigar", "Nasus", "Garen",
                     "Kog'Maw", "Orianna", "Ziggs", "Syndra"):
            assert not dash(name), name


class TestTheRosterAgrees:
    def test_the_bundle_matches_the_deriver(self):
        for name, row in ROSTER.items():
            assert ("dash" in (row.get("mechanics") or [])) == dash(name), name
