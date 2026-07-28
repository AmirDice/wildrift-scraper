"""Poke must not be offered to champions who fight in melee.

Poke means repeatable, reasonably safe pressure from range. The playstyle list
is built from the champion's CLASS, and three classes that grant Poke --
Mage, Enchanter and Marksman -- each contain melee champions. Lillia is a Mage
who attacks in melee, and the studio was offering her a Poke build.

The melee list is curated in data/combat_profiles.json (the scrape carries no
attack-range field) and mirrored into playstyles.json for the frontend, which
has no access to the Python profiles. These tests are what keep the two honest.
"""
from __future__ import annotations

import json
import pathlib

from web.advisor import profiles

ROOT = pathlib.Path(__file__).resolve().parent.parent
PLAYSTYLES = json.loads(
    (ROOT / "web-next" / "src" / "data" / "playstyles.json").read_text(encoding="utf-8"))
COMBAT = json.loads(
    (ROOT / "data" / "combat_profiles.json").read_text(encoding="utf-8"))

CURATED_MELEE = {name for name, entry in COMBAT["champions"].items()
                 if entry.get("rangeProfile") == "melee"}
CLASSIFIED = json.loads(
    (ROOT / "data" / "range_classification.json").read_text(encoding="utf-8"))["champions"]


class TestTheTwoListsAgree:
    def test_the_advisor_and_the_studio_read_the_same_no_poke_list(self):
        """One list, two consumers. profiles.NO_POKE loads playstyles.json
        directly, so a drift here is a drift between the advisor's idea of a
        legal playstyle and the menu the studio actually offers."""
        assert profiles.NO_POKE == set(PLAYSTYLES["noPoke"])

    def test_no_champion_can_reach_poke_through_its_class(self):
        """The invariant that actually matters, checked across the whole roster.

        Adding a melee champion to a poke-granting class, or granting poke to a
        class that contains melee champions, both break this -- and neither
        needs anyone to remember that the melee list exists.
        """
        by_class = PLAYSTYLES["byClass"]
        overrides = PLAYSTYLES["overrides"]
        listed = set(PLAYSTYLES["noPoke"])

        for name, record in profiles.CHAMPIONS.items():
            allowed = overrides.get(name) or by_class.get(record.get("class", "")) or []
            if "poke" not in allowed:
                continue
            if not profiles.poke_eligibility(name)["eligible"]:
                assert name in listed, (
                    f"{name} cannot poke, its class grants Poke, and it is not in "
                    f"noPoke -- the studio would offer it a Poke build")


class TestPokeEligibility:
    def test_lillia_cannot_poke(self):
        """The reported bug. She is ranged in the kit and still cannot poke."""
        assert not profiles.poke_eligibility("Lillia")["eligible"]

    def test_no_curated_melee_champion_is_poke_eligible(self):
        for name in CURATED_MELEE:
            assert not profiles.poke_eligibility(name)["eligible"], name

    def test_a_ranged_champion_who_fights_up_close_still_cannot_poke(self):
        """The distinction the whole reclassification exists for.

        These four have RANGED basic attacks -- marking them melee to suppress
        Poke was the wrong fix, because it also withheld ranged-only items they
        are allowed to buy.
        """
        for name in ("Lillia", "Thresh", "Rakan", "Vladimir"):
            assert profiles.range_profile(name) == "ranged", name
            assert not profiles.poke_eligibility(name)["eligible"], name

    def test_a_genuine_ranged_mage_still_pokes(self):
        """Vel'Koz is here on the owner's confirmation, not the classifier's.

        The model read him as textbook poke -- fights long, most of his damage
        from range -- but returned low confidence on two separate passes, and
        an unsure answer does not get to advertise a build. The owner confirmed
        it, which is what promoted him. That is the intended escape hatch for
        the unsure list, and it is recorded in range_classification.json under
        `userConfirmed` so it survives a re-run.
        """
        for name in ("Lux", "Ziggs", "Zilean", "Vel'Koz"):
            assert profiles.range_profile(name) == "ranged", name
            assert profiles.poke_eligibility(name)["eligible"], name

    def test_an_unsure_classification_never_offers_poke(self):
        low = {name for name, entry in CLASSIFIED.items()
               if entry.get("confidence") not in ("high", "medium")}
        assert low, "expected some low-confidence entries to guard"
        for name in low & set(profiles.CHAMPIONS):
            assert not profiles.poke_eligibility(name)["eligible"], (
                f"{name} was classified with low confidence but is still offered "
                f"a Poke build")

    def test_the_class_default_still_applies_without_an_override(self):
        assert profiles.range_profile("Ashe") == "ranged"
        assert profiles.range_profile("Garen") == "melee"


class TestRangedOnlyItems:
    """range_profile also gates items, which it did not used to.

    itemmeta re-derived melee/ranged from the class and ignored these
    overrides, so Runaan's Hurricane -- the one ranged-only item -- was offered
    to every melee champion classed as a Mage.
    """

    def test_no_melee_champion_is_offered_a_ranged_only_item(self):
        from web.advisor import itemmeta
        ranged_only = [slug for slug in itemmeta.completed_items()
                       if not itemmeta.metadata(slug)["meleeAllowed"]]
        assert ranged_only, "expected at least one ranged-only item to guard"

        for name in sorted(CURATED_MELEE):
            record = profiles.CHAMPIONS.get(name) or {}
            kept, _ = itemmeta.filter_candidates(
                record, profiles.combat_profile(name), profiles.scaling_profile(name))
            for slug in ranged_only:
                assert slug not in kept, f"{name} is melee but was offered {slug}"

    def test_ranged_champions_keep_them(self):
        from web.advisor import itemmeta
        record = profiles.CHAMPIONS.get("Ashe") or {}
        kept, _ = itemmeta.filter_candidates(
            record, profiles.combat_profile("Ashe"), profiles.scaling_profile("Ashe"))
        assert "runaans-hurricane" in kept
