"""Summoner spells.

Two halves. `summoners_for` is the static rule table, which is now the FALLBACK
rather than the answer, and is tested here unchanged because a fallback that has
quietly rotted is worse than no fallback. `enforce` is the new path: the model
picks, and these tests are the guarantee that no model output can put a jungler
on the rift without Smite.
"""
from __future__ import annotations

import pytest

from web.advisor import profiles, summoners


def spells(champion: str) -> list[str]:
    record = profiles.CHAMPIONS.get(champion) or {}
    return summoners.summoners_for(
        champion, record.get("role", ""), record.get("class", ""))[0]


class TestJungle:
    def test_every_jungler_gets_smite(self):
        for name, record in profiles.CHAMPIONS.items():
            if record.get("role") == "Jungle":
                assert "Smite" in spells(name), name

    def test_no_laner_gets_smite(self):
        for name, record in profiles.CHAMPIONS.items():
            if record.get("role") not in ("Jungle", "", None):
                assert "Smite" not in spells(name), name

    def test_flash_is_the_default_jungle_partner(self):
        assert spells("Kindred") == ["Flash", "Smite"]

    def test_a_run_down_jungler_gets_ghost_and_smite(self):
        """Hecarim is both, and the run-down rule wins the second slot."""
        assert spells("Hecarim") == ["Ghost", "Smite"]


class TestRunDownChampions:
    @pytest.mark.parametrize("champion", ["Darius", "Olaf", "Nasus", "Singed", "Gwen"])
    def test_they_get_ghost_and_flash_outside_the_jungle(self, champion):
        assert spells(champion) == ["Ghost", "Flash"]

    def test_the_rule_beats_the_class_default(self):
        """Singed is a Tank and Gwen a Bruiser; neither falls to Flash+Ignite."""
        assert "Ghost" in spells("Singed")
        assert "Ghost" in spells("Gwen")


class TestSupports:
    @pytest.mark.parametrize("champion", ["Janna", "Lulu", "Nami", "Soraka", "Milio"])
    def test_protective_supports_get_heal_and_flash(self, champion):
        assert spells(champion) == ["Heal", "Flash"]

    @pytest.mark.parametrize("champion", ["Leona", "Alistar", "Blitzcrank",
                                          "Nautilus", "Braum", "Rell", "Maokai"])
    def test_engage_supports_get_ignite_and_flash(self, champion):
        assert spells(champion) == ["Ignite", "Flash"]

    def test_an_assassin_support_counts_as_an_engage_support(self):
        """Pyke is a kill-lane support; Heal suits him no better than Leona."""
        assert spells("Pyke") == ["Ignite", "Flash"]

    def test_every_support_carries_flash(self):
        for name, record in profiles.CHAMPIONS.items():
            if record.get("role") == "Support":
                assert "Flash" in spells(name), name


class TestMarksmen:
    @pytest.mark.parametrize("champion", ["Lucian", "Vayne", "Ezreal", "Tristana",
                                          "Samira", "Zeri", "Kai'Sa"])
    def test_marksmen_with_a_dash_get_flash_and_barrier(self, champion):
        assert spells(champion) == ["Flash", "Barrier"]

    @pytest.mark.parametrize("champion", ["Ashe", "Jhin", "Miss Fortune",
                                          "Draven", "Sivir", "Kog'Maw"])
    def test_marksmen_without_a_dash_get_ghost_and_flash(self, champion):
        assert spells(champion) == ["Ghost", "Flash"]

    def test_marksman_junglers_follow_the_jungle_rule_instead(self):
        """The user's carve-out: 'apart from junglers like graves, kindred'."""
        assert spells("Graves") == ["Flash", "Smite"]
        assert spells("Kindred") == ["Flash", "Smite"]

    def test_jinx_is_not_treated_as_mobile(self):
        """Her Flame Chompers text interrupts enemy dashes; she has none."""
        assert spells("Jinx") == ["Ghost", "Flash"]

    def test_varus_is_not_treated_as_mobile(self):
        """Piercing Arrow charges up, it does not move him."""
        assert spells("Varus") == ["Ghost", "Flash"]

    def test_corki_is_treated_as_mobile(self):
        """Valkyrie 'Flies a short distance' -- a dash no keyword scan catches."""
        assert spells("Corki") == ["Flash", "Barrier"]

    def test_a_marksman_support_takes_the_support_rule(self):
        assert spells("Senna") == ["Heal", "Flash"]


