"""Deterministic validation: what must be rejected, and what must not be."""
from __future__ import annotations

from conftest import check, make_build
from web.advisor import validate as validate_mod


def errors_in(report, section) -> str:
    return " ".join(report.errors.get(section, []))


def test_identity_violation_accepts_full_champion_card_shape():
    card = {"hardLimits": {"avoidStats": ["ap", "crit"]}}
    assert validate_mod.identity_violations(["rabadons-deathcap"], card)
    assert validate_mod.identity_violations(["infinity-edge"], card)


def test_magic_damage_amp_is_not_a_free_sett_item():
    # Abyssal Mask has no AP ratio, but its aura is still a magic-damage
    # amplification effect. It must not survive as a nominal "tank" slot on a
    # physical Sett build just because the item has HP/MR.
    from web.advisor import prompt
    violations = validate_mod.identity_violations(
        ["abyssal-mask"], prompt.identity_card("Sett"))
    assert any("magic penetration" in row for row in violations)


def test_hecarim_crit_core_is_rejected_as_a_forbidden_path():
    from web.advisor import prompt
    items = ["essence-reaver", "lord-dominiks-regard", "infinity-edge",
             "experimental-hexplate", "spear-of-shojin"]
    violations = validate_mod.identity_combo_violations(
        items, prompt.identity_card("Hecarim"))
    assert any("Crit Damage" in row for row in violations)


def test_rammus_attack_damage_items_are_rejected_by_identity():
    from web.advisor import prompt
    card = prompt.identity_card("Rammus")
    violations = validate_mod.identity_violations(
        ["divine-sunderer", "hullbreaker"], card)
    assert len(violations) == 2
    assert all("attack damage" in row for row in violations)


def test_frontline_crit_items_are_rejected_by_champion_policy():
    from web.advisor import prompt
    violations = validate_mod.identity_violations(
        ["essence-reaver", "infinity-edge", "lord-dominiks-regard"],
        prompt.identity_card("Sett"), champion_name="Sett", champion_class="Bruiser")
    assert len(violations) == 3
    assert all("critical strike" in row for row in violations)


def test_situational_frontline_crit_is_rejected_in_curated_mode():
    from web.advisor import prompt
    assert validate_mod.identity_violations(
        ["infinity-edge"], prompt.identity_card("Olaf"),
        champion_name="Olaf", champion_class="Bruiser")


def test_situational_frontline_crit_roster_is_blocked_but_strong_roster_remains():
    from web.advisor import crit_policy, prompt
    for champion in ("Vi", "Jarvan IV", "Wukong"):
        assert not crit_policy.allows(champion, "Bruiser")
        assert validate_mod.identity_violations(
            ["infinity-edge", "essence-reaver", "lord-dominiks-regard"],
            prompt.identity_card(champion), champion_name=champion,
            champion_class="Bruiser")
    assert crit_policy.allows("Yasuo", "Bruiser")


def test_wukong_prompt_does_not_keep_the_old_crit_never_rule():
    from web.advisor import prompt
    block = prompt.meta_identity_block("Wukong")
    assert "crit affinity: SITUATIONAL/OFF-META" in block
    assert "NEVER, at any cost: Crit Fighter" not in block


class TestBaseline:
    def test_a_well_formed_build_passes(self, build):
        report = check(build)
        assert report.ok, report.flat()

    def test_the_old_swap_shape_still_validates(self, build):
        """Backward compatibility: `replaces` + `atPosition` without a
        resultingOrder is under-specified, not wrong. Complete it, do not
        reject it."""
        build["situational"] = [{
            "item": "thornmail", "replaces": "guardian-angel", "atPosition": 2,
            "when": "against heavy attack-speed damage",
        }]
        report = check(build)
        assert report.ok, report.flat()
        entry = build["situational"][0]
        assert entry["resultingOrder"].count("thornmail") == 1
        assert "guardian-angel" not in entry["resultingOrder"]
        assert len(entry["resultingOrder"]) == 5
        # The old field names survive so the existing frontend keeps rendering.
        assert entry["replaces"] == "guardian-angel"
        assert entry["atPosition"] == 2


class TestActiveItemMutex:
    """Issue 1: a build may contain at most one active item."""

    def test_zero_active_items_passes(self, build):
        assert check(build).ok

    def test_one_active_item_passes(self, build):
        build["items"] = ["zhonyas-hourglass", "black-cleaver", "deaths-dance",
                          "steraks-gage", "guardian-angel"]
        build["candidateItemScores"].append(
            {"item": "zhonyas-hourglass", "score": 70, "reason": "stasis"})
        assert check(build).ok, check(build).flat()

    def test_two_active_items_fail(self, build):
        build["items"] = ["zhonyas-hourglass", "gargoyle-stoneplate", "deaths-dance",
                          "steraks-gage", "guardian-angel"]
        for s in ("zhonyas-hourglass", "gargoyle-stoneplate"):
            build["candidateItemScores"].append({"item": s, "score": 70, "reason": "x"})
        report = check(build)
        assert "active item" in errors_in(report, "items")

    def test_a_situational_order_with_two_actives_fails(self, build):
        # main build has one active; the swap inserts a second.
        build["items"] = ["zhonyas-hourglass", "black-cleaver", "deaths-dance",
                          "steraks-gage", "guardian-angel"]
        build["candidateItemScores"].append(
            {"item": "zhonyas-hourglass", "score": 70, "reason": "x"})
        build["situational"] = [{
            "item": "gargoyle-stoneplate", "insertAtPosition": 2, "removedItem": "black-cleaver",
            "resultingOrder": ["zhonyas-hourglass", "gargoyle-stoneplate", "deaths-dance",
                               "steraks-gage", "guardian-angel"],
            "when": "against burst"}]
        report = check(build)
        assert "situational" in report.errors


