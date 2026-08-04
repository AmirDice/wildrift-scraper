"""The curated generator and the live advisor must not drift apart again.

They are separate files with separate prompts, and they have drifted twice in
this project's history -- once on boots timing and situational runes, once on
the whole combat-profile rework. Both times the symptom was the same: builds
shipped from one path that the other path would have rejected. These tests pin
the facts that must stay shared.
"""
from __future__ import annotations

import scripts.build_champions_llm as curated
from web.advisor import itemmeta, profiles, summoners


def _curated_prompt(name="Hecarim", champ_class="Bruiser", role="Jungle"):
    champs = curated._load(curated.CHAMPS)
    items = curated._load(curated.ITEMS)
    runes = curated._load(curated.RUNES)
    rules = curated._load(curated.RULES) or {}
    item_by_slug = {i["slug"]: i for i in items}
    c = next(x for x in champs if x["name"] == name)
    variants = curated.variants_for(name, champ_class, role)
    return curated.build_prompt(
        curated._champion_block(c, champ_class, role), curated._item_pool(items),
        curated._rune_pool(runes), curated._mutex_block(rules, item_by_slug),
        variants, role, curated._kit_hints(c))


class TestCuratedVariantModel:
    """Primary variants plus an optional reviewed Alternative Path."""

    def test_variant_labels_cover_the_four_base_variants(self):
        for vid, name in [("standard", "Standard"), ("damage", "Aggressive"),
                          ("tanky", "Durable"), ("offmeta", "Alternative Path")]:
            assert curated.VARIANT_LABEL[vid] == name

    def test_every_variant_id_in_use_has_a_clean_label(self):
        """No ADC variant should fall back to a raw .title() ("Dps", "Antitank")."""
        ids = set()
        for name, cls, role in [("Ashe", "Marksman", "Dragon"),
                                ("Annie", "Mage", "Mid"), ("Zed", "Assassin", "Mid"),
                                ("Lulu", "Enchanter", "Support")]:
            ids.update(curated.variants_for(name, cls, role))
        for vid in ids:
            assert vid in curated.VARIANT_LABEL, f"{vid} has no user-facing label"

    def test_trust_tier_separates_primary_and_approved_alternative(self):
        tier = lambda v: curated.VARIANT_TRUST_TIER.get(v, "trusted")
        assert tier("standard") == "trusted"
        assert tier("crit") == "trusted"
        assert tier("antitank") == "trusted"
        assert tier("offmeta") == "alternative"

    def test_alternative_is_optional_and_reviewed(self):
        assert "offmeta" not in curated.variants_for("Rammus", "Tank", "Jungle")
        assert "offmeta" not in curated.variants_for("Irelia", "Bruiser", "Baron")
        assert "offmeta" in curated.variants_for("Fiora", "Bruiser", "Baron")
        assert "offmeta" in curated.variants_for("Nunu & Willump", "Tank", "Jungle")

    def test_aggressive_is_not_defined_as_glass_cannon(self):
        d = curated.VARIANT_DESC["damage"]
        assert "NOT automatically full lethality" in d or "NOT automatically" in d
        assert "glass" in d.lower()  # it explicitly says NOT glass cannon

    def test_durable_must_keep_champion_function(self):
        d = curated.VARIANT_DESC["tanky"]
        assert "ignorable full tank" in d

    def test_prompt_forbids_differing_variants_artificially(self):
        p = _curated_prompt()
        assert "Do NOT change an item solely to make one variant look different" in p
        assert "three EMPHASES of the" in p
        assert "free-form novelty" in p


class TestCuratedPromptPrinciples:
    """These live in the SYSTEM prompt; the per-champion USER message carries the
    kit-specific hints and the variant schema."""

    def test_synergy_is_no_longer_an_automatic_winner(self):
        assert "generically-strong item is WRONG" not in curated.SYSTEM
        assert "SYNERGY IS A MAJOR FACTOR, NOT AN AUTOMATIC WINNER" in curated.SYSTEM

    def test_manamune_is_evaluated_not_auto_core(self):
        assert "PER-CAST / RESOURCE ITEMS" in curated.SYSTEM
        assert "never treat them as automatically core" in curated.SYSTEM
        assert "Select Manamune only when" in curated.SYSTEM

    def test_movement_speed_is_weighed_not_forced(self):
        """Hecarim's kit trips the move-speed hint; it must no longer force a
        variant to be built around move speed. The hint is in the USER prompt."""
        p = _curated_prompt()
        assert "at least one variant must be built around" not in p
        assert "Do NOT force a variant to be built around move speed" in p

    def test_unknown_enemy_robustness_block_is_present(self):
        assert "UNKNOWN ENEMY TEAM" in curated.SYSTEM
        assert "first three purchases must form a coherent" in curated.SYSTEM

    def test_tie_breakers_are_present(self):
        assert "TIE-BREAKERS when two items or builds are close" in curated.SYSTEM

    def test_situational_is_zero_to_four_not_three_to_five(self):
        p = _curated_prompt()
        assert "0 TO 4 MEANINGFUL swaps" in p
        assert "Return an EMPTY list when no strong adaptation exists" in p


