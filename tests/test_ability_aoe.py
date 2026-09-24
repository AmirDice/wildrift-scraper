"""The multi-target axis must stay derived for the whole roster.

Before this, only Graves had curated component targeting, so every other
champion's abilities contributed nothing to the 1v3 and that axis quietly
measured "did this build buy Runaan's".  These tests exist to stop it
collapsing back to one champion, and to hold the two rules that keep the
derivation honest: an attack rider is not area damage, and hand curation wins.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import web.fight_engine as fe
from scripts import derive_ability_aoe as derive

ROOT = Path(__file__).resolve().parents[1]


def _aoe() -> dict:
    return json.loads((ROOT / "data" / "ability_aoe.json").read_text(
        encoding="utf-8"))["champions"]


def test_the_committed_file_matches_the_derivation():
    """A stale file is the failure mode that hides every other one."""
    doc, _ = derive.build()
    rendered = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    current = (ROOT / "data" / "ability_aoe.json").read_text(encoding="utf-8")

    assert current == rendered, (
        "data/ability_aoe.json is stale; run python -m scripts.derive_ability_aoe")


def test_coverage_is_the_roster_and_not_one_curated_champion():
    aoe = _aoe()

    assert len(aoe) > 100, f"only {len(aoe)} champions carry area rules"
    assert sum(len(slots) for slots in aoe.values()) > 200


def test_hand_curation_beats_the_derivation():
    """Graves' cone opens behind the first champion, so it cannot hit them."""
    ult = _aoe()["Graves"]["4"]

    assert ult["Shell Impact"]["secondaryPct"] == 0
    assert ult["Cone Explosion"]["primaryPct"] == 0
    assert ult["Cone Explosion"]["maxSecondaryTargets"] == 2


def test_passive_slots_are_never_derived():
    """Graves' shotgun fires four pellets into one body, not three bodies."""
    aoe = _aoe()
    derived_passives = [c for c, slots in aoe.items() if "P" in slots]

    assert derived_passives == [], derived_passives


@pytest.mark.parametrize("champion,slot,component", [
    ("Jax", "4", "Grandmaster-at-Arms Passive"),
    ("Blitzcrank", "4", "Static Field Passive"),
    ("Thresh", "3", "Flay Passive"),
])
def test_attack_riders_stay_on_the_primary_target(champion, slot, component):
    """Every-third-hit damage lands on the body being attacked."""
    rule = fe.ability_aoe_rule(champion, slot, component)

    assert rule["secondaryPct"] == 0
    assert rule["maxSecondaryTargets"] == 0


def test_gragas_empowered_attack_is_the_curated_exception():
    rule = fe.ability_aoe_rule("Gragas", "2", "Drunken Rage Empowered Attack")

    assert rule["secondaryPct"] == 100


def test_falloff_in_a_separate_sentence_is_still_applied():
    """Caitlyn's Q states 'piercing' and its 40% falloff in different sentences."""
    rule = fe.ability_aoe_rule("Caitlyn", "1", "Piltover Peacemaker")

    assert rule["secondaryPct"] == 60


def test_a_bounce_reaches_one_extra_body_not_the_whole_fight():
    rule = fe.ability_aoe_rule("Jhin", "1", "Dancing Grenade")

    assert rule["maxSecondaryTargets"] == 1


def test_minion_only_spread_is_not_champion_area_damage():
    """Jhin's W stops on the first champion; only minions take the rest."""
    rule = fe.ability_aoe_rule("Jhin", "2", "Deadly Flourish")

    assert rule["maxSecondaryTargets"] == 0


@pytest.mark.parametrize("champion", ["Jinx", "Darius", "Lux", "Samira", "Malphite"])
def test_kits_with_area_damage_reach_the_aoe_axis(champion):
    stats = fe.resolve_stats(champion, 15, [], [])
    result = fe.rotation(champion, stats, fe.target_profiles(15)["adc"], 8,
                         level=15, secondary_targets=2)

    assert result["abilityAoeDmg"] > 0


def test_a_genuinely_single_target_kit_still_scores_zero():
    """Vayne's whole kit is one body at a time; the axis must not reward her."""
    stats = fe.resolve_stats("Vayne", 15, [], [])
    result = fe.rotation("Vayne", stats, fe.target_profiles(15)["adc"], 8,
                         level=15, secondary_targets=2)

    assert result["abilityAoeDmg"] == 0