class TestHardLegality:
    def test_two_items_from_a_hard_exclusive_group_are_rejected(self, build):
        build["items"] = ["black-cleaver", "terminus", "deaths-dance",
                          "steraks-gage", "sundered-sky"]
        report = check(build)
        assert "armor-penetration" in errors_in(report, "items")

    def test_base_and_transformed_tear_items_are_exclusive(self):
        assert validate_mod.hard_exclusive_violation(["manamune", "muramana"])
        assert validate_mod.hard_exclusive_violation(
            ["archangels-staff", "seraphs-embrace"])
        assert validate_mod.hard_exclusive_violation(
            ["winters-approach", "fimbulwinter"])

    def test_an_invented_item_slug_is_rejected(self, build):
        build["items"][0] = "sword-of-a-thousand-truths"
        report = check(build)
        assert not report.ok
        assert "items" in report.errors

    def test_boots_cannot_occupy_an_item_slot(self, build):
        build["items"][0] = "ionian-boots-of-lucidity"
        report = check(build)
        assert not report.ok

    def test_duplicate_items_are_rejected(self, build):
        build["items"][1] = build["items"][0]
        report = check(build)
        assert "5 unique" in errors_in(report, "items")

    def test_selected_items_must_be_scored(self, build):
        build["candidateItemScores"] = [
            row for row in build["candidateItemScores"]
            if row["item"] != "deaths-dance"]
        report = check(build)
        assert "deaths-dance" in errors_in(report, "scores")


class TestRedundancyIsAWarningNotAnError:
    def test_two_grievous_wounds_items_warn_but_pass(self, build):
        build["items"] = ["chempunk-chainsword", "thornmail", "deaths-dance",
                          "steraks-gage", "sundered-sky"]
        build["candidateItemScores"] += [
            {"item": s, "score": 70, "reason": "x"} for s in
            ["chempunk-chainsword", "thornmail"]]
        # The guide names the items it was written for, so swapping the build
        # out from under it correctly invalidates it -- rewrite it to match.
        build["playGuide"]["powerSpike"] = (
            "Chempunk Chainsword at one item is the spike, and Conqueror keeps "
            "stacking through the longer fights it buys you.")
        build["playGuide"]["teamfight"] = (
            "Open on whoever Thornmail punishes hardest and hold Last Stand range.")
        report = check(build, enemies_known=True)
        assert report.ok, report.flat()
        # Owner decision (2026-08-04): the grievous-wounds redundancy group is
        # gone -- it swept in Serylda's Grudge, a mainline armor-pen item the
        # ladder pairs freely -- so the pairing now passes with NO warning.
        assert not any("grievous-wounds" in w for w in report.warnings)


class TestBoots:
    def test_defensive_boots_are_rejected_with_no_enemy_team(self, build):
        build["boots"] = "plated-steelcaps"
        report = check(build, enemies_known=False)
        assert "no enemy team" in errors_in(report, "boots")

    def test_defensive_boots_are_allowed_against_a_known_comp_with_a_reason(self, build):
        build["boots"] = "plated-steelcaps"
        build["why"] = ["Their Master Yi and Ashe are both auto-attack damage, "
                        "so the armour and the block passive keep me alive in fights."]
        report = check(build, enemies_known=True)
        assert report.ok, report.flat()

    def test_defensive_boots_against_a_known_comp_still_need_the_reason(self, build):
        build["boots"] = "mercurys-treads"
        build["why"] = []
        build["buildScore"]["reason"] = "good"
        report = check(build, enemies_known=True)
        assert "which specific enemy threat" in errors_in(report, "boots")


class TestGuardianAngel:
    def test_it_is_allowed_late(self, build):
        assert build["items"][4] == "guardian-angel"
        assert check(build).ok

    def test_it_is_rejected_as_an_early_purchase(self, build):
        build["items"] = ["guardian-angel", "black-cleaver", "deaths-dance",
                          "steraks-gage", "sundered-sky"]
        build["candidateItemScores"].append(
            {"item": "sundered-sky", "score": 70, "reason": "x"})
        report = check(build)
        assert "late strategic" in errors_in(report, "items")