class TestDefaultAndInvariants:
    def test_the_fallback_is_flash_and_ignite(self):
        assert spells("Annie") == ["Flash", "Ignite"]

    def test_every_champion_gets_exactly_two_distinct_known_spells(self):
        for name in profiles.CHAMPIONS:
            got = spells(name)
            assert len(got) == 2, name
            assert len(set(got)) == 2, name
            assert all(s in summoners.SPELLS for s in got), name

    def test_every_champion_gets_a_reason(self):
        for name, record in profiles.CHAMPIONS.items():
            _, reason = summoners.summoners_for(
                name, record.get("role", ""), record.get("class", ""))
            assert len(reason) > 20, name

    def test_resolved_returns_the_frontend_shape(self):
        entries, reason = summoners.resolved("Hecarim", "Jungle", "Bruiser")
        assert [e["name"] for e in entries] == ["Ghost", "Smite"]
        assert all(e["icon"].startswith("https://") for e in entries)
        assert reason


class TestEnforceInTheJungle:
    """Smite is a guarantee, not a request. The model cannot spend that slot."""

    def test_a_jungler_who_picked_flash_keeps_it_and_gains_smite(self):
        assert summoners.enforce(["Flash", "Ignite"], "Jungle") == ["Flash", "Smite"]

    def test_a_jungler_who_picked_ghost_keeps_ghost(self):
        assert summoners.enforce(["Ghost", "Ignite"], "Jungle") == ["Ghost", "Smite"]

    def test_a_jungler_who_forgot_smite_entirely_still_gets_it(self):
        """The failure the old lookup existed to prevent."""
        assert summoners.enforce(["Flash", "Exhaust"], "Jungle") == ["Flash", "Smite"]

    def test_a_jungler_who_returned_only_smite_has_no_partner_to_keep(self):
        """Nothing to salvage, so the caller falls back to the rule table."""
        assert summoners.enforce(["Smite"], "Jungle") is None

    def test_a_jungler_with_an_illegal_partner_falls_back(self):
        assert summoners.enforce(["Ignite", "Exhaust"], "Jungle") is None
        assert summoners.enforce(["Smite", "Heal"], "Jungle") is None

    def test_smite_is_never_the_partner_slot(self):
        """Smite twice must not resolve to a loadout of two Smites."""
        assert summoners.enforce(["Smite", "Smite"], "Jungle") is None

    def test_the_role_check_is_not_case_sensitive(self):
        assert summoners.enforce(["Flash", "Ignite"], "jungle") == ["Flash", "Smite"]


class TestEnforceInLane:
    def test_a_laner_gets_what_they_asked_for(self):
        assert summoners.enforce(["Cleanse", "Flash"], "Mid") == ["Cleanse", "Flash"]

    def test_a_laner_can_skip_flash_entirely(self):
        """Flash is the usual anchor, not a rule. The model may trade it."""
        assert summoners.enforce(["Exhaust", "Barrier"], "Bot") == ["Exhaust", "Barrier"]

    def test_smite_is_stripped_from_a_laner(self):
        assert summoners.enforce(["Smite", "Flash", "Ignite"], "Mid") == ["Flash", "Ignite"]

    def test_a_laner_left_with_one_usable_spell_falls_back(self):
        assert summoners.enforce(["Smite", "Flash"], "Mid") is None


class TestEnforceHandlesModelJunk:
    def test_unknown_spells_are_discarded(self):
        assert summoners.enforce(["Teleport", "Flash", "Ignite"], "Mid") == ["Flash", "Ignite"]
        assert summoners.enforce(["Teleport", "Clarity"], "Mid") is None

    def test_casing_and_whitespace_are_normalised(self):
        assert summoners.enforce([" flash ", "IGNITE"], "Mid") == ["Flash", "Ignite"]

    def test_duplicates_collapse_rather_than_filling_both_slots(self):
        assert summoners.enforce(["Flash", "Flash", "Ignite"], "Mid") == ["Flash", "Ignite"]

    def test_extras_beyond_two_are_dropped(self):
        assert summoners.enforce(["Flash", "Ignite", "Heal", "Barrier"], "Mid") == \
            ["Flash", "Ignite"]

    @pytest.mark.parametrize("junk", [[], None, "Flash", [None], [{"name": "Flash"}], [123]])
    def test_malformed_input_never_raises(self, junk):
        """A model returning the wrong TYPE must fall back, not 500 the build."""
        assert summoners.enforce(junk, "Mid") is None
        assert summoners.enforce(junk, "Jungle") is None

    def test_icons_for_returns_the_frontend_shape(self):
        entries = summoners.icons_for(["Ghost", "Smite"])
        assert [e["name"] for e in entries] == ["Ghost", "Smite"]
        assert all(e["icon"].startswith("https://") for e in entries)


