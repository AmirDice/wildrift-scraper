"""Structured enemy-threat derivation for the counter builder.

The point of this layer is that a tank and a carry do not contribute equally to
damage threat, and that threats are prioritised rather than counted. These tests
pin that behaviour on real champions.
"""
from __future__ import annotations

from web.advisor import threats

# A comp with two physical carries, two tanks, one mage.
PHYS_HEAVY = ["Ashe", "Master Yi", "Malphite", "Leona", "Ahri"]


class TestTeamThreatProfile:
    def test_all_fields_are_categorical(self):
        levels = set(threats._LEVELS)
        profile = threats.team_threat_profile(PHYS_HEAVY)
        for key, value in profile.items():
            if key == "durableTargetCount":
                assert isinstance(value, int)
            else:
                assert value in levels, f"{key}={value}"

    def test_tanks_contribute_less_than_carries_to_damage_threat(self):
        """Two physical carries + assassin should read higher physical than the
        two magic tanks read magic."""
        profile = threats.team_threat_profile(PHYS_HEAVY)
        order = threats._LEVELS
        assert order.index(profile["physicalDamage"]) > order.index(profile["magicDamage"])

    def test_it_counts_durable_targets(self):
        # Malphite + Leona are tanks; Ashe/Yi/Ahri are not.
        assert threats.team_threat_profile(PHYS_HEAVY)["durableTargetCount"] == 2

    def test_layered_cc_reads_high(self):
        # Four of the five have cc.
        profile = threats.team_threat_profile(PHYS_HEAVY)
        assert profile["hardCc"] in ("high", "very_high")

    def test_an_all_tank_comp_has_low_damage_high_durability(self):
        profile = threats.team_threat_profile(["Malphite", "Leona", "Ornn", "Sion", "Alistar"])
        order = threats._LEVELS
        assert order.index(profile["physicalDamage"]) <= order.index("medium")
        assert profile["durableTargetCount"] >= 4


class TestPriorityThreats:
    def test_threats_are_ranked_by_severity(self):
        ranked = threats.priority_threats(PHYS_HEAVY, "Hecarim")
        severities = [t["severity"] for t in ranked]
        assert severities == sorted(severities, reverse=True)

    def test_each_threat_names_itemizable_and_non_item_responses(self):
        for t in threats.priority_threats(PHYS_HEAVY, "Hecarim"):
            assert "itemizableResponses" in t
            assert "nonItemResponses" in t
            assert t["threats"]

    def test_a_healing_enemy_produces_a_grievous_wounds_response(self):
        ranked = threats.priority_threats(["Soraka", "Ashe", "Malphite", "Leona", "Ahri"], "Hecarim")
        soraka = next(t for t in ranked if t["champion"] == "Soraka")
        assert "grievous_wounds" in soraka["itemizableResponses"]

    def test_damage_contribution_is_categorical(self):
        for t in threats.priority_threats(PHYS_HEAVY, "Hecarim"):
            assert t["damageContribution"] in ("low", "medium", "high")