class TestSituationalSwaps:
    def test_an_insertion_that_reorders_the_build_is_accepted(self, build):
        build["situational"] = [{
            "item": "thornmail", "insertAtPosition": 2, "removedItem": "guardian-angel",
            "resultingOrder": ["black-cleaver", "thornmail", "trinity-force",
                               "deaths-dance", "steraks-gage"],
            "when": "against a comp with two healing attack-speed threats",
        }]
        report = check(build)
        assert report.ok, report.flat()

    def test_a_resulting_order_that_is_not_five_items_is_rejected(self, build):
        build["situational"] = [{
            "item": "thornmail", "insertAtPosition": 2, "removedItem": "guardian-angel",
            "resultingOrder": ["black-cleaver", "thornmail", "trinity-force"],
            "when": "against attack speed",
        }]
        report = check(build)
        assert "exactly 5" in errors_in(report, "situational")

    def test_a_resulting_order_still_holding_the_removed_item_is_rejected(self, build):
        build["situational"] = [{
            "item": "thornmail", "insertAtPosition": 2, "removedItem": "guardian-angel",
            "resultingOrder": ["black-cleaver", "thornmail", "trinity-force",
                               "deaths-dance", "guardian-angel"],
            "when": "against attack speed",
        }]
        report = check(build)
        assert "still contains" in errors_in(report, "situational")

    def test_a_position_disagreeing_with_the_order_is_rejected(self, build):
        build["situational"] = [{
            "item": "thornmail", "insertAtPosition": 2, "removedItem": "guardian-angel",
            "resultingOrder": ["black-cleaver", "trinity-force", "thornmail",
                               "deaths-dance", "steraks-gage"],
            "when": "against attack speed",
        }]
        report = check(build)
        assert "must agree" in errors_in(report, "situational")

    def test_a_resulting_order_breaking_hard_legality_is_rejected(self, build):
        build["situational"] = [{
            "item": "terminus", "insertAtPosition": 2, "removedItem": "guardian-angel",
            "resultingOrder": ["black-cleaver", "terminus", "trinity-force",
                               "deaths-dance", "steraks-gage"],
            "when": "against stacked armour",
        }]
        report = check(build)
        assert "illegal" in errors_in(report, "situational")

    def test_every_swap_parked_at_the_end_is_rejected(self, build):
        build["situational"] = [{
            "item": "thornmail", "insertAtPosition": 5, "removedItem": "guardian-angel",
            "resultingOrder": ["black-cleaver", "trinity-force", "deaths-dance",
                               "steraks-gage", "thornmail"],
            "when": "against attack speed",
        }]
        report = check(build)
        assert "too late to matter" in errors_in(report, "situational")


class TestSituationalRunes:
    def test_a_rune_freeing_an_item_slot_must_say_what_fills_it(self, build):
        build["situationalRunes"] = [{
            "rune": "Legend: Tenacity", "replacesType": "item",
            "replaces": "steraks-gage", "when": "against heavy crowd control",
        }]
        report = check(build)
        assert "freedSlotItem" in errors_in(report, "situationalRunes")

    def test_a_complete_item_replacing_rune_swap_is_accepted(self, build):
        build["situationalRunes"] = [{
            "rune": "Legend: Tenacity", "replacesType": "item",
            "replaces": "steraks-gage", "freedSlotItem": "thornmail", "atPosition": 4,
            "resultingItems": ["black-cleaver", "trinity-force", "deaths-dance",
                               "thornmail", "guardian-angel"],
            "when": "against heavy crowd control from a melee comp",
        }]
        report = check(build)
        assert report.ok, report.flat()

    def test_a_minor_cannot_be_swapped_across_slots(self, build):
        build["situationalRunes"] = [{
            "rune": "Overgrowth", "replacesType": "rune",
            "replaces": "Legend: Alacrity", "when": "against poke",
        }]
        report = check(build)
        assert "same tree and slot" in errors_in(report, "situationalRunes")

    def test_a_same_slot_minor_swap_is_accepted(self, build):
        build["situationalRunes"] = [{
            "rune": "Legend: Tenacity", "replacesType": "rune",
            "replaces": "Legend: Alacrity", "when": "against heavy crowd control",
        }]
        report = check(build)
        assert report.ok, report.flat()

    def test_a_rune_already_on_the_page_cannot_be_swapped_in(self, build):
        build["situationalRunes"] = [{
            "rune": "Brutal", "replacesType": "rune",
            "replaces": "Legend: Alacrity", "when": "for more damage",
        }]
        report = check(build)
        assert "already on the main rune page" in errors_in(report, "situationalRunes")


class TestRunePage:
    def test_two_minors_from_one_slot_are_rejected(self, build):
        build["runes"]["minors"] = ["Brutal", "Triumph", "Legend: Alacrity"]
        report = check(build)
        assert "slots 1, 2 and 3" in errors_in(report, "runes")

    def test_a_minor_from_another_tree_is_rejected(self, build):
        build["runes"]["minors"] = ["Brutal", "Last Stand", "Overgrowth"]
        report = check(build)
        assert "primary tree" in errors_in(report, "runes")

    def test_a_flex_duplicating_a_minor_is_rejected(self, build):
        build["runes"]["flex"] = "Brutal"
        report = check(build)
        assert "already on the page" in errors_in(report, "runes")

    def test_a_non_keystone_keystone_is_rejected(self, build):
        build["runes"]["keystone"] = "Brutal"
        report = check(build)
        assert "not a keystone" in errors_in(report, "runes")

    def test_a_flex_from_the_primary_tree_is_rejected(self, build):
        """Issue 2: Precision primary cannot take a Precision flex."""
        build["runes"]["flex"] = "Coup de Grace"  # Precision, same as the primary
        report = check(build)
        assert "different tree" in errors_in(report, "runes").lower()

    def test_a_flex_from_a_different_tree_passes(self, build):
        build["runes"]["flex"] = "Gathering Storm"  # Sorcery, off the Precision primary
        assert check(build).ok, check(build).flat()

    def test_a_same_tree_flex_repairs_as_a_rune_only_failure(self, build):
        build["runes"]["flex"] = "Coup de Grace"
        report = check(build)
        assert report.sections() == ["runes"]

    def test_an_illegal_page_does_not_invalidate_the_item_build(self, build):
        """The point of sectioned errors: a bad rune page is repaired alone."""
        build["runes"]["minors"] = ["Brutal", "Triumph", "Legend: Alacrity"]
        report = check(build)
        assert report.sections() == ["runes"]


