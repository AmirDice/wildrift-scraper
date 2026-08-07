"""Prompt assembly, and the contract that keeps /api/build alive."""
from __future__ import annotations

import io
import json
from contextlib import redirect_stdout

import pytest

from web import build_advisor as advisor
from web.advisor import itemmeta, profiles, runemeta
from web.advisor import prompt as prompt_mod


def build_prompt(champion="Hecarim", role="Jungle", enemies=(), **kwargs) -> str:
    """Assemble the real user message by intercepting the model call."""
    captured = {}

    def capture(_key, text):
        captured["prompt"] = text
        raise SystemExit(0)

    original = advisor._call
    advisor._call = capture
    try:
        advisor.advise(champion=champion, role=role, enemies=list(enemies), **kwargs)
    except SystemExit:
        pass
    finally:
        advisor._call = original
    return captured.get("prompt", "")


@pytest.fixture(scope="module")
def hecarim_unknown(monkeypatch_module=None):
    import os
    # The capture intercepts advisor._call before any network use, but advise()
    # checks for the DEFAULT model's key first -- which is Gemini now. Locally
    # _ensure_gemini_key() finds the real key in web-next/.env.local; CI has
    # neither, so without this the prompt comes back empty.
    os.environ.setdefault("GEMINI_API_KEY", "test-key-not-used")
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key-not-used")
    return build_prompt()


@pytest.fixture(scope="module")
def hecarim_known():
    import os
    os.environ.setdefault("GEMINI_API_KEY", "test-key-not-used")
    os.environ.setdefault("DEEPSEEK_API_KEY", "test-key-not-used")
    return build_prompt(enemies=["Ashe", "Master Yi", "Malphite"], mode="counter")


class TestStdoutContract:
    """web-next/src/app/api/build/route.ts does JSON.parse on this process's
    stdout. Anything else printed there takes the live build tool down, which
    makes this the highest-consequence test in the suite."""

    def test_diagnostics_go_to_stderr_not_stdout(self):
        import os
        os.environ.setdefault("DEEPSEEK_API_KEY", "test-key-not-used")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            build_prompt()
        assert buffer.getvalue() == "", (
            "the advisor wrote to stdout while assembling a prompt; /api/build "
            f"parses stdout as JSON and would break. Got: {buffer.getvalue()[:200]!r}")

    def test_profile_derivation_logs_to_stderr(self, capsys):
        profiles.profile("Hecarim", log=True)
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "artifact" in captured.err


class TestSystemMessage:
    def test_it_no_longer_claims_to_produce_the_highest_win_rate(self):
        assert "highest-winrate loadout" not in prompt_mod.SYSTEM
        assert "highest expected practical win rate" in prompt_mod.SYSTEM

    def test_it_says_category_scores_are_estimates_not_measurements(self):
        assert "COACH ESTIMATES" in prompt_mod.SYSTEM
        assert "not measured or simulated" in prompt_mod.SYSTEM

    def test_it_mentions_no_simulator_or_fight_engine(self):
        lowered = prompt_mod.SYSTEM.lower()
        assert "fight engine" not in lowered
        assert "simulator" not in lowered

    def test_it_asks_for_the_split_score_lists(self):
        assert "candidateItemScores" in prompt_mod.SYSTEM
        assert "mandatoryAuditScores" in prompt_mod.SYSTEM
        assert "do NOT count toward" in prompt_mod.SYSTEM

    def test_it_states_that_a_ratio_is_not_a_licence_to_itemise(self):
        assert "does NOT make items granting that stat viable" in prompt_mod.SYSTEM

    def test_it_carries_the_tie_breakers_and_both_rubrics(self):
        assert "TIE-BREAKERS" in prompt_mod.SYSTEM
        assert "ITEM SCORE RUBRIC" in prompt_mod.SYSTEM
        assert "BUILD SCORE RUBRIC" in prompt_mod.SYSTEM

    def test_it_preserves_the_load_bearing_old_instructions(self):
        """Section 20: these behaviours were working and must survive."""
        for phrase in [
            "PURCHASE ORDER IS TIMING, NOT A RANKING",
            "your training data",
            "Return ONLY JSON",
            "15-20 minutes",
            "only after deciding, explain",
        ]:
            assert phrase in prompt_mod.SYSTEM, phrase


