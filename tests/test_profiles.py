"""Champion profile derivation -- the layer that replaced the coarse tags."""
from __future__ import annotations

import pytest

from web.advisor import profiles


def test_whole_roster_derives_without_crashing():
    """141 champions, all shapes of data. A crash here takes the tool down."""
    for name in profiles.CHAMPIONS:
        result = profiles.profile(name, log=False)
        assert set(result["combatProfile"]) == {
            "basicAttackPattern", "basicAttackFrequency", "spellbladeProcReliability",
            "repeatedOnHitReliance", "attackSpeedValue", "critValue",
            "mobilityToDamageConversion", "healingReliance",
        }
        identity = result["buildIdentityProfile"]
        assert identity["primaryBuildPath"] in {"physical", "magic", "tank", "support"}
        assert identity["primaryCombatEngine"]
        assert identity["mainDamageSource"]
        assert identity["approvedBuildPaths"]


def test_profile_fields_use_the_declared_enums():
    levels = {"none", "low", "medium", "high"}
    patterns = {"caster", "ability-weaving", "repeated-attacks",
                "basic-attack-carry", "mixed"}
    labels = {"none", "low-incidental", "low", "medium", "high", "core"}
    for name in profiles.CHAMPIONS:
        result = profiles.profile(name, log=False)
        combat = result["combatProfile"]
        assert combat["basicAttackPattern"] in patterns, name
        for key, value in combat.items():
            if key != "basicAttackPattern":
                assert value in levels, f"{name}.{key}={value}"
        for stat, label in result.get("scalingProfile", {}).items():
            assert label in labels, f"{name}.{stat}={label}"


class TestHecarim:
    """The champion the rework was specified against (spec section 22)."""

    @pytest.fixture(scope="class")
    def hecarim(self):
        return profiles.profile("Hecarim", log=False)

    def test_weaves_abilities_rather_than_stacking_attacks(self, hecarim):
        assert hecarim["combatProfile"]["basicAttackPattern"] == "ability-weaving"

    def test_spellblade_is_high(self, hecarim):
        assert hecarim["combatProfile"]["spellbladeProcReliability"] == "high"

    def test_repeated_on_hit_reliance_is_low(self, hecarim):
        """One empowered attack is not on-hit reliance. This is the whole point:
        the old `onHit` tag forced Guinsoo's, Nashor's, Runaan's and Terminus
        into his comparison set."""
        assert hecarim["combatProfile"]["repeatedOnHitReliance"] == "low"

    def test_attack_speed_is_not_a_requirement(self, hecarim):
        assert hecarim["combatProfile"]["attackSpeedValue"] in ("none", "low")

    def test_movement_speed_converts_to_damage(self, hecarim):
        assert hecarim["combatProfile"]["mobilityToDamageConversion"] == "high"

    def test_ad_anchors_the_build_and_ap_does_not(self, hecarim):
        assert hecarim["scalingProfile"]["totalAD"] == "core"
        assert hecarim["scalingProfile"]["AP"] == "low-incidental"
        assert hecarim["buildPathStats"] == ["totalAD"]

    def test_warpath_survives_as_a_structured_effect(self, hecarim):
        """The prose is malformed; the parsed conversion is not."""
        warpath = [e for e in hecarim["structuredEffects"] if e["ability"] == "Warpath"]
        assert warpath == [{
            "ability": "Warpath", "slot": "P", "effectType": "stat-conversion",
            "outputStat": "totalAD", "ratio": 0.12, "inputStat": "movementSpeed",
        }]

    def test_malformed_ability_text_is_flagged_and_cleaned(self, hecarim):
        assert any("zero-equals" in a for a in hecarim["abilityTextArtifacts"])
        text = [a["text"] for a in profiles.normalized_abilities("Hecarim")
                if a["slot"] == "P"][0]
        assert "0 =" not in text
        assert "12% bonus MS" in text  # meaning preserved, artifact removed


def test_incidental_ap_is_not_a_build_path_across_ad_kits():
    """A kit can carry a real AP ratio and still have no AP build."""
    for name in ("Hecarim", "Xin Zhao"):
        result = profiles.profile(name, log=False)
        assert "AP" not in result.get("buildPathStats", [])


def test_a_hybrid_champions_off_identity_stat_is_experimental_not_a_trusted_anchor():
    """Issue 10: Jax is an AD champion who CAN go AP, but AP must not be a
    trusted anchor -- only his AD anchors trusted builds, and AP is available
    solely as a hybrid/experimental path."""
    jax = profiles.profile("Jax", log=False)
    assert "totalAD" in jax["buildPathStats"]
    assert "AP" not in jax["buildPathStats"]
    assert jax["buildPathViability"]["totalAD"] == "core"
    assert jax["buildPathViability"]["AP"] == "hybrid_or_experimental"