class TestSummonersSurviveValidation:
    """The model picks summoners now, and the validator must not touch them.

    This class previously asserted the opposite: validation popped the key,
    because the advisor assigned spells itself. When the model was given the
    choice back, that pop was left in place and silently discarded every pick,
    so the fallback table answered every single build while appearing to work.
    These tests exist so that cannot happen quietly a second time.
    """

    def test_the_model_pick_is_preserved_for_the_advisor_to_enforce(self, build):
        build["summoners"] = ["Ghost", "Smite"]
        report = check(build, role="Jungle")
        assert report.ok, report.flat()
        assert build["summoners"] == ["Ghost", "Smite"], (
            "validation discarded the model's summoners; the advisor would fall "
            "back to the static table for every build")

    def test_junk_is_left_for_enforce_rather_than_failing_the_build(self, build):
        """Malformed spells are still not a reason to reject a good build."""
        build["summoners"] = ["Smite", "Smite", "nonsense"]
        assert check(build, role="Mid").ok

    def test_a_jungler_missing_smite_does_not_fail_the_build(self, build):
        """Smite is imposed downstream by enforce(), not demanded here."""
        assert check(build, role="Jungle").ok


class TestSnowballSwap:
    def test_a_vague_condition_is_rejected(self, build):
        build["snowballSwap"] = {
            "item": "thornmail", "replaces": "guardian-angel", "when": "when ahead"}
        report = check(build)
        assert "too vague" in errors_in(report, "snowball")

    def test_a_concrete_condition_is_accepted(self, build):
        build["snowballSwap"] = {
            "item": "thornmail", "replaces": "guardian-angel", "atPosition": 3,
            "when": "roughly 1500 gold ahead before the second Baron-lane objective",
        }
        report = check(build)
        assert report.ok, report.flat()
        assert len(build["snowballSwap"]["resultingOrder"]) == 5

    def test_null_is_valid(self, build):
        build["snowballSwap"] = None
        assert check(build).ok


class TestScoreSplit:
    def test_the_audit_list_does_not_consume_the_candidate_quota(self, build):
        """Section 2: audits are scored separately and do not count as
        competitive candidates."""
        build["mandatoryAuditScores"] = [
            {"item": "guinsoos-rageblade", "score": 15, "reason": "no repeated on-hit"},
            {"item": "nashors-tooth", "score": 10, "reason": "no AP build path"},
        ]
        report = check(build, required_audit_items=["guinsoos-rageblade", "nashors-tooth"])
        assert report.ok, report.flat()
        assert len(build["candidateItemScores"]) == 12
        assert len(build["mandatoryAuditScores"]) == 2

    def test_a_missing_audit_item_is_reported(self, build):
        report = check(build, required_audit_items=["guinsoos-rageblade"])
        assert "guinsoos-rageblade" in errors_in(report, "scores")

    def test_the_legacy_combined_list_is_still_published(self, build):
        build["mandatoryAuditScores"] = [
            {"item": "guinsoos-rageblade", "score": 15, "reason": "no"}]
        check(build)
        published = {row["item"] for row in build["itemScores"]}
        assert "guinsoos-rageblade" in published
        assert "black-cleaver" in published

    def test_a_bad_score_row_is_dropped_not_failed(self, build):
        """A stray score row is commentary, not a defect. Failing on one cost a
        full regeneration in the first live run."""
        build["candidateItemScores"].append(
            {"item": "black-cleaver", "score": 140, "reason": "out of range"})
        build["candidateItemScores"].append(
            {"item": "not-a-real-item", "score": 50, "reason": "invented"})
        report = check(build)
        assert report.ok, report.flat()
        assert any("dropped" in w for w in report.warnings)
        scored = {row["item"] for row in build["candidateItemScores"]}
        assert "not-a-real-item" not in scored

    def test_scoring_a_withheld_item_warns_but_does_not_fail(self, build):
        allowed = [s for s in build["items"]] + ["sundered-sky", "goredrinker",
                                                 "dead-mans-plate", "thornmail",
                                                 "sunfire-aegis", "warmogs-armor",
                                                 "randuins-omen"]
        report = check(build, allowed_items=allowed + ["serpents-fang"])
        assert report.ok, report.flat()

    def test_an_item_withheld_from_the_pool_cannot_be_selected(self, build):
        """Selection is the real guard, and it stays a hard error."""
        allowed = [s for s in build["items"] if s != "guardian-angel"]
        report = check(build, allowed_items=allowed)
        assert "withheld" in errors_in(report, "items")


def _counter_summary():
    return {
        "confidence": 65,
        "counterPriorities": ["survive Master Yi's sustained physical DPS"],
        "threatResponses": [
            {"choiceType": "item", "choice": "randuins-omen",
             "answers": ["Master Yi", "Ashe"], "reason": "armour + crit slow"}],
        "acceptedTradeoffs": ["kept one damage item so I am not ignorable"],
        "unansweredThreats": ["Ahri's mobility"],
        "allyContextUsed": False,
    }