class TestChampionBlock:
    def test_the_profiles_reach_the_prompt(self, hecarim_unknown):
        assert "COMBAT PROFILE" in hecarim_unknown
        assert "SCALING PROFILE" in hecarim_unknown
        assert "BUILD IDENTITY PROFILE" in hecarim_unknown
        assert '"primaryCombatEngine"' in hecarim_unknown
        assert '"approvedBuildPaths"' in hecarim_unknown
        assert '"repeatedOnHitReliance": "low"' in hecarim_unknown

    def test_system_prioritises_repeatable_damage_source_over_one_ratio(self):
        assert "BUILD IDENTITY IS AUTHORITATIVE" in prompt_mod.SYSTEM
        assert "isolated ability prints the largest ratio" in prompt_mod.SYSTEM

    def test_build_path_viability_overrides_raw_ratio(self, hecarim_unknown):
        assert "BUILD-PATH VIABILITY" in hecarim_unknown
        assert '"totalAD": "core"' in hecarim_unknown
        assert '"AP": "not_viable"' in hecarim_unknown

    def test_malformed_text_is_cleaned_and_flagged(self, hecarim_unknown):
        assert "STRUCTURED EFFECTS" in hecarim_unknown
        assert "DATA QUALITY WARNING" in hecarim_unknown
        # The cleaned ability line no longer carries the dead assignment.
        warpath = [line for line in hecarim_unknown.splitlines()
                   if line.startswith("[P] Warpath")]
        assert warpath and "0 =" not in warpath[0]

    def test_the_old_coarse_tags_are_gone(self, hecarim_unknown):
        assert "mechanics=[" not in hecarim_unknown
        assert "scalesWith=[" not in hecarim_unknown


class TestRulesTiers:
    def test_two_tiers_with_no_redundancy_groups(self, hecarim_unknown):
        """Owner decision (2026-08-04): the redundancy groups are empty -- the
        only one ever defined was grievous-wounds, and it swept in Serylda's
        Grudge, a mainline armor-pen item the ladder pairs freely. With no
        groups the section must VANISH, not render as an empty tier, and the
        letters must close ranks so the model never sees a gap."""
        assert "A. HARD LEGALITY" in hecarim_unknown
        assert "B. REDUNDANCY" not in hecarim_unknown
        assert "why it is usually wrong" not in hecarim_unknown
        # the factual `grievous-wounds` passive TAG stays on pool lines --
        # only the redundancy rule about it is gone
        assert "B. DEFAULT STRATEGY" in hecarim_unknown
        assert "RULES, IN TWO TIERS" in hecarim_unknown

    def test_terminus_appears_in_the_hard_armor_penetration_group(self, hecarim_unknown):
        line = [l for l in hecarim_unknown.splitlines()
                if l.strip().startswith("armor-penetration:")][0]
        for slug in ("black-cleaver", "terminus", "lord-dominiks-regard",
                     "mortal-reminder", "seryldas-grudge"):
            assert slug in line

    def test_guardian_angel_is_late_strategic_not_forbidden(self, hecarim_unknown):
        assert "guardian-angel is a LATE STRATEGIC option" in hecarim_unknown
        assert "position 4 or later" in hecarim_unknown


class TestUnknownEnemyHandling:
    def test_the_unknown_enemy_block_assumes_the_typical_comp(self, hecarim_unknown):
        """Owner decision (2026-08-04): "you have no evidence" was false --
        ranked comps are highly regular, so with no enemies supplied the model
        builds against the TYPICAL composition, stated as archetypes, and is
        still forbidden from naming specific champions."""
        assert "WHEN THE ENEMY TEAM IS UNKNOWN" in hecarim_unknown
        assert "typical ranked composition" in hecarim_unknown
        assert "Do NOT name specific enemy champions" in hecarim_unknown
        # the old vacuum framing must be gone
        assert "You have no evidence" not in hecarim_unknown

    def test_it_is_absent_when_an_enemy_team_is_supplied(self, hecarim_known):
        assert "WHEN THE ENEMY TEAM IS UNKNOWN" not in hecarim_known

    def test_defensive_boots_are_situational_only_without_enemies(self, hecarim_unknown):
        assert "DEFENSIVE BOOTS -- situationalBoots ONLY" in hecarim_unknown

    def test_defensive_boots_may_be_main_boots_with_enemies(self, hecarim_known):
        assert "available as MAIN boots" in hecarim_known