def test_an_ad_bruisers_incidental_ap_ratio_is_not_viable():
    """Issue 7: Fiora and Irelia scrape with an AP ratio (and Irelia even
    scrapes as primaryDamage=magic), but neither is an AP champion."""
    for name in ("Fiora", "Irelia"):
        p = profiles.profile(name, log=False)
        assert profiles.build_identity(name) == "physical", name
        assert p["buildPathViability"].get("AP") == "not_viable", name
        # AD is the anchor.
        anchors = p.get("buildPathStats") or []
        assert any(s in ("totalAD", "bonusAD") for s in anchors), name


class TestReviewedBuildIdentity:
    def test_master_yi_is_an_on_hit_carry_not_a_lethality_caster(self):
        profile = profiles.profile("Master Yi", log=False)
        combat = profile["combatProfile"]
        identity = profile["buildIdentityProfile"]
        assert combat["basicAttackPattern"] == "repeated-attacks"
        assert combat["repeatedOnHitReliance"] == "high"
        assert combat["attackSpeedValue"] == "high"
        assert identity["approvedBuildPaths"][0] == "ad-on-hit"
        assert identity["variantRules"]["*"]["maximumLethalityItems"] == 1

    def test_rammus_is_an_armor_tank_not_an_ap_bruiser(self):
        identity = profiles.build_identity_profile("Rammus")
        assert identity["primaryBuildPath"] == "tank"
        assert "armor" in identity["coreStats"]
        assert "Spiked Shell" in identity["mainDamageSource"]
        assert profiles.alternative_path("Rammus") is None

    def test_nasus_is_defined_by_q_stacks_not_incidental_ap(self):
        identity = profiles.build_identity_profile("Nasus")
        assert profiles.build_identity("Nasus") == "physical"
        assert identity["primaryBuildPath"] == "physical"
        assert "Siphoning Strike" in identity["mainDamageSource"]
        assert identity["variantRules"]["*"]["maximumAPItems"] == 1

    def test_fiora_has_only_a_reviewed_physical_crit_alternative(self):
        identity = profiles.build_identity_profile("Fiora")
        assert "Riposte" in identity["mainDamageSource"]
        assert identity["forbiddenAnchors"] == ["AP"]
        assert profiles.alternative_path("Fiora")["id"] == "crit-duelist"

    def test_irelia_uses_corrected_ultimate_cooldowns(self):
        ult = next(a for a in profiles.normalized_abilities("Irelia") if a["slot"] == "4")
        assert ult["cooldowns"] == [70, 65, 60]
        assert profiles._cooldown(profiles.CHAMPIONS["Irelia"]["abilities"][-1], "Irelia") == 60
        assert any("curated cooldown correction" in row
                   for row in profiles.ability_artifacts("Irelia"))

    def test_irelia_has_no_ap_alternative(self):
        identity = profiles.build_identity_profile("Irelia")
        assert "passive attacks" in identity["mainDamageSource"]
        assert profiles.alternative_path("Irelia") is None

    def test_nunu_separates_tank_default_from_ap_burst_alternative(self):
        identity = profiles.build_identity_profile("Nunu & Willump")
        assert identity["primaryBuildPath"] == "tank"
        assert identity["variantRules"]["*"]["minimumDefensiveItems"] == 3
        assert profiles.alternative_path("Nunu & Willump")["id"] == "ap-burst"


def test_an_ap_bruiser_override_keeps_magic_identity():
    """Mordekaiser scrapes with an AD ratio but is itemised full AP; a curated
    override protects that."""
    assert profiles.build_identity("Mordekaiser") == "magic"
    assert profiles.profile("Mordekaiser", log=False)["buildPathViability"]["AP"] == "core"


def test_a_once_per_target_proc_is_not_repeated_on_hit():
    """Issue 9: Jarvan's passive is a per-unique-enemy proc; his attack-speed
    steroid must not make him an on-hit carry."""
    jarvan = profiles.combat_profile("Jarvan IV")
    assert jarvan["repeatedOnHitReliance"] == "low"
    assert jarvan["basicAttackPattern"] != "repeated-attacks"


def test_a_true_on_hit_marksman_is_still_high_reliance():
    assert profiles.combat_profile("Ashe")["repeatedOnHitReliance"] == "high"


