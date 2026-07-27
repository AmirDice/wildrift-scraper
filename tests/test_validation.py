"""Deterministic validation: what must be rejected, and what must not be."""
from __future__ import annotations

from conftest import check, make_build


def errors_in(report, section) -> str:
    return " ".join(report.errors.get(section, []))


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
        report = check(build, enemies_known=True)
        assert report.ok, report.flat()
        assert any("grievous-wounds" in w for w in report.warnings)


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


class TestSummonersAreNoLongerValidated:
    """They are assigned in code after validation, so the model cannot get them
    wrong and a build must not fail over them."""

    def test_whatever_the_model_returned_is_discarded(self, build):
        build["summoners"] = ["Smite", "Smite", "nonsense"]
        report = check(build, role="Mid")
        assert report.ok, report.flat()
        assert "summoners" not in build

    def test_a_jungler_missing_smite_no_longer_fails_the_build(self, build):
        build["summoners"] = ["Flash", "Ignite"]
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