class TestCounterMode:
    def test_counter_mode_drops_reactive_swaps(self, build):
        build["situational"] = [{
            "item": "thornmail", "replaces": "guardian-angel", "atPosition": 2,
            "when": "against attack speed"}]
        build["situationalRunes"] = [{
            "rune": "Legend: Tenacity", "replacesType": "rune",
            "replaces": "Legend: Alacrity", "when": "against crowd control"}]
        build["counterSummary"] = _counter_summary()
        check(build, mode="counter", enemies_known=True)
        assert build["situational"] == []
        assert build["situationalRunes"] == []

    def test_counter_mode_drops_the_build_evaluation(self, build):
        build["counterSummary"] = _counter_summary()
        check(build, mode="counter", enemies_known=True)
        assert "buildScore" not in build

    def test_a_well_formed_counter_summary_passes(self, build):
        build["counterSummary"] = _counter_summary()
        report = check(build, mode="counter", enemies_known=True)
        assert report.ok, report.flat()

    def test_a_missing_counter_summary_is_a_counter_summary_error(self, build):
        build.pop("counterSummary", None)
        report = check(build, mode="counter", enemies_known=True)
        assert "counterSummary" in report.errors
        # It repairs in isolation, not by regenerating the whole build.
        assert "items" not in report.errors

    def test_a_counter_summary_without_priorities_is_rejected(self, build):
        summary = _counter_summary()
        summary["counterPriorities"] = []
        build["counterSummary"] = summary
        report = check(build, mode="counter", enemies_known=True)
        assert "counterPriorities" in errors_in(report, "counterSummary")


class TestLocks:
    def test_a_missing_locked_item_is_reported(self, build):
        report = check(build, item_locks=["sundered-sky"])
        assert "pinned" in errors_in(report, "locks")

    def test_a_present_locked_item_passes(self, build):
        assert check(build, item_locks=["black-cleaver"]).ok

    def test_a_missing_locked_rune_is_reported(self, build):
        report = check(build, rune_locks=["Overgrowth"])
        assert "Overgrowth" in errors_in(report, "locks")


class TestRuneReasonsFollowTheirRune:
    """Reasons are zipped with runes BY INDEX downstream, so a reason written
    for a rune that did not make the page shifts every reason after it.

    This shipped on a live Pantheon build: Hubris was explained as "Eyeball
    Collector: scales AD from takedowns", and Eyeball Collector as "Relentless
    Hunter: out-of-combat movement speed" -- a rune that was not in the build.
    """

    def page(self):
        return {"keystone": "Electrocute", "primaryTree": "Domination",
                "minors": ["Sudden Impact", "Hubris", "Eyeball Collector"],
                "flex": "Coup de Grace"}

    def realign(self, minors_reasons):
        from web.advisor import validate as validate_mod
        page = self.page()
        res = {"runes": page,
               "runeReasons": {"keystone": "Electrocute procs off the combo.",
                               "minors": minors_reasons,
                               "flex": "Coup de Grace: finishes low targets."}}
        report = validate_mod.Report()
        validate_mod._realign_rune_reasons(res, page, report)
        return dict(zip(page["minors"], res["runeReasons"]["minors"])), report

    def test_a_reason_lands_on_the_rune_it_names(self):
        paired, _ = self.realign([
            "Sudden Impact: true damage after the dash.",
            "Eyeball Collector: scales AD from takedowns.",
            "Relentless Hunter: out-of-combat move speed.",
        ])
        assert paired["Sudden Impact"].startswith("Sudden Impact")
        assert paired["Eyeball Collector"].startswith("Eyeball Collector")

    def test_a_reason_for_a_rune_not_in_the_page_is_dropped(self):
        paired, _ = self.realign([
            "Sudden Impact: true damage after the dash.",
            "Eyeball Collector: scales AD from takedowns.",
            "Relentless Hunter: out-of-combat move speed.",
        ])
        assert "Relentless Hunter" not in " ".join(paired.values())

    def test_a_rune_with_no_reason_of_its_own_gets_none(self):
        """Better blank than borrowed: the frontend hides reasonless rows."""
        paired, _ = self.realign([
            "Sudden Impact: true damage after the dash.",
            "Eyeball Collector: scales AD from takedowns.",
            "Relentless Hunter: out-of-combat move speed.",
        ])
        assert paired["Hubris"] == ""

    def test_the_realignment_is_reported(self):
        _, report = self.realign([
            "Sudden Impact: true damage after the dash.",
            "Eyeball Collector: scales AD from takedowns.",
            "Relentless Hunter: out-of-combat move speed.",
        ])
        assert any("realigned" in w for w in report.warnings)

    def test_correct_reasons_are_left_exactly_as_they_are(self):
        reasons = [
            "Sudden Impact: true damage after the dash.",
            "Hubris: stacking AD on takedowns.",
            "Eyeball Collector: scales AD from takedowns.",
        ]
        paired, report = self.realign(list(reasons))
        assert list(paired.values()) == reasons
        assert not any("realigned" in w for w in report.warnings)

    def test_unlabelled_reasons_keep_their_order(self):
        """Not every reason names its rune; those fall back to position."""
        paired, _ = self.realign([
            "Sudden Impact: true damage after the dash.",
            "stacks attack damage as you get takedowns.",
            "gives more AD per eyeball.",
        ])
        assert paired["Hubris"] == "stacks attack damage as you get takedowns."
        assert paired["Eyeball Collector"] == "gives more AD per eyeball."


class TestAnInvalidBuildIsNeverServed:
    """The repair budget can run out with the build still broken.

    It used to be returned anyway. A measured Akali run shipped five builds with
    boots sitting in the item slots, and one containing 'shadowflame', an item
    that does not exist in the game -- every failure printed to the log first,
    then served. Cached, one of those becomes the champion's permanent answer.
    """

    def test_boots_in_the_item_slots_is_caught(self, build):
        build["items"] = ["boots-of-mana", "lich-bane", "stormsurge",
                          "void-staff", "rabadons-deathcap"]
        report = check(build)
        assert "items" in report.sections()
        assert "boots" in errors_in(report, "items")

    def test_an_item_that_does_not_exist_is_caught(self, build):
        build["items"] = ["lich-bane", "shadowflame", "stormsurge",
                          "void-staff", "rabadons-deathcap"]
        report = check(build)
        assert "items" in report.sections()
        assert "5 unique known slugs" in errors_in(report, "items")

    def test_the_core_sections_are_the_ones_that_must_never_ship(self):
        """items/boots/runes/locks are the build; the rest annotate it.

        Guards the split the advisor gates on, so a section moving between the
        two groups is a deliberate edit rather than an accident.
        """
        from web.advisor import validate as validate_mod
        core = {"items", "boots", "runes", "locks"}
        assert core <= set(validate_mod.SECTIONS)
        extras = set(validate_mod.SECTIONS) - core
        assert extras == {"situational", "situationalRunes", "snowball",
                          "scores", "counterSummary", "playGuide"}


