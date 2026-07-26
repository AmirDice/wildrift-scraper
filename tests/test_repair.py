"""Targeted repair: fix the broken section, preserve everything else."""
from __future__ import annotations

import json

from conftest import check
from web.advisor import repair


class TestPlan:
    def test_a_rune_failure_is_repairable_in_isolation(self):
        targeted, blocking = repair.plan(["runes"])
        assert targeted == ["runes"]
        assert blocking == []

    def test_an_item_failure_forces_full_regeneration(self):
        """The five items are the spine: scores, swaps and rune reasoning all
        describe them, so patching them alone would leave the rest stale."""
        targeted, blocking = repair.plan(["items"])
        assert blocking == ["items"]

    def test_a_scores_failure_is_repairable(self):
        """Scores describe the build without being it. The first live run cost a
        full regeneration because this was excluded."""
        targeted, blocking = repair.plan(["scores"])
        assert targeted == ["scores"]
        assert blocking == []

    def test_the_scores_repair_prompt_pins_the_existing_build(self, build):
        text = repair.repair_prompt("scores", build, ["missing a row"], ["black-cleaver"])
        assert "do not change it" in text
        assert "black-cleaver" in text

    def test_a_mixed_failure_is_treated_as_blocking(self):
        targeted, blocking = repair.plan(["runes", "items"])
        assert blocking == ["items"]


class TestRepairPrompt:
    def test_it_carries_the_invalid_section_and_the_exact_errors(self, build):
        build["runes"]["minors"] = ["Brutal", "Triumph", "Legend: Alacrity"]
        report = check(build)
        text = repair.repair_prompt("runes", build, report.errors["runes"], [])
        assert "THE INVALID SECTION" in text
        assert "Triumph" in text
        assert "slots 1, 2 and 3" in text

    def test_it_supplies_the_pool_needed_to_fix_the_section(self, build):
        text = repair.repair_prompt("runes", build, ["broken"], [])
        assert "LEGAL RUNE OPTIONS" in text
        assert "Conqueror" in text          # keystones listed
        assert "slot 1:" in text            # slot map listed

    def test_it_forbids_touching_anything_else(self, build):
        text = repair.repair_prompt("runes", build, ["broken"], [])
        assert "Do not restate or change any other part of the build" in text

    def test_a_boots_repair_only_ships_the_boots_pool(self, build):
        text = repair.repair_prompt("boots", build, ["broken"], [])
        assert "LEGAL BOOTS" in text
        assert "LEGAL RUNE OPTIONS" not in text

    def test_it_is_far_smaller_than_a_full_prompt(self, build):
        """The saving is the point: a full regeneration re-sends ~65 KB."""
        text = repair.repair_prompt("runes", build, ["broken"], [])
        assert len(text) < 5_000


class TestApplyRepair:
    def test_it_replaces_only_the_section_it_owns(self, build):
        original_items = list(build["items"])
        patch = {"runes": {"keystone": "Electrocute", "primaryTree": "Domination",
                           "minors": ["Cheap Shot", "Hubris", "Eyeball Collector"],
                           "flex": "Celerity"}}
        assert repair.apply_repair(build, "runes", patch)
        assert build["runes"]["keystone"] == "Electrocute"
        assert build["items"] == original_items

    def test_it_ignores_keys_the_section_does_not_own(self, build):
        """A model that returns a whole new build must not overwrite the parts
        that already validated."""
        original_items = list(build["items"])
        patch = {
            "runes": {"keystone": "Electrocute", "primaryTree": "Domination",
                      "minors": ["Cheap Shot", "Hubris", "Eyeball Collector"],
                      "flex": "Celerity"},
            "items": ["thornmail", "thornmail", "thornmail", "thornmail", "thornmail"],
            "buildScore": {"overall": 1},
        }
        repair.apply_repair(build, "runes", patch)
        assert build["items"] == original_items
        assert build["buildScore"]["overall"] == 80.0

    def test_it_reports_when_the_repair_returned_nothing_usable(self, build, capsys):
        assert not repair.apply_repair(build, "runes", {"nonsense": 1})
        captured = capsys.readouterr()
        assert captured.out == ""          # never stdout
        assert "returned none of" in captured.err


class TestRepairActuallyFixes:
    def test_an_illegal_page_validates_after_a_correct_patch(self, build):
        build["runes"]["minors"] = ["Brutal", "Triumph", "Legend: Alacrity"]
        assert check(build).sections() == ["runes"]

        repair.apply_repair(build, "runes", {"runes": {
            "keystone": "Conqueror", "primaryTree": "Precision",
            "minors": ["Brutal", "Last Stand", "Legend: Alacrity"],
            "flex": "Celerity"}})
        report = check(build)
        assert report.ok, report.flat()

    def test_a_bad_boot_upgrade_is_fixed_without_regenerating_items(self, build):
        original_items = list(build["items"])
        build["boots"] = "not-a-boot"
        assert check(build).sections() == ["boots"]

        repair.apply_repair(build, "boots", {"boots": "ionian-boots-of-lucidity"})
        report = check(build)
        assert report.ok, report.flat()
        assert build["items"] == original_items
        # The tier-3 is derived, never taken from the model.
        assert build["bootsUpgrade"] == "crimson-lucidity"