class TestTheAllowedPool:
    """Which spells a request may offer at all.

    Reported on Jinx: a standard studio build came back with Heal. Heal heals
    the ALLY it is cast on, which is the reason to bring it, so on a solo laner
    it is a worse Barrier. And with no enemy team a summoner pick cannot be a
    read, so the spells that answer a specific matchup are not offered blind.
    """

    def test_studio_offers_the_five_the_typical_comp_justifies(self):
        """The studio is not blind: the prompt assumes the typical ranked comp,
        and Barrier is a read of the burst threat that comp guarantees mid.
        Ignite stays out -- an archetype cannot tell you a lane is killable."""
        assert summoners.allowed_pool("Mid", enemies_known=False) == frozenset(
            {"Flash", "Exhaust", "Ghost", "Cleanse", "Barrier"})

    def test_studio_withholds_heal_and_ignite(self):
        pool = summoners.allowed_pool("Bot", enemies_known=False)
        assert "Heal" not in pool and "Ignite" not in pool

    def test_counter_opens_everything_except_heal(self):
        pool = summoners.allowed_pool("Mid", enemies_known=True)
        assert "Ignite" in pool and "Barrier" in pool
        assert "Heal" not in pool

    def test_a_support_keeps_heal_in_both_modes(self):
        for known in (True, False):
            assert "Heal" in summoners.allowed_pool("Support", enemies_known=known)

    def test_smite_is_never_selectable(self):
        for role in ("Mid", "Jungle", "Support"):
            for known in (True, False):
                assert "Smite" not in summoners.allowed_pool(role, known)


class TestTheReportedJinxBug:
    def test_heal_on_a_studio_marksman_is_refused(self):
        assert summoners.enforce(["Heal", "Flash"], "Bot", enemies_known=False) is None

    def test_ignite_on_a_studio_build_is_refused(self):
        assert summoners.enforce(["Ignite", "Flash"], "Mid", enemies_known=False) is None

    def test_the_studio_four_are_accepted(self):
        assert summoners.enforce(["Flash", "Exhaust"], "Bot", enemies_known=False) == \
            ["Flash", "Exhaust"]

    def test_heal_survives_for_a_support(self):
        assert summoners.enforce(["Heal", "Flash"], "Support", enemies_known=False) == \
            ["Heal", "Flash"]

    def test_the_fallback_cannot_smuggle_a_banned_spell_back_in(self):
        """Vayne's lookup answer is Flash+Barrier, and Barrier is not offered
        in studio mode. Falling back must not become a way around the rule."""
        names = [e["name"] for e in
                 summoners.resolved("Vayne", "Bot", "Marksman", enemies_known=False)[0]]
        assert set(names) <= summoners.allowed_pool("Bot", enemies_known=False)


class TestOffRoleJungle:
    def test_a_champion_who_is_not_a_jungler_still_gets_smite(self):
        """The REQUESTED role decides, not the champion's usual one."""
        assert summoners.enforce(["Flash", "Ignite"], "Jungle", enemies_known=False) == \
            ["Flash", "Smite"]

    def test_the_fallback_also_forces_smite_off_role(self):
        names = [e["name"] for e in
                 summoners.resolved("Lux", "Jungle", "Mage", enemies_known=False)[0]]
        assert "Smite" in names


class TestMobility:
    def test_a_champion_with_no_dash_reads_as_immobile(self):
        assert not summoners.has_mobility("Jinx", "Fires rockets. Sets traps.")

    def test_the_curated_marksman_list_covers_what_the_text_scan_misses(self):
        """Ezreal's Arcane Shift and Vayne's Tumble are both dashes the ability
        text does not describe with a keyword."""
        for name in ("Ezreal", "Vayne"):
            assert summoners.has_mobility(name, "")

    def test_a_dash_in_the_text_counts(self):
        assert summoners.has_mobility("Nobody", "Dashes to the target location.")
