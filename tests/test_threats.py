"""Structured enemy-threat derivation for the counter builder.

The point of this layer is that a tank and a carry do not contribute equally to
damage threat, and that threats are prioritised rather than counted. These tests
pin that behaviour on real champions.
"""
from __future__ import annotations

from web.advisor import threats

# A comp with two physical carries, two tanks, one mage.
#
# Zed rather than Master Yi since 2026-08-27: the owner reclassified Yi as a
# bruiser, which is right for how he builds but drops his damage weight and
# makes him count as a durable target, so he no longer isolates what these
# tests are about. The intent is unchanged -- tanks must not out-weigh carries.
PHYS_HEAVY = ["Ashe", "Zed", "Malphite", "Leona", "Ahri"]


class TestTeamThreatProfile:
    def test_all_fields_are_categorical(self):
        levels = set(threats._LEVELS)
        profile = threats.team_threat_profile(PHYS_HEAVY)
        for key, value in profile.items():
            if key in ("durableTargetCount", "hardCcCount", "hardCcDepth"):
                assert isinstance(value, int)
            elif key == "resistanceNeeded":
                # Not a level: which resistance this comp's damage calls for.
                assert value in ("armor", "magic_resist", "both", "none")
            elif key == "damageSplitPct":
                # The raw split, because a categorical level cannot tell you
                # whether to buy armour or magic resistance.
                assert set(value) == {"physical", "magic"}
                assert 99 <= sum(value.values()) <= 101 or sum(value.values()) == 0
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


class TestOwnerClassCorrections:
    """The scraped class and role are wrong often enough to matter, and the
    corrections live in data/champion_meta_overrides.json. Pinned here so a
    re-scrape cannot quietly put "Warwick, Assassin" back."""

    def test_the_reclassified_bruisers_are_bruisers(self):
        for name in ("Garen", "Viego", "Master Yi", "Pantheon", "Warwick"):
            assert threats._champ(name)["class"] == "Bruiser", name

    def test_misread_damage_types_are_physical(self):
        """A magic Jayce made a physical poke comp measure as a magic one."""
        for name in ("Jayce", "Ezreal"):
            assert threats._champ(name).get("primaryDamage") == "physical", name

    def test_flex_picks_carry_every_role_they_are_played_in(self):
        """Olaf was Baron-only, so a jungle main was never shown the best
        answer in the game to a crowd-control composition."""
        assert "Jungle" in (threats._champ("Olaf").get("roles") or [])
        assert "Baron" in (threats._champ("Olaf").get("roles") or [])


class TestResistanceAndTenacityGates:
    """The two signals that decide a defensive purchase, both added after a
    test run bought the wrong resistance and a tenacity rune nobody needed."""

    def test_a_magic_comp_asks_for_magic_resist(self):
        """Four of these five deal magic damage from ABILITIES, not attacks.
        Resistances used to be requested only from basic-attack carries, so
        this comp asked for none and the build took 165 armour and no magic
        resistance."""
        profile = threats.team_threat_profile(
            ["Malphite", "Amumu", "Lissandra", "Leona", "Syndra"])
        assert profile["resistanceNeeded"] in ("magic_resist", "both")
        assert profile["damageSplitPct"]["magic"] > profile["damageSplitPct"]["physical"]

    def test_a_physical_comp_asks_for_armor(self):
        profile = threats.team_threat_profile(
            ["Darius", "Master Yi", "Zed", "Samira", "Pyke"])
        assert profile["resistanceNeeded"] == "armor"

    def test_crowd_control_counts_only_what_the_enemy_does_to_you(self):
        """Kai'Sa's passive reads "nearby ALLIES apply 1 stack to champions
        they Immobilize" and she was counted as a crowd-control threat, which
        pushed a comp over the tenacity threshold."""
        assert not threats._has(threats._champ("Kai'Sa"), "cc")
        assert threats._has(threats._champ("Pyke"), "cc")       # his E stuns
        assert not threats._has(threats._champ("Master Yi"), "cc")