class TestPokeEligibility:
    """Issue 5: poke depends on repeatable ranged pressure, not class."""

    def test_a_melee_assassin_classed_as_mage_is_not_poke_eligible(self):
        e = profiles.poke_eligibility("Akali")
        assert e["eligible"] is False
        assert profiles.range_profile("Akali") == "melee"

    def test_a_conventional_melee_diver_is_not_poke_eligible(self):
        assert profiles.poke_eligibility("Diana")["eligible"] is False

    def test_a_true_ranged_poke_mage_is_eligible(self):
        for name in ("Ziggs", "Vel'Koz", "Lux"):
            if name in profiles.CHAMPIONS:
                assert profiles.poke_eligibility(name)["eligible"] is True, name

    def test_akali_variants_have_no_poke_but_a_credible_replacement(self):
        import scripts.build_champions_llm as curated
        variants = curated.variants_for("Akali", "Mage", "Mid")
        assert "poke" not in variants
        assert "burst" in variants  # the credible alternative for a melee assassin

    def test_the_profile_exposes_poke_eligibility(self):
        p = profiles.profile("Akali", log=False)
        assert p["playstyleEligibility"]["poke"]["eligible"] is False
        assert p["rangeProfile"] == "melee"


def test_pure_caster_has_no_crit_or_on_hit_value():
    annie = profiles.profile("Annie", log=False)["combatProfile"]
    assert annie["basicAttackPattern"] == "caster"
    assert annie["critValue"] == "none"
    assert annie["repeatedOnHitReliance"] == "none"


def test_marksman_is_a_basic_attack_carry():
    ashe = profiles.profile("Ashe", log=False)["combatProfile"]
    assert ashe["basicAttackPattern"] == "basic-attack-carry"
    assert ashe["repeatedOnHitReliance"] == "high"


def test_curated_override_wins():
    """Graves' reload kit does not want raw attack speed, whatever the pattern."""
    graves = profiles.profile("Graves", log=False)["combatProfile"]
    assert graves["basicAttackPattern"] == "basic-attack-carry"
    assert graves["attackSpeedValue"] == "low"


def test_stub_ability_data_is_reported_rather_than_guessed():
    """Cho'Gath's scrape returned blurbs. Say so; do not invent scaling."""
    artifacts = profiles.ability_artifacts("Cho'Gath")
    assert any("numeric cooldown" in a for a in artifacts)


def test_the_new_profile_is_far_more_selective_than_the_old_tag():
    """The regression this rework exists to prevent: `onHit` on 60% of the
    roster made the mandatory audit meaningless."""
    old = sum(1 for c in profiles.CHAMPIONS.values()
              if "onHit" in (c.get("mechanics") or []))
    new = sum(1 for n in profiles.CHAMPIONS
              if profiles.combat_profile(n)["repeatedOnHitReliance"] in ("medium", "high"))
    assert old > 80
    assert new < old / 2


class TestManaReliance:
    """The mirror of the manaless rule, which was missing entirely.

    A champion with no mana was told mana stats are dead. Nothing ever told the
    model that a kit is BOUNDED by mana, so builds for champions who cast
    constantly skipped mana the same way a Graves build does -- reported on
    Sona, whose auras are maintained by casting.
    """

    OWNER_LIST = ["Ezreal", "Jayce", "Kassadin", "Orianna", "Ryze", "Smolder", "Sona"]

    def test_each_named_champion_is_told_mana_is_limiting(self):
        for name in self.OWNER_LIST:
            facts = " ".join(profiles.kit_mechanics(name))
            assert "MANA-BOUND" in facts, name

    def test_the_guidance_carries_the_reason_for_that_kit(self):
        """A bare flag is a rule; the reason is what lets it be overridden."""
        facts = " ".join(profiles.kit_mechanics("Sona"))
        assert "Why for this kit:" in facts
        assert "auras" in facts.lower()

    def test_it_names_no_item(self):
        """The lesson from the manaless wording: naming an item as an example
        got it bought five times out of five."""
        for name in self.OWNER_LIST:
            facts = " ".join(m for m in profiles.kit_mechanics(name) if "MANA-BOUND" in m)
            for slug in ("boots-of-mana", "Boots of Mana", "Archangel", "Seraph",
                         "Rod of Ages", "Winter", "Fimbulwinter"):
                assert slug.lower() not in facts.lower(), f"{name} names {slug}"

    def test_it_says_stats_not_items(self):
        facts = " ".join(m for m in profiles.kit_mechanics("Ryze") if "MANA-BOUND" in m)
        assert "STATS" in facts

    def test_a_manaless_champion_never_gets_it(self):
        for name in ("Graves", "Katarina", "Garen"):
            facts = " ".join(profiles.kit_mechanics(name))
            assert "MANA-BOUND" not in facts, name

    def test_an_ordinary_mana_user_gets_neither_claim(self):
        """Most champions use mana without being bounded by it. Saying so for
        everyone would make the signal meaningless."""
        facts = " ".join(profiles.kit_mechanics("Lux"))
        assert "MANA-BOUND" not in facts
        assert "no mana" not in facts.lower()


