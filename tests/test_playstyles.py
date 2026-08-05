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

    def test_an_owner_confirmation_outranks_the_classifier(self):
        """Vel'Koz and Nidalee both came back low confidence twice.

        The unsure rule would have withheld Poke from both; the owner confirmed
        it, and that confirmation is what puts it back.
        """
        for name in ("Vel'Koz", "Nidalee"):
            assert CLASSIFIED[name].get("userConfirmed"), name
            assert name in profiles.POKE_CONFIRMED, name
            assert profiles.poke_eligibility(name)["eligible"], name

    def test_a_correction_survives_re_running_the_classifier(self):
        """Rell is the case that matters here, in the other direction.

        She was confirmed for Poke and then corrected, and the correction is
        stored the same way the confirmation was. Without that, the next
        --apply would read the model's answer and the mistake would come back.
        """
        assert "corrected" in CLASSIFIED["Rell"]["userConfirmed"].lower()
        assert "Rell" not in profiles.POKE_CONFIRMED
        assert not profiles.poke_eligibility("Rell")["eligible"]
        assert "Rell" not in PLAYSTYLES["overrides"], (
            "the Poke override --apply added for Rell is still there; her class "
            "grants no Poke, so leaving it would re-offer the style")

    def test_confirmed_champions_are_absent_from_the_no_poke_list(self):
        assert not (profiles.POKE_CONFIRMED & profiles.NO_POKE)

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

    def test_a_hybrid_champion_is_denied_ranged_only_items(self):
        """Owner's rule: any melee in the kit disqualifies a ranged-only item.

        Gnar and Jayce both have a ranged mode and a melee mode. Runaan's
        Hurricane switches off the moment they transform, so an item that is
        only live half the game is not an item they can build around -- hybrid
        is treated exactly like melee here, even though it is not melee.
        """
        from web.advisor import itemmeta
        for name in ("Gnar", "Jayce"):
            assert profiles.range_profile(name) == "hybrid", name
            assert not profiles.is_pure_ranged(name), name
            record = profiles.CHAMPIONS.get(name) or {}
            kept, _ = itemmeta.filter_candidates(
                record, profiles.combat_profile(name), profiles.scaling_profile(name))
            assert "runaans-hurricane" not in kept, name

    def test_a_pure_ranged_champion_with_no_melee_mode_keeps_them(self):
        """The other half of the same rule, and a correction to the default.

        Akshan and Urgot were melee by class default, which was simply wrong.
        """
        from web.advisor import itemmeta
        for name in ("Akshan", "Urgot"):
            assert profiles.range_profile(name) == "ranged", name
            record = profiles.CHAMPIONS.get(name) or {}
            kept, _ = itemmeta.filter_candidates(
                record, profiles.combat_profile(name), profiles.scaling_profile(name))
            assert "runaans-hurricane" in kept, name

    def test_ranged_champions_keep_them(self):
        from web.advisor import itemmeta
        record = profiles.CHAMPIONS.get("Ashe") or {}
        kept, _ = itemmeta.filter_candidates(
            record, profiles.combat_profile("Ashe"), profiles.scaling_profile("Ashe"))
        assert "runaans-hurricane" in kept