class TestBootsFollowTheDamagePath:
    """An AP request that returns attack-speed boots is not honouring it.

    Reported on Kayle: asked for an AP build, given Berserker's Greaves. The
    damage path reached the ITEM rules and stopped there, and the hard-legality
    rule says plainly that boots are not one of the five items -- so "do not mix
    in AD items" reads as not covering them.
    """

    def test_attack_speed_boots_are_rejected_on_an_ap_build(self, build):
        build["boots"] = "berserkers-greaves"
        report = check(build, damage_path="ap")
        assert "boots" in report.sections()
        assert "AP build" in " ".join(report.errors["boots"])

    def test_ad_boots_are_rejected_on_an_ap_build(self, build):
        build["boots"] = "boots-of-dynamism"
        assert "boots" in check(build, damage_path="ap").sections()

    def test_ap_boots_are_rejected_on_an_ad_build(self, build):
        build["boots"] = "boots-of-mana"
        assert "boots" in check(build, damage_path="ad").sections()

    def test_the_ap_boot_passes_on_an_ap_build(self, build):
        build["boots"] = "boots-of-mana"
        assert "boots" not in check(build, damage_path="ap").sections()

    def test_neutral_boots_stay_legal_on_every_path(self, build):
        """The rule forbids the OFF-PATH OFFENSIVE boot, not every boot that is
        not the on-path one. Ionian on an AP mage is a normal, correct choice."""
        for path in ("ap", "ad", "standard"):
            build["boots"] = "ionian-boots-of-lucidity"
            assert "boots" not in check(build, damage_path=path).sections(), path

    def test_the_standard_path_constrains_nothing(self, build):
        for boots in ("berserkers-greaves", "boots-of-mana", "boots-of-dynamism"):
            build["boots"] = boots
            assert "boots" not in check(build, damage_path="standard").sections(), boots


class TestLadderCoreScoring:
    """The REQUIRED CANDIDATES rule, with teeth.

    The prompt demands a score for every ladder-core item whether or not it
    reaches the build. That lived only in prose until a live Aatrox run
    silently skipped trinity-force -- a core item -- and nothing caught it.
    Now the validator fails the scores section, which the targeted repair
    loop already knows how to fix.
    """

    def test_an_unscored_core_item_fails_scores(self, build):
        scored = {r["item"] for r in build["candidateItemScores"]}
        assert "kraken-slayer" not in scored, "fixture drifted; pick another slug"
        report = check(build, ladder_core=["kraken-slayer"])
        assert not report.ok
        assert "kraken-slayer" in errors_in(report, "scores")

    def test_a_scored_core_item_passes_even_when_not_built(self, build):
        build["candidateItemScores"].append(
            {"item": "kraken-slayer", "score": 55,
             "reason": "on-hit burst loses to Cleaver shred on this kit"})
        report = check(build, ladder_core=["kraken-slayer"])
        assert report.ok, report.flat()
        assert "kraken-slayer" not in (build.get("items") or [])

    def test_core_boots_are_exempt(self, build):
        """candidateItemScores never carries boots; they are argued in
        bootsReason. A tier-3 boot in the ladder core must not demand the
        impossible."""
        report = check(build, ladder_core=["gunmetal-greaves", "armored-advance"])
        assert report.ok, report.flat()

    def test_core_support_items_are_exempt(self, build):
        """Same carve-out the selected-items check has: the free support item
        is mandatory for the role, not selected, so there is nothing to score
        it against."""
        report = check(build, ladder_core=["black-mist-scythe"])
        assert report.ok, report.flat()

    def test_no_core_means_no_new_requirement(self, build):
        assert check(build, ladder_core=None).ok
        assert check(build, ladder_core=[]).ok