class TestItemPool:
    def test_withheld_items_are_declared_rather_than_silently_dropped(self, hecarim_unknown):
        assert "ITEMS WITHHELD FROM THE POOL" in hecarim_unknown
        assert "runaans-hurricane" in hecarim_unknown

    def test_the_audit_is_spellblade_for_hecarim(self, hecarim_unknown):
        assert "MANDATORY ITEM AUDIT" in hecarim_unknown
        audit_section = hecarim_unknown.split("MANDATORY ITEM AUDIT")[1].split("\n\n")[0]
        assert "trinity-force" in audit_section
        assert "guinsoos-rageblade" not in audit_section

    def test_the_prompt_is_not_truncated_and_carries_every_section(self, hecarim_unknown):
        for section in ["CHAMPION: Hecarim", "ROLE: Jungle", "RULES, IN TWO TIERS",
                        "BOOTS (pick ONE tier-2", "RUNES (page =", "ITEM POOL"]:
            assert section in hecarim_unknown, section
        assert len(hecarim_unknown) > 40_000

    def test_summoner_spells_are_asked_of_the_model(self, hecarim_unknown):
        """The model picks them now, so the pool and schema field are back.

        This test previously asserted the exact opposite, and inverting it is
        the point: the old design could not see the enemy comp, and a summoner
        choice against a known comp is a judgement, not a lookup.
        """
        assert "SUMMONER SPELLS (choose exactly 2" in hecarim_unknown
        assert '"summoners"' in prompt_mod.SYSTEM
        assert "DO NOT CHOOSE SUMMONER SPELLS" not in prompt_mod.SYSTEM, (
            "the system prompt still tells the model its summoners are discarded, "
            "which contradicts the pool block")

    def test_a_jungler_is_told_smite_is_not_the_decision(self, hecarim_unknown):
        """Hecarim is a jungler, so only the partner slot is open to him."""
        assert "Smite is MANDATORY" in hecarim_unknown
        assert "must be either Flash or Ghost" in hecarim_unknown

    def test_a_laner_is_told_never_to_take_smite(self):
        block = advisor._summoner_block("Mid")
        assert "NEVER take Smite" in block
        assert "Both slots are open" in block


class TestRuneMetadata:
    def test_every_rune_resolves_to_a_tree_and_slot_or_is_a_keystone(self):
        for rune in runemeta.RUNES:
            meta = runemeta.metadata(rune["name"])
            assert meta["tree"], rune["name"]

    def test_the_pool_block_states_the_page_rule(self):
        assert "1 keystone + 3 minors from ONE tree" in runemeta.pool_text_block()


class TestThePlaystyleReachesTheRunes:
    """A playstyle is a brief for the whole build, not just the item list.

    The rune section never mentioned it. The playstyle line sits at the top of
    the prompt so the model COULD apply it, but every word of guidance about it
    was written about items -- and a Sustain build that itemises for healing
    while taking an unrelated keystone has answered half the question.
    """

    def test_the_rune_block_says_the_request_applies_to_it(self, hecarim_unknown):
        assert "THE REQUEST APPLIES TO THE RUNE PAGE" in hecarim_unknown

    def test_it_defers_to_the_kit_the_same_way_the_items_do(self, hecarim_unknown):
        """A rune whose trigger the champion cannot meet is not serving the
        playstyle, exactly as with an item it cannot proc."""
        assert "a rune whose trigger this champion cannot meet" in hecarim_unknown

    def test_the_reasons_must_connect_the_page_to_the_request(self, hecarim_unknown):
        assert "how the page serves what was asked for" in hecarim_unknown


class TestEverySelectedOptionGovernsTheWholeLoadout:
    """Items, boots, runes AND summoners are chosen from one brief.

    Each of the four can serve the request or ignore it independently, and
    almost every option's text was phrased about items -- "cheap first-ITEM
    spikes", "avoid conditional ITEMS", "do not mix in AP ITEMS" -- so the rune
    page and the summoner slots were the parts the request never reached.
    Stated once where the options are introduced rather than repeated inside
    each option's own text, which is written per option while this rule is the
    same for all of them.
    """

    def test_the_scope_covers_every_toggle_not_just_the_playstyle(self, hecarim_unknown):
        assert "EVERY SELECTED OPTION GOVERNS THE ENTIRE LOADOUT" in hecarim_unknown
        for toggle in ("playstyle", "power curve", "optimisation goal",
                       "damage path", "risk tolerance"):
            assert toggle in hecarim_unknown, toggle

    def test_it_names_all_four_parts_of_the_loadout(self, hecarim_unknown):
        for part in ("items", "boots", "rune page", "summoner spells"):
            assert part in hecarim_unknown, part

    def test_it_says_the_item_wording_still_applies_to_the_whole_build(self, hecarim_unknown):
        """Several options are worded about items and are not being rewritten
        one by one; the reader is told to read them as build-wide."""
        assert "read them as applying to the whole build" in hecarim_unknown

    def test_the_summoner_block_carries_it_too(self, hecarim_unknown):
        assert "THE REQUEST APPLIES HERE TOO" in hecarim_unknown

    def test_the_rune_block_carries_it_too(self, hecarim_unknown):
        assert "THE REQUEST APPLIES TO THE RUNE PAGE" in hecarim_unknown

    def test_the_rune_block_names_more_than_the_playstyle(self, hecarim_unknown):
        """Power curve and damage path shape a rune page as much as playstyle."""
        assert "Early-game curve" in hecarim_unknown
        assert "AP path wants runes" in hecarim_unknown

    def test_every_section_defers_to_the_kit_rather_than_the_description(self, hecarim_unknown):
        assert "is not serving the request whatever" in hecarim_unknown