class TestPlaystylePromptsDeferToTheKit:
    """A playstyle names an OUTCOME; the kit decides the mechanism.

    Reported on Sustain: the prompt read "a LIFESTEAL / omnivamp sustain
    build", and lifesteal is a basic-attack stat. Orianna cannot proc it, so
    asking her for Sustain asked for a build she cannot express. Sustain for
    Orianna and Sustain for Aatrox are different builds serving one goal, and
    only the kit knows which.
    """

    DEFINITIONS = {d["key"]: d for d in PLAYSTYLES["definitions"]}

    # Styles offered to more than one class, where the means genuinely differ.
    CROSS_CLASS = ("vamp", "tanky", "oneshot", "antitank", "utility")

    def test_cross_class_styles_defer_the_mechanism_to_the_kit(self):
        # Case-insensitive: these prompts capitalise THIS for emphasis wherever
        # the deferral is the point, so "THIS champion's damage" is the phrase
        # doing exactly what this test asks for and a case-sensitive match
        # rejected it.
        for key in self.CROSS_CLASS:
            prompt = self.DEFINITIONS[key]["prompt"].lower()
            assert "this kit" in prompt or "this champion" in prompt, (
                f"{key} states a mechanism without deferring to the kit, which is "
                f"how Sustain came to ask a mage for lifesteal")

    def test_sustain_warns_that_lifesteal_is_a_basic_attack_stat(self):
        """The exact bug, named in the prompt so it cannot come back quietly."""
        prompt = self.DEFINITIONS["vamp"]["prompt"].lower()
        assert "basic-attack stat" in prompt
        assert "caster" in prompt

    def test_every_style_a_mage_can_pick_is_expressible_by_a_mage(self):
        """Any style granted to Mage must not demand basic-attack mechanics
        without a caster carve-out."""
        for key in PLAYSTYLES["byClass"]["Mage"]:
            prompt = self.DEFINITIONS[key]["prompt"]
            names_attack_stat = any(
                term in prompt.lower() for term in ("lifesteal", "attack speed", "on-hit"))
            if names_attack_stat:
                assert "caster" in prompt.lower() or "cannot" in prompt.lower(), (
                    f"{key} is offered to Mages and names a basic-attack mechanic "
                    f"with no carve-out for a caster")

    def test_no_prompt_is_a_bare_mechanism(self):
        """Every prompt should say what the build is FOR, not only what to buy."""
        for key, entry in self.DEFINITIONS.items():
            assert len(entry["prompt"]) > 60, f"{key} is too terse to state an outcome"


class TestPresetsMergedIntoOneShot:
    """Three presets asked for the same build, so two of them had to go.

    'Burst' meant: delete a priority target in one rotation, penetration over
    sustain, accept the fragility. 'Glass cannon' (id `damage`) meant: maximum
    damage, offense over defense, buy only what the kit converts. One-shot
    means both. A player choosing between them was choosing between spellings
    of one request, and the model got near-identical instructions depending on
    which they picked.
    """

    DEFINITIONS = {d["key"]: d for d in PLAYSTYLES["definitions"]}
    GONE = ("burst", "damage")

    def test_the_merged_presets_are_no_longer_offered(self):
        for key in self.GONE:
            assert key not in self.DEFINITIONS
            for group, lists in (("class", PLAYSTYLES["byClass"]),
                                 ("override", PLAYSTYLES["overrides"])):
                for name, keys in lists.items():
                    assert key not in keys, f"{group} {name} still offers {key}"

    def test_every_class_still_has_the_one_rotation_build(self):
        """Removing them must not leave a class with no way to ask for damage.

        Mage and Tank only ever had Burst; Bruiser and Fighter only ever had
        Glass cannon. Without the swap each would have lost the request
        entirely, which is a missing feature rather than a simplification.
        """
        for name in ("Assassin", "Marksman", "Mage", "Tank", "Bruiser", "Fighter"):
            assert "oneshot" in PLAYSTYLES["byClass"][name], name

    def test_assassins_and_mages_can_ask_for_anti_tank(self):
        """Added when Glass cannon went: both classes meet frontlines and had
        no preset that said so."""
        for name in ("Assassin", "Mage"):
            assert "antitank" in PLAYSTYLES["byClass"][name], name

    def test_a_per_champion_override_did_not_miss_the_anti_tank_grant(self):
        """An override REPLACES the class list, so an Assassin or Mage with one
        keeps whatever it was frozen with unless it is updated too."""
        for name in ("Zed", "Akali"):
            assert "antitank" in PLAYSTYLES["overrides"][name], name

    def test_the_survivor_kept_what_both_presets_contributed(self):
        """Burst's escape hatch and Glass cannon's convertibility rule."""
        prompt = self.DEFINITIONS["oneshot"]["prompt"].lower()
        assert "cannot kill inside one rotation" in prompt
        assert "convert is the operative word" in prompt

    def test_no_class_lists_the_same_playstyle_twice(self):
        for name, keys in PLAYSTYLES["byClass"].items():
            assert len(keys) == len(set(keys)), f"{name} has a duplicate playstyle"

    def test_legacy_requests_still_resolve(self):
        """Shared links, albums and cache keys carry the old ids."""
        from web import build_advisor as adv
        assert adv.PLAYSTYLES.get("oneshot")
        for key in self.GONE:
            assert key not in adv.PLAYSTYLES