class TestItemToItemSynergyField:
    """`synergyWith` exists because per-item scoring cannot express "this is
    worth more BECAUSE that is in the build" -- Guinsoo's doubling every other
    on-hit item, Runaan's turning single-target on-hit into AoE.

    Asking for it in prose produced nothing measurable: zero of 25 scored
    items across five champions named a partner. A field can be checked, which
    is the same lesson the ladder-core scoring rule taught.

    Cleaned, never failed: the list is commentary on the decision, not the
    decision, so a bad reference is dropped with a warning rather than costing
    a regeneration.
    """

    @staticmethod
    def _partner(build):
        """A real item that is NOT the first score row's own item."""
        own = build["candidateItemScores"][0]["item"]
        return next(r["item"] for r in build["candidateItemScores"][1:]
                    if r["item"] != own)

    def test_valid_references_survive(self, build):
        partner = self._partner(build)
        build["candidateItemScores"][0]["synergyWith"] = [partner]
        report = check(build)
        assert report.ok, report.flat()
        assert build["candidateItemScores"][0]["synergyWith"] == [partner]

    def test_an_unknown_slug_is_dropped_with_a_warning(self, build):
        partner = self._partner(build)
        build["candidateItemScores"][0]["synergyWith"] = [partner, "not-a-real-item"]
        report = check(build)
        assert report.ok, report.flat()
        assert build["candidateItemScores"][0]["synergyWith"] == [partner]
        assert any("not-a-real-item" in w for w in report.warnings)

    def test_self_reference_is_dropped(self, build):
        row = build["candidateItemScores"][0]
        row["synergyWith"] = [row["item"]]
        report = check(build)
        assert report.ok, report.flat()
        assert build["candidateItemScores"][0]["synergyWith"] == []
        assert any("itself" in w for w in report.warnings)

    def test_boots_cannot_be_a_synergy_target(self, build):
        """candidateItemScores is a non-boots list; a boot reference here is a
        category error, not a synergy."""
        row = build["candidateItemScores"][0]
        row["synergyWith"] = ["ionian-boots-of-lucidity"]
        report = check(build)
        assert report.ok, report.flat()
        assert build["candidateItemScores"][0]["synergyWith"] == []

    def test_absent_or_empty_normalises_to_a_list(self, build):
        """An item genuinely can stand alone. Absent must not become a failure
        -- and must not become None either, or the frontend has to guard it."""
        build["candidateItemScores"][0].pop("synergyWith", None)
        build["candidateItemScores"][1]["synergyWith"] = []
        report = check(build)
        assert report.ok, report.flat()
        assert build["candidateItemScores"][0]["synergyWith"] == []
        assert build["candidateItemScores"][1]["synergyWith"] == []

    def test_duplicates_collapse(self, build):
        partner = self._partner(build)
        build["candidateItemScores"][0]["synergyWith"] = [partner, partner]
        assert check(build).ok
        assert build["candidateItemScores"][0]["synergyWith"] == [partner]


class TestLadderCoreInCounterMode:
    """The REQUIRED CANDIDATES rule is what stops identity drift: the model
    must SCORE the items real top-50 players build on this champion, whether
    or not they reach the build.

    Counter mode was shown that block and then never held to it, so a counter
    build could skip the champion's staple items silently. Answering an enemy
    composition is not a licence to stop playing the champion.
    """

    def _page(self):
        return {"keystone": "Lethal Tempo", "minors": ["Brutal", "Cut Down", "Legend: Alacrity"],
                "flex": "Bone Plating"}

    def test_a_counter_build_that_skips_a_staple_item_fails(self):
        from web.advisor import prompt as prompt_mod
        core = [s for s in prompt_mod.ladder_core_slugs("Vayne")
                if validate_mod._completed_non_boots(s)]
        assert core, "Vayne should have a ladder core to require"
        chosen = core[:2]
        res = {"items": chosen,
               "candidateItemScores": [{"item": s, "score": 80} for s in chosen],
               "runes": self._page()}
        report = check(res, mode="counter", ladder_core=core, hard_cc_count=4)
        assert not report.ok
        assert any("required candidates" in str(e) for e in report.errors.get("scores", []))

    def test_the_counter_message_does_not_demand_prose(self):
        """Counter mode returns scores without reasons on purpose, so the
        failure must not ask for something the mode forbids."""
        from web.advisor import prompt as prompt_mod
        core = [s for s in prompt_mod.ladder_core_slugs("Vayne")
                if validate_mod._completed_non_boots(s)]
        res = {"items": core[:1],
               "candidateItemScores": [{"item": core[0], "score": 80}],
               "runes": self._page()}
        report = check(res, mode="counter", ladder_core=core, hard_cc_count=4)
        text = " ".join(str(e) for e in report.errors.get("scores", []))
        assert "a score, whether" in text and "reason" not in text


class TestAntiHealGate:
    """Against three of the heaviest healers in the game the model built no
    Grievous Wounds at all, identically across three runs, and raising the
    healing signal did not change it. Nothing was blocking it: every anti-heal
    item was in the pool and named in the prompt, and it scored one at 75 then
    took five items scoring 88 and above. Prose loses a scoring contest."""

    BUILD = ["blade-of-the-ruined-king", "guinsoos-rageblade", "terminus",
             "wits-end", "amaranths-twinguard"]

    def _run(self, items, spells=("Flash", "Ghost"), healing="high"):
        return validate_mod.validate(
            {"items": list(items), "summoners": list(spells), "counterSummary": {}},
            mode="counter", healing_level=healing)

    def test_it_fails_a_build_with_no_grievous_wounds(self):
        assert any("Grievous Wounds" in m for m in self._run(self.BUILD).flat())

    def test_any_anti_heal_item_satisfies_it(self):
        build = self.BUILD[:3] + ["chempunk-chainsword", "amaranths-twinguard"]
        assert not any("Grievous Wounds" in m for m in self._run(build).flat())

    def test_ignite_satisfies_it(self):
        """50% Grievous Wounds out of a summoner slot IS the answer; demanding
        an item as well would be demanding two."""
        report = self._run(self.BUILD, spells=("Flash", "Ignite"))
        assert not any("Grievous Wounds" in m for m in report.flat())

    def test_it_stays_silent_below_high(self):
        assert not any("Grievous Wounds" in m
                       for m in self._run(self.BUILD, healing="medium").flat())

    def test_it_stays_silent_outside_counter_mode(self):
        report = validate_mod.validate({"items": list(self.BUILD), "summoners": ["Flash", "Ghost"]},
                          mode="studio", healing_level="very_high")
        assert not any("Grievous Wounds" in m for m in report.flat())


