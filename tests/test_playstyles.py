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


class TestTheTwoListsAgree:
    def test_the_frontend_list_mirrors_the_curated_overrides(self):
        assert set(PLAYSTYLES["meleeInRangedClass"]) == CURATED_MELEE, (
            "playstyles.json meleeInRangedClass has drifted from "
            "combat_profiles.json rangeProfile; the studio and the advisor would "
            "disagree about who can poke")

    def test_no_melee_champion_can_reach_poke_through_its_class(self):
        """The invariant that actually matters, checked across the whole roster.

        Adding a melee champion to a poke-granting class, or granting poke to a
        class that contains melee champions, both break this -- and neither
        needs anyone to remember that the melee list exists.
        """
        by_class = PLAYSTYLES["byClass"]
        overrides = PLAYSTYLES["overrides"]
        listed = set(PLAYSTYLES["meleeInRangedClass"])

        for name, record in profiles.CHAMPIONS.items():
            allowed = overrides.get(name) or by_class.get(record.get("class", "")) or []
            if "poke" not in allowed:
                continue
            if profiles.range_profile(name) == "melee":
                assert name in listed, (
                    f"{name} is melee, its class grants Poke, and it is not in "
                    f"meleeInRangedClass -- the studio would offer it a Poke build")


class TestPokeEligibility:
    def test_lillia_is_melee_and_cannot_poke(self):
        """The reported bug."""
        assert profiles.range_profile("Lillia") == "melee"
        assert not profiles.poke_eligibility("Lillia")["eligible"]

    def test_no_curated_melee_champion_is_poke_eligible(self):
        for name in CURATED_MELEE:
            assert not profiles.poke_eligibility(name)["eligible"], name

    def test_a_genuine_ranged_mage_still_pokes(self):
        for name in ("Lux", "Ziggs", "Vel'Koz"):
            assert profiles.range_profile(name) == "ranged", name
            assert profiles.poke_eligibility(name)["eligible"], name

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