class TestSharedSources:
    def test_both_read_the_same_summoner_rules(self):
        assert curated.SUMMONERS is summoners.SPELLS

    def test_both_read_the_same_hard_exclusive_groups(self):
        rules = curated._load(curated.RULES)
        assert set(curated.hard_exclusive_groups(rules)) == set(itemmeta.HARD_EXCLUSIVE)

    def test_terminus_is_exclusive_in_the_curated_path_too(self):
        rules = curated._load(curated.RULES)
        groups = curated.hard_exclusive_groups(rules)
        assert "terminus" in groups["armor-penetration"]

    def test_both_treat_guardian_angel_as_late_strategic(self):
        assert "guardian-angel" in curated.LATE_STRATEGIC
        assert "guardian-angel" in itemmeta.LATE_STRATEGIC
        assert "guardian-angel" not in curated.SITUATIONAL_ONLY
        assert "guardian-angel" not in itemmeta.SITUATIONAL_ONLY


class TestCuratedChampionBlock:
    """The curated prompt must describe a champion the same way the live one does."""

    def _block(self, name="Hecarim"):
        champs = curated._load(curated.CHAMPS)
        record = next(c for c in champs if c["name"] == name)
        return curated._champion_block(record, "Bruiser", "Jungle")

    def test_it_carries_the_derived_profiles(self):
        block = self._block()
        assert "COMBAT PROFILE" in block
        assert "SCALING PROFILE" in block
        assert "BUILD IDENTITY PROFILE" in block
        assert '"repeatedOnHitReliance": "low"' in block

    def test_it_names_the_stats_that_can_anchor_a_build(self):
        block = self._block()
        assert "BUILD-PATH VIABILITY" in block
        assert '"totalAD": "core"' in block
        assert '"AP": "not_viable"' in block

    def test_it_no_longer_sends_the_coarse_tags(self):
        """`onHit` was on 85 of 141 champions and `ap` on 117; sending them as
        fact is what taught the model to stack attack speed on Hecarim."""
        block = self._block()
        assert "scales with:" not in block
        assert "mechanics:" not in block

    def test_malformed_ability_text_is_cleaned_and_flagged(self):
        block = self._block()
        assert "DATA QUALITY WARNING" in block
        assert "STRUCTURED EFFECTS" in block
        # The ability listing is indented; the warning line quotes the broken
        # text as evidence and is expected to still contain it.
        warpath = [ln for ln in block.splitlines() if ln.startswith("  [P] Warpath")]
        assert warpath, block
        assert "0 =" not in warpath[0]
        assert "12% bonus MS" in warpath[0]


class TestCuratedKitHints:
    def _hints(self, name):
        champs = curated._load(curated.CHAMPS)
        return curated._kit_hints(next(c for c in champs if c["name"] == name))

    def test_a_weaving_kit_is_pointed_at_spellblade_not_attack_speed(self):
        hints = " ".join(self._hints("Hecarim"))
        assert "ABILITY-WEAVING KIT" in hints
        assert "NOT an on-hit stacking kit" in hints
        assert "REPEATED ON-HIT KIT" not in hints

    def test_a_true_on_hit_carry_still_gets_the_on_hit_hint(self):
        hints = " ".join(self._hints("Ashe"))
        assert "REPEATED ON-HIT KIT" in hints

    def test_the_move_speed_hint_is_not_duplicated(self):
        hints = self._hints("Hecarim")
        move_speed = [h for h in hints if "MOVE SPEED" in h.upper()]
        assert len(move_speed) == 1, move_speed

    def test_no_hint_claims_attack_speed_multiplies_a_weaving_kit(self):
        """The single wrongest sentence the old prompt contained."""
        for name in ("Hecarim", "Nasus", "Darius"):
            hints = " ".join(self._hints(name))
            assert "attack speed and on-hit items multiply the passive" not in hints


class TestCuratedRulesBlock:
    def test_redundancy_section_is_gone_while_hard_exclusivity_stays(self):
        """Owner decision (2026-08-04): the redundancy groups are empty -- the
        only one was grievous-wounds, which swept in Serylda's Grudge, a
        mainline armor-pen item the ladder pairs freely. Hard exclusivity is a
        GAME rule and must survive; the redundancy advice must vanish rather
        than render as an empty header."""
        rules = curated._load(curated.RULES)
        items = {i["slug"]: i for i in curated._load(curated.ITEMS)}
        block = curated._mutex_block(rules, items)
        assert "HARD EXCLUSIVITY" in block
        assert "REDUNDANCY" not in block
        assert "why it is usually wrong" not in block

    def test_the_system_prompt_states_the_three_tiers(self):
        assert "RULES COME IN THREE TIERS" in curated.SYSTEM
        assert "Only the first is absolute" in curated.SYSTEM

    def test_it_no_longer_bans_guardian_angel_outright(self):
        assert "GUARDIAN ANGEL is NOT merely reactive" in curated.SYSTEM
        assert "position 4 or 5" in curated.SYSTEM

    def test_it_does_not_ask_for_summoner_spells(self):
        assert "DO NOT CHOOSE SUMMONER SPELLS" in curated.SYSTEM
        assert '"summoners":[{"name"' not in curated.build_prompt(
            "", "", "", "", ["standard"], "Jungle", [])

    def test_it_tells_the_model_to_trust_the_profiles(self):
        assert "buildPathViability" in curated.SYSTEM
        assert "repeatedOnHitReliance" in curated.SYSTEM


class TestProfilesAgreeAcrossBothPaths:
    def test_the_same_champion_derives_the_same_profile(self):
        """Both call the same module, so this pins that neither wraps it in a
        way that changes the answer."""
        for name in ("Hecarim", "Ashe", "Annie", "Graves"):
            live = profiles.combat_profile(name)
            champs = curated._load(curated.CHAMPS)
            record = next(c for c in champs if c["name"] == name)
            block = curated._champion_block(record, "", "")
            assert live["repeatedOnHitReliance"] in block
            assert live["basicAttackPattern"] in block
