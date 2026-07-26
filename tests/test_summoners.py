"""Summoner assignment: flat rules, applied in code, correct by construction."""
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