class TestCleanseContradiction:
    """A Hecarim build reported Lissandra's point-and-click ultimate as having
    no answer while Mercurial Scimitar sat in its own pool -- an item whose
    entire text is removing all crowd control from you. The item data was never
    missing; actives reach the prompt with their full text."""

    def _summary(self, threats, items, pool=()):
        return validate_mod.validate({"items": list(items), "summoners": ["Flash", "Smite"],
                         "counterSummary": {"unansweredThreats": list(threats)}},
                        mode="counter", allowed_items=list(pool))

    def test_it_fails_when_the_cleanse_is_in_the_build(self):
        report = self._summary(["Lissandra's point-and-click ultimate cannot be dodged"],
                               ["trinity-force", "spear-of-shojin", "deaths-dance",
                                "seryldas-grudge", "mercurial-scimitar"])
        assert any("unanswerable" in m for m in report.flat())

    def test_it_fails_when_the_cleanse_is_merely_available(self):
        report = self._summary(["their stun chain is unavoidable"],
                               ["trinity-force", "spear-of-shojin", "deaths-dance",
                                "seryldas-grudge", "black-cleaver"],
                               pool=["mercurial-scimitar"])
        assert any("in this champion's pool" in m for m in report.flat())

    def test_it_ignores_a_threat_that_is_not_crowd_control(self):
        report = self._summary(["their global ultimate covers the whole map"],
                               ["trinity-force", "spear-of-shojin", "deaths-dance",
                                "seryldas-grudge", "mercurial-scimitar"])
        assert not any("unanswerable" in m for m in report.flat())

    def test_it_is_repairable_in_isolation(self):
        """counterSummary repairs on its own, so the fix is one small call and
        never a regeneration -- which is why this is a failure rather than a
        warning that leaves the wrong sentence on screen."""
        from web.advisor import repair
        report = self._summary(["their stun is unavoidable"],
                               ["trinity-force", "spear-of-shojin", "deaths-dance",
                                "seryldas-grudge", "mercurial-scimitar"])
        targeted, blocking = repair.plan(report.sections())
        assert "counterSummary" in targeted and not blocking

    def test_an_ally_targeted_cleanse_does_not_count(self):
        """Mikael's removes crowd control from an ALLIED champion, which is not
        an answer to being locked down yourself."""
        from web.advisor.validate import CLEANSE_ITEMS
        assert "mikaels-blessing" not in CLEANSE_ITEMS
        assert "mercurial-scimitar" in CLEANSE_ITEMS

    def test_naming_the_item_and_dismissing_it_is_compliance(self):
        """The message offers two branches: build it, or say why it is not
        worth the slot. The model took the second -- "Mercurial Scimitar would
        compromise the core damage engine" -- and the gate rejected it twice
        more, which is the check refusing the answer it asked for."""
        report = self._summary(
            ["Lissandra's point-and-click stun cannot be dodged; Mercurial "
             "Scimitar would cost this build its damage engine"],
            ["trinity-force", "spear-of-shojin", "deaths-dance",
             "seryldas-grudge", "mercurial-scimitar"])
        assert not any("unanswerable" in m for m in report.flat())


class TestBlueBuffGate:
    """A jungler holds blue buff from the first clear, so a rune slot spent on
    mana buys what the map hands over for free."""

    def _page(self, role, minors):
        return validate_mod.validate(
            {"items": ["trinity-force", "spear-of-shojin", "deaths-dance",
                       "seryldas-grudge", "black-cleaver"],
             "summoners": ["Flash", "Smite"], "counterSummary": {},
             "runes": {"keystone": "Conqueror", "minors": minors, "flex": "Second Wind"}},
            mode="counter", role=role)

    def test_a_mana_rune_fails_on_a_jungle_page(self):
        report = self._page("Jungle", ["Manaflow Band", "Brutal", "Triumph"])
        assert any("blue buff" in m.lower() for m in report.flat())

    def test_the_same_rune_is_fine_in_a_lane(self):
        """Blue buff is the jungler's; a mid laner buys its own mana."""
        report = self._page("Mid", ["Manaflow Band", "Brutal", "Triumph"])
        assert not any("blue buff" in m.lower() for m in report.flat())

    def test_runes_that_merely_mention_mana_are_untouched(self):
        """Triumph restores mana on a takedown but is taken for the health,
        and Fleet Footwork's mana line is incidental to a keystone about
        movement. Excluding either would cost a jungler a good rune to solve a
        problem it does not have."""
        report = self._page("Jungle", ["Triumph", "Brutal", "Legend: Alacrity"])
        assert not any("blue buff" in m.lower() for m in report.flat())
        from web.advisor import runemeta
        assert runemeta.MANA_RUNES == ("Manaflow Band",)

    def test_the_prompt_says_so_too(self):
        """The gate is the teeth; the pool block is where the model is told,
        and only a jungle build should carry the note."""
        from web.advisor import runemeta
        assert "BLUE BUFF" in runemeta.pool_text_block("Jungle")
        assert "BLUE BUFF" not in runemeta.pool_text_block("Mid")
        assert "BLUE BUFF" not in runemeta.pool_text_block()

    def test_it_is_repairable_rather_than_a_regeneration(self):
        """Runes repair on their own, so a mana rune costs one short call and
        never a whole regeneration. Asserted on the rune section alone: this
        fixture is a skeleton and trips other checks that are not the point."""
        from web.advisor import repair
        report = self._page("Jungle", ["Manaflow Band", "Brutal", "Triumph"])
        targeted, _blocking = repair.plan(["runes"])
        assert "runes" in targeted
        assert "runes" in report.sections()
