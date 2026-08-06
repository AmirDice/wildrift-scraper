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


class TestPartialCompScaling:
    """The level thresholds are tuned for five enemies; a partial comp must not
    be graded against a denominator it cannot reach.

    The reported case: Lee Sin, Riven, Karma -- every named enemy shields, the
    most shield-saturated answer three picks can give -- and the team profile
    said "medium", because three enemies accumulate at most 1.5 against a
    "high" bar of 1.8 that assumes five contributors.
    """

    def test_a_comp_where_every_enemy_shields_reads_high(self):
        profile = threats.team_threat_profile(["Karma", "Riven", "Lee Sin"])
        assert profile["shielding"] in ("high", "very_high")

    def test_a_full_team_is_unchanged_by_the_scaling(self):
        # factor is 5/5=1, so the original expectations still hold
        profile = threats.team_threat_profile(PHYS_HEAVY)
        order = threats._LEVELS
        assert order.index(profile["physicalDamage"]) > order.index(profile["magicDamage"])

    def test_one_named_enemy_describes_that_enemy_not_a_guess_at_five(self):
        """Naming only Karma means everything known about the comp IS Karma;
        her shielding should read strong rather than being diluted by four
        empty slots."""
        profile = threats.team_threat_profile(["Karma"])
        assert profile["shielding"] in ("high", "very_high")


class TestWinrateDrivenSeverity:
    """Severity runs on the MEASURED meta win rate, not a tier bucket.

    The tier buckets collapsed real differences: a 56.5% Nidalee and a 52%
    champion could share a bucket and read as equal threats. The measured
    number was already loaded onto every enemy record (_wr) and then never
    used.
    """

    def test_a_meta_tyrant_outranks_weak_picks_of_scarier_classes(self):
        # Nidalee (56.5%) vs a comp of ~49% picks: she must rank first even
        # though Lux and Corki contribute damage from "louder" classes.
        ranked = threats.priority_threats(
            ["Corki", "Lulu", "Lux", "Mordekaiser", "Nidalee"], "Graves")
        assert ranked[0]["champion"] == "Nidalee"

    def test_the_measured_winrate_is_shown_to_the_model(self):
        ranked = threats.priority_threats(["Nidalee"], "Graves")
        assert isinstance(ranked[0].get("metaWinrate"), (int, float))

    def test_missing_winrate_falls_back_to_the_tier_bucket(self):
        assert threats._wr_severity(None, "GOD") == 0.9
        assert threats._wr_severity(None, "") == 0.4

    def test_the_mapping_spans_the_old_bucket_range(self):
        # 46% reads like the old D bucket, 60% past the old GOD bucket, and
        # the clamps hold at the extremes.
        assert threats._wr_severity(46.0, "") == 0.2
        assert threats._wr_severity(60.0, "") == 0.9
        assert threats._wr_severity(30.0, "") == 0.2
        assert threats._wr_severity(99.0, "") == 0.95