class TestMultiStrikeEmpoweredAttacks:
    """An empowered attack that lands three hits applies on-hit three times.

    The rule read "empowered attack" and stopped, so Pantheon's Shield Vault --
    which the ability text says "strikes 3 times" -- counted as ONE on-hit
    application and he read as low reliance. That is why Blade of the Ruined
    King was scored 25 and skipped: the model was told his kit barely applies
    on-hit, when a single Mortal Will cycle applies it three times.

    The two things are separable and were being conflated: how OFTEN on-hit
    lands, and whether ATTACK SPEED is what makes it land. Pantheon's attack
    speed efficiency is 0.30 and that stays true; the application count was the
    part that was wrong.
    """

    MULTI_STRIKE = ("Pantheon", "Renekton", "Shyvana", "Viego")

    def test_zeds_energy_refund_is_not_a_multi_strike(self):
        """"gains Energy whenever an ABILITY strikes the same enemy twice" is a
        refund condition, not an attack landing twice. A bare `twice` match
        promoted him, which is why the pattern is anchored on "attack"."""
        assert profiles.combat_profile("Zed")["repeatedOnHitReliance"] == "low"

    def test_a_multi_strike_empower_is_not_low_reliance(self):
        for name in self.MULTI_STRIKE:
            got = profiles.combat_profile(name)["repeatedOnHitReliance"]
            assert got == "medium", f"{name} reads {got}"

    def test_it_is_not_promoted_all_the_way_to_high(self):
        """Three applications per cycle is real, but it is not a marksman
        applying on-hit on every auto -- that distinction is the whole point of
        the field."""
        for name in self.MULTI_STRIKE:
            assert profiles.combat_profile(name)["repeatedOnHitReliance"] != "high", name

    def test_a_once_per_target_proc_that_strikes_twice_is_middle_ground(self):
        """Viego. His proc lands twice but only on the first attack per target,
        so he is neither Jarvan (one application) nor a marksman."""
        assert profiles.combat_profile("Viego")["repeatedOnHitReliance"] == "medium"

    def test_a_once_per_target_proc_that_strikes_once_stays_low(self):
        """The rule the floor must not swallow."""
        assert profiles.combat_profile("Jarvan IV")["repeatedOnHitReliance"] == "low"

    def test_the_floor_never_demotes_a_genuine_on_hit_carry(self):
        """Master Yi matches the pattern and is correctly `high`. An earlier
        attempt placed this as a branch and dropped him to medium."""
        for name in ("Master Yi", "Caitlyn", "Senna", "Gwen", "Jax"):
            assert profiles.combat_profile(name)["repeatedOnHitReliance"] == "high", name

    def test_a_single_hit_empower_is_still_low(self):
        """The rule this narrows must keep working for everyone else."""
        for name in ("Darius", "Aatrox", "Camille"):
            assert profiles.combat_profile(name)["repeatedOnHitReliance"] == "low", name

    def test_a_real_on_hit_carry_is_untouched(self):
        assert profiles.combat_profile("Jax")["repeatedOnHitReliance"] == "high"

    def test_attack_speed_efficiency_is_unaffected(self):
        """Applying on-hit often does NOT mean attack speed converts well, and
        promoting one must not quietly promote the other."""
        know = (profiles.FORMULAS.get("Pantheon") or {}).get("knowledge") or {}
        assert know.get("asEfficiency", 1.0) < 0.5

    def test_no_multi_strike_kit_reads_as_low_reliance(self):
        """The invariant, stated as an outcome rather than a membership list.

        A champion whose ATTACK lands more than once applies on-hit more than
        once, so `low` is wrong for them whatever route they took to it. Master
        Yi matches the pattern and is already `high`, which is why the check is
        "not low" rather than "in my list" -- the list would have to be edited
        every time an existing high-reliance kit happened to match.

        Viego needed the rule to be a FLOOR rather than a branch: the
        once-per-target rule claims him before any later branch runs, and
        moving the check earlier demoted Master Yi instead. A floor only lifts
        `low`, so it fixes one without breaking the other.
        """
        for name, record in profiles.CHAMPIONS.items():
            text = " ".join((a.get("text") or "") for a in (record.get("abilities") or []))
            if profiles._MULTI_STRIKE.search(text):
                got = profiles.combat_profile(name)["repeatedOnHitReliance"]
                assert got in ("medium", "high"), (
                    f"{name}'s attack strikes more than once but reads {got}")
