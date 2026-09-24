"""Engine-judged maximum-damage candidate tournament."""
import json
from pathlib import Path

import pytest

from web import build_advisor as adv
from web import fight_engine as fe


def candidate(label="A", last="guardian-angel"):
    return {
        "id": label,
        "hypothesis": "damage with a defensive final slot",
        "items": ["blade-of-the-ruined-king", "guinsoos-rageblade",
                  "kraken-slayer", "terminus", last],
        "boots": "berserkers-greaves",
        "runes": {
            "keystone": "Lethal Tempo", "primaryTree": "Precision",
            "minors": ["Brutal", "Cut Down", "Legend: Alacrity"],
            "flex": "Bone Plating",
        },
        "summoners": ["Flash", "Barrier"],
    }


def test_candidate_gate_requires_three_distinct_legal_cores():
    a = candidate("A", "guardian-angel")
    b = candidate("B", "wits-end")
    c = candidate("C", "bloodthirster")
    allowed = sorted({item for build in (a, b, c) for item in build["items"]})

    accepted, errors = adv._legal_tournament_candidates(
        {"candidates": [a, b, c]}, allowed)

    assert [row["id"] for row in accepted] == ["A", "B", "C"]
    assert errors == []


def test_jungle_candidates_get_smite_instead_of_being_rejected():
    # Graves max damage never reached the engine: every candidate paired Flash
    # with Ignite, the gate rejected all three for needing Smite, and the
    # request silently fell back to one ordinary generation.
    a = candidate("A", "guardian-angel")
    b = candidate("B", "wits-end")
    c = candidate("C", "bloodthirster")
    for build in (a, b, c):
        build["summoners"] = ["Flash", "Ignite"]
    allowed = sorted({item for build in (a, b, c) for item in build["items"]})

    accepted, errors = adv._legal_tournament_candidates(
        {"candidates": [a, b, c]}, allowed, role="jungle")

    assert errors == []
    assert [row["id"] for row in accepted] == ["A", "B", "C"]
    assert all(sorted(row["summoners"]) == ["Flash", "Smite"] for row in accepted)
    # The measured core is the repaired one, so the post-judge enforcement of
    # the same rule cannot knock it out of the tested set.
    assert a["summoners"] == ["Flash", "Ignite"]


def test_candidates_equal_after_summoner_repair_are_duplicates():
    a = candidate("A")
    b = candidate("B")
    a["summoners"] = ["Flash", "Ignite"]
    b["summoners"] = ["Flash", "Exhaust"]
    allowed = sorted(set(a["items"]))

    accepted, errors = adv._legal_tournament_candidates(
        {"candidates": [a, b]}, allowed, role="jungle", expected_count=2)

    assert [row["id"] for row in accepted] == ["A"]
    assert any("duplicates" in e for e in errors)


def test_core_repaired_after_the_judge_degrades_instead_of_raising():
    # Max-durability Caitlyn used to 500 here.
    judged = candidate("A")
    meta = {"winner": "A", "measurements": [{"id": "A"}]}
    tested = {adv._candidate_signature(judged)}

    assert adv._settle_tournament_label(dict(judged), meta, tested) is meta

    repaired = {**judged, "items": judged["items"][:4] + ["bloodthirster"]}
    settled = adv._settle_tournament_label(repaired, meta, tested)
    assert settled["winner"] is None
    assert settled["judgedWinner"] == "A"
    assert settled["coreRepairedAfterJudge"] is True
    assert settled["measurements"] == meta["measurements"]
    assert adv._settle_tournament_label(repaired, None, tested) is None


def test_flexible_champions_get_distinct_cross_path_archetypes():
    varus = adv.profiles.profile("Varus", log=False)
    paths = adv._damage_archetypes(
        "Varus", varus["combatProfile"], varus["scalingProfile"], "standard")
    ids = {row["id"] for row in paths}

    assert "ap-caster" in ids
    assert ids & {"ad-crit", "ad-on-hit"}
    assert adv._tournament_candidate_count(paths) >= len(paths)


def test_candidate_gate_requires_every_declared_damage_archetype():
    builds = [candidate("A", "guardian-angel"),
              candidate("B", "wits-end"), candidate("C", "bloodthirster")]
    for build in builds:
        build["archetype"] = "ad-on-hit"
    allowed = sorted({item for build in builds for item in build["items"]})

    accepted, errors = adv._legal_tournament_candidates(
        {"candidates": builds}, allowed, expected_count=3,
        required_archetypes=["ad-on-hit", "ap-caster"])

    assert len(accepted) == 3
    assert any("ap-caster" in error for error in errors)


def test_generation_prompt_requests_all_paths_in_one_completion():
    paths = [{"id": "ad-crit", "description": "crit autos"},
             {"id": "ad-on-hit", "description": "on-hit autos"},
             {"id": "ap-caster", "description": "AP burst"},
             {"id": "ap-on-hit", "description": "AP on-hit"}]
    prompt = adv._tournament_generation_prompt("base", paths, 4)

    assert "exactly 4" in prompt
    assert all(path["id"] in prompt for path in paths)
    assert '"archetype"' in prompt


def test_candidate_gate_rejects_unknown_items_and_duplicate_builds():
    a = candidate("A", "guardian-angel")
    duplicate = candidate("B", "guardian-angel")
    invented = candidate("C", "item-that-does-not-exist")
    allowed = list(a["items"])

    accepted, errors = adv._legal_tournament_candidates(
        {"candidates": [a, duplicate, invented]}, allowed)

    assert accepted == [a]
    assert any("duplicates" in error for error in errors)
    assert any("outside the supplied pool" in error for error in errors)


def test_simulation_returns_comparable_damage_and_survival_dimensions():
    measured = adv._simulate_tournament("Jinx", [candidate()])

    engine = measured[0]["engine"]
    assert engine["dps"]["10"] > 0
    assert engine["ttk"]["adc"] is not None
    assert engine["damageBeforeDeath"] > 0
    assert engine["ehp"] > 0
    assert set(engine["damageScenarios"]["targets"]) == {
        "adc", "mage", "fighter", "bruiser", "tank"
    }


def test_patch_73_nashors_does_not_keep_removed_adaptive_stats():
    stats = fe.resolve_stats("Jinx", 15, ["nashors-tooth"], [])

    assert stats["ap"] == 80
    assert stats["bonusAd"] == 0


def test_cross_stat_health_ratios_survive_for_hybrid_damage_paths():
    varus = next(c for c in fe.FORMULAS["Varus"]["abilities"]["2"]["damage"]
                 if c["name"] == "Blight detonation (max stacks)")
    kaisa = next(c for c in fe.FORMULAS["Kai'Sa"]["abilities"]["P"]["damage"]
                 if c["name"] == "Plasma Detonation")
    kayle = next(c for c in fe.FORMULAS["Kayle"]["abilities"]["3"]["damage"]
                 if c["name"] == "Starfire Spellblade Active")

    assert varus["crossRatios"] == [{
        "target": "targetMaxHp", "stat": "ap", "pctPerStat": 0.012}]
    assert kaisa["crossRatios"][0]["target"] == "targetMissingHp"
    assert kayle["crossRatios"][0]["pctPerStat"] == 0.02


def test_jax_empower_is_real_damage_not_a_dropped_alternative():
    empower = fe.FORMULAS["Jax"]["abilities"]["2"]["damage"][0]
    assert empower["name"] == "Empower"
    assert not empower.get("alt")


def test_miss_fortune_love_tap_uses_every_third_hit_and_current_crit():
    passive = fe.FORMULAS["Miss Fortune"]["abilities"]["P"]["damage"][0]
    assert fe.every_n_share("Miss Fortune")[0] == pytest.approx(1 / 3)
    assert passive["critScale"] == {"base": 0.6, "perCrit": 0.4}


def test_unresolved_champion_mechanics_are_disclosed_to_the_judge():
    coverage = fe.champion_mechanics_coverage("Varus")
    assert coverage["status"] == "partial"
    assert coverage["engineAuthoritative"] is False
    assert coverage["buildRelevantGapCount"] > 0
    assert "Do not use an engine score" in coverage["policy"]


def test_statikk_chain_lightning_reaches_the_aoe_axis():
    vector = fe.evaluation_vector("Jinx", ["statikk-shiv"], [], level=15)

    assert vector["aoeDamage"] > 0


def test_hexoptics_keeps_crit_in_every_band_and_scales_only_attack_damage():
    target = fe.target_profiles(15)["adc"]
    rows = {}
    for band in fe.CONDITION_BANDS:
        stats = fe.resolve_stats(
            "Caitlyn", 15, ["hexoptics-c44"], [], condition_band=band)
        result = fe.rotation("Caitlyn", stats, target, 8, level=15)
        rows[band] = (stats, result)

    assert {round(row[0]["crit"] * 100) for row in rows.values()} == {25}
    assert rows["floor"][0]["attackDamageAmp"] == 0
    assert rows["expected"][0]["attackDamageAmp"] == pytest.approx(0.05)
    assert rows["ceiling"][0]["attackDamageAmp"] == pytest.approx(0.10)
    assert rows["floor"][1]["autoDmg"] < rows["expected"][1]["autoDmg"]
    assert rows["expected"][1]["autoDmg"] < rows["ceiling"][1]["autoDmg"]


def test_conditional_panels_publish_skill_weights_and_all_three_bands():
    developing = fe.conditional_damage_scenarios(
        "Jinx", ["hexoptics-c44"], [], skill_level="developing")
    high = fe.conditional_damage_scenarios(
        "Jinx", ["hexoptics-c44"], [], skill_level="high")

    assert set(developing["bands"]) == {"floor", "expected", "ceiling"}
    assert developing["weights"]["floor"] > high["weights"]["floor"]
    assert high["weights"]["ceiling"] > developing["weights"]["ceiling"]
    assert (developing["bands"]["floor"]["targets"]["adc"]["damage8"]
            < developing["bands"]["ceiling"]["targets"]["adc"]["damage8"])


def test_tournament_measurements_carry_the_requested_skill_profile():
    build = candidate()
    build["items"][0] = "hexoptics-c44"

    measured = adv._simulate_tournament(
        "Jinx", [build], skill_level="developing")
    conditional = measured[0]["engine"]["conditionalDamage"]

    assert conditional["skillLevel"] == "developing"
    assert conditional["hasConditionalEffects"] is True
    assert conditional["weights"] == fe.CONDITION_SKILL_WEIGHTS["developing"]


def test_provable_build_has_one_panel_and_is_not_skill_discounted():
    panel = fe.conditional_damage_scenarios(
        "Jinx", ["blade-of-the-ruined-king"], [], skill_level="developing")

    assert panel["hasConditionalEffects"] is False
    assert set(panel["bands"]) == {"expected"}


def test_dark_harvest_threshold_is_checked_but_soul_count_uses_bands():
    target = fe.target_profiles(15)["adc"]
    damage = {}
    souls = {}
    for band in fe.CONDITION_BANDS:
        stats = fe.resolve_stats(
            "Jinx", 15, [], ["Dark Harvest"], condition_band=band)
        effect = next(e for e in stats["conditionalEffects"]
                      if e["source"] == "Dark Harvest")
        souls[band] = effect["value"]
        damage[band] = fe.rotation("Jinx", stats, target, 8, level=15)["total"]

    assert souls == {"floor": 0, "expected": 8, "ceiling": 16}
    assert damage["floor"] < damage["expected"] < damage["ceiling"]


def test_sudden_impact_requires_an_intrinsic_kit_trigger_not_flash():
    assert fe.can_trigger_sudden_impact("Varus") is False
    assert fe.can_trigger_sudden_impact("Jinx") is False
    assert fe.can_trigger_sudden_impact("Graves") is True
    assert fe.can_trigger_sudden_impact("Twitch") is True

    varus = fe.resolve_stats("Varus", 15, [], ["Sudden Impact"])
    graves = fe.resolve_stats("Graves", 15, [], ["Sudden Impact"])
    assert not any(p["label"] == "Sudden Impact" for p in varus["procs"])
    assert any(p["label"] == "Sudden Impact" for p in graves["procs"])


def test_first_strike_is_full_for_three_seconds_not_the_whole_long_fight():
    target = fe.target_profiles(15)["bruiser"]
    base = fe.resolve_stats("Jinx", 15, [], [])
    first = fe.resolve_stats("Jinx", 15, [], ["First Strike"])
    base3 = fe.rotation("Jinx", base, target, 3, level=15)["total"]
    first3 = fe.rotation("Jinx", first, target, 3, level=15)["total"]
    base8 = fe.rotation("Jinx", base, target, 8, level=15)["total"]
    first8 = fe.rotation("Jinx", first, target, 8, level=15)["total"]

    assert first3 / base3 == pytest.approx(1.07)
    assert first8 / base8 == pytest.approx(1 + 0.07 * 3 / 8)


def test_coup_de_grace_only_amplifies_damage_after_target_crosses_40_percent():
    target = fe.target_profiles(15)["adc"]
    base = fe.resolve_stats("Jinx", 15, [], [])
    coup = fe.resolve_stats("Jinx", 15, [], ["Coup de Grace"])

    assert (fe.rotation("Jinx", coup, target, 0.5, level=15)["total"]
            == fe.rotation("Jinx", base, target, 0.5, level=15)["total"])
    assert (fe.rotation("Jinx", coup, target, 8, level=15)["total"]
            > fe.rotation("Jinx", base, target, 8, level=15)["total"])


def test_one_vs_three_caps_item_aoe_to_two_real_secondary_targets():
    panel = fe.damage_scenarios(
        "Jinx", ["statikk-shiv", "runaans-hurricane"], [], level=15)
    one_three = panel["oneVsThree"]

    assert one_three["secondaryTargets"] == ["adc", "mage"]
    assert one_three["secondaryItemAoeDamage"] > 0
    assert one_three["totalDamage"] == (
        one_three["primaryDamage"] + one_three["secondaryItemAoeDamage"]
        + one_three["secondaryChampionAoeDamage"])
    assert "champion-ability AoE" in one_three["scope"]


def test_graves_one_vs_three_allocates_q_w_and_ult_cone_to_secondaries():
    items = ["essence-reaver", "youmuus-ghostblade", "the-collector",
             "infinity-edge", "lord-dominiks-regard", "boots-of-dynamism"]
    runes = ["First Strike", "Sudden Impact", "Tyrant",
             "Eyeball Collector", "Coup de Grace"]
    panel = fe.damage_scenarios("Graves", items, runes, level=15)

    assert panel["oneVsThree"]["secondaryChampionAoeDamage"] > 0
    assert panel["oneVsThree"]["secondaryItemAoeDamage"] == 0
    assert fe.ability_aoe_rule("Graves", "4", "Shell Impact")[
        "maxSecondaryTargets"] == 0
    assert fe.ability_aoe_rule("Graves", "4", "Cone Explosion")[
        "primaryPct"] == 0
    assert fe.ability_aoe_rule("Graves", "1", "Initial Round")[
        "secondaryPct"] == 100
    assert fe.ability_aoe_rule("Graves", "1", "Detonation")[
        "secondaryPct"] == 100
    assert fe.ability_aoe_rule("Graves", "2", "Initial Impact")[
        "secondaryPct"] == 100


def test_browser_engine_exports_graves_component_targeting_rules():
    root = Path(__file__).resolve().parents[1]
    bundle = json.loads(
        (root / "web-next" / "src" / "data" / "engine.json")
        .read_text(encoding="utf-8")
    )
    graves = bundle["abilityAoe"]["Graves"]

    assert graves["1"]["Initial Round"]["maxSecondaryTargets"] == 2
    assert graves["4"]["Shell Impact"]["maxSecondaryTargets"] == 0
    assert graves["4"]["Cone Explosion"]["primaryPct"] == 0
    assert bundle["itemFx"]["hexoptics-c44"]["conditionalAttackAmpPct"] == {
        "floor": 0, "expected": 5, "ceiling": 10,
    }
    assert bundle["runeFx"]["keystones"]["Dark Harvest"]["burstProc"][
        "assumedSoulsByBand"] == {"floor": 0, "expected": 8, "ceiling": 16}
    assert bundle["champions"]["Varus"]["suddenImpactTrigger"] is False
    assert bundle["champions"]["Graves"]["suddenImpactTrigger"] is True


def test_untagged_single_target_ability_is_not_copied_to_secondaries():
    stats = fe.resolve_stats("Vayne", 15, [], [])
    result = fe.rotation("Vayne", stats, fe.target_profiles(15)["adc"], 8,
                         level=15, secondary_targets=1)

    assert result["abilityAoeDmg"] == 0


def test_goredrinker_active_uses_total_ad_damage_channel():
    stats = fe.resolve_stats("Aatrox", 15, ["goredrinker"], [])
    proc = next(p for p in stats["procs"] if p["label"] == "goredrinker")

    assert proc["totalAdRatio"] == 1.75
    assert proc["type"] == "physical"


def test_long_cooldown_item_and_rune_procs_do_not_repeat_in_teamfight_window():
    goredrinker = fe.resolve_stats("Aatrox", 15, ["goredrinker"], [])
    gore_proc = next(p for p in goredrinker["procs"]
                     if p["label"] == "goredrinker")
    sudden = fe.resolve_stats("Graves", 15, [], ["Sudden Impact"])
    sudden_proc = next(p for p in sudden["procs"]
                       if p["label"] == "Sudden Impact")

    assert gore_proc["cd"] == 12
    assert sudden_proc["cd"] == 10
    assert fe._proc_activations(8, gore_proc["cd"], gore_proc["arm"]) == 1
    assert fe._proc_activations(8, sudden_proc["cd"], sudden_proc["arm"]) == 1
    assert fe._proc_activations(19.9, sudden_proc["cd"], sudden_proc["arm"]) == 2


def test_bork_drain_is_one_scheduled_slow_and_not_a_damage_proc():
    stats = fe.resolve_stats("Jinx", 15, ["blade-of-the-ruined-king"], [])

    assert not any(p["label"] == "blade-of-the-ruined-king"
                   for p in stats["procs"])
    assert stats["targetSlowEffects"] == [{
        "pct": 0.3, "durationS": 1.5, "cooldownS": 30,
        "armHits": 3,
    }]
    eight_second = fe._for_window("Jinx", stats, 8)
    assert eight_second["targetSlow"] == pytest.approx(0.3 * 1.5 / 8)


def test_max_damage_routes_to_one_tournament_generation(monkeypatch):
    calls = []

    def fake(champion, role, enemies, **kwargs):
        calls.append((champion, role, enemies, kwargs))
        return {"items": []}

    monkeypatch.setattr(adv, "advise", fake)

    adv.advise_best_of("Jinx", "dragon", [], runs=3, build_bias="max_damage")

    assert len(calls) == 1
    assert calls[0][3]["engine_tournament"] is True


def test_engine_can_add_a_stronger_recombination_from_model_nominations():
    a = candidate("A", "immortal-shieldbow")
    a["items"] = ["stormrazor", "runaans-hurricane", "infinity-edge",
                  "lord-dominiks-regard", "immortal-shieldbow"]
    a["runes"]["minors"] = ["Brutal", "Cut Down", "Legend: Bloodline"]
    a["runes"]["flex"] = "Eyeball Collector"
    a["summoners"] = ["Flash", "Ghost"]
    b = candidate("B", "bloodthirster")
    b["items"] = ["the-collector", "phantom-dancer", "infinity-edge",
                  "mortal-reminder", "bloodthirster"]
    b["runes"] = {"keystone": "Lethal Tempo", "primaryTree": "Domination",
                  "minors": ["Empowered Attack", "Tyrant", "Eyeball Collector"],
                  "flex": "Brutal"}
    b["summoners"] = ["Flash", "Ghost"]
    c = candidate("C", "immortal-shieldbow")
    c["items"] = ["hexoptics-c44", "rapid-firecannon", "infinity-edge",
                  "lord-dominiks-regard", "immortal-shieldbow"]
    c["boots"] = "gluttonous-greaves"
    c["runes"] = {"keystone": "Fleet Footwork", "primaryTree": "Precision",
                  "minors": ["Brutal", "Coup de Grace", "Legend: Bloodline"],
                  "flex": "Bone Plating"}

    challenger, meta = adv._engine_challenger("Jinx", [a, b, c], role="Dragon")

    assert meta["searched"] > 0
    assert meta["scenarioEvaluations"] > 0
    assert meta["objective"] == "multi_profile_damage"
    assert set(meta["weights"]) == {
        "fiveTargetDps", "fiveTargetBurst", "oneVsThreeDamage"
    }
    assert challenger is not None
    assert set(challenger["items"]) <= set(a["items"] + b["items"] + c["items"])
    assert set(adv._candidate_rune_names(challenger)) <= set(
        adv._candidate_rune_names(a) + adv._candidate_rune_names(b)
        + adv._candidate_rune_names(c))
    assert meta["challengerScore"] > meta["authoredBestScore"]


def test_judge_prompt_discloses_trigger_and_no_splicing_limits():
    prompt = adv._tournament_judge_prompt("base prompt", [{"id": "A"}])

    assert "Do not splice a" in prompt and "new untested build" in prompt
    assert "ENGINE-D" in prompt
    assert "Sudden Impact" in prompt
    assert "Guardian Angel revive" in prompt
    assert "a 30-second proc cannot repeat" in prompt
    assert "ADC, mage, fighter, bruiser and tank" in prompt
    assert "NOT literal 1v3 win probability" in prompt
    # The area shapes stopped being Graves-only, so the judge is told both that
    # ability AoE is credited across the roster AND what is still excluded from
    # it -- otherwise it reads a rider's single-target number as a kit failure.
    assert "derived across the roster" in prompt
    assert "empowered basic attacks" in prompt


# ---------------------------------------------------------------------------
# THE OBJECTIVE, BEYOND DAMAGE
#
# The tournament shipped measuring damage only, so a durability request was
# handed to a damage optimizer and the engine challenger could only ever return
# the bloodiest build it found. These hold the blend that fixes that, and the
# one property that must not move: maximum damage is numerically unchanged.
# ---------------------------------------------------------------------------


def _candidate(cid, items, boots, keystone, minors, flex, archetype):
    return {"id": cid, "archetype": archetype, "items": items, "boots": boots,
            "runes": {"keystone": keystone, "minors": minors, "flex": flex},
            "summoners": ["Flash", "Ghost"]}


JINX_CANDIDATES = [
    _candidate("A", ["stormrazor", "runaans-hurricane", "infinity-edge",
                     "lord-dominiks-regards", "immortal-shieldbow"],
               "berserkers-greaves", "Lethal Tempo",
               ["Brutal", "Cut Down", "Legend: Bloodline"], "Eyeball Collector",
               "ad-crit"),
    _candidate("B", ["the-collector", "phantom-dancer", "infinity-edge",
                     "mortal-reminder", "bloodthirster"],
               "berserkers-greaves", "Lethal Tempo",
               ["Brutal", "Coup de Grace", "Legend: Alacrity"], "Eyeball Collector",
               "ad-crit"),
]


def test_every_bias_on_the_axis_routes_to_the_tournament():
    assert adv.TOURNAMENT_BIASES == frozenset(adv.BUILD_BIAS)


def test_maximum_damage_still_scores_pure_damage():
    """The shipped path must be numerically untouched by the blend."""
    damage_w, survival_w = adv._tournament_blend("max_damage")

    assert (damage_w, survival_w) == (1.0, 0.0)


def test_the_blend_moves_monotonically_from_damage_to_survival():
    order = ["max_damage", "damage", "balanced", "durability", "max_durability"]
    survival = [adv._tournament_blend(b)[1] for b in order]

    assert survival == sorted(survival)
    assert all(abs(sum(adv._tournament_blend(b)) - 1.0) < 1e-9 for b in order)


def test_an_unknown_bias_falls_back_to_damage_rather_than_guessing():
    assert adv._tournament_blend("nonsense") == (1.0, 0.0)


def test_the_prefilter_is_blended_too_or_durable_items_never_get_searched():
    """A damage-ranked shortlist cannot produce a durability challenger."""
    pure = adv._tournament_prefilter_weights("sustained_damage", 1.0, 0.0)
    blended = adv._tournament_prefilter_weights("sustained_damage", 0.2, 0.8)

    assert pure == "sustained_damage"
    assert isinstance(blended, dict)
    assert blended["timeToDie"] > blended.get("sustainedDps", 0)
    assert blended["compEhp"] > 0


def test_damage_before_death_is_weighted_as_survival_not_damage():
    """Pure timeToDie would reward a marksman for contributing nothing."""
    assert "damageBeforeDeath" in adv.TOURNAMENT_SURVIVAL_WEIGHTS
    assert adv.TOURNAMENT_SURVIVAL_WEIGHTS["damageBeforeDeath"] > 0.2


def test_the_judge_is_told_which_objective_produced_the_ranking():
    damage = adv._tournament_judge_prompt("base", [{"id": "A"}], "max_damage")
    durable = adv._tournament_judge_prompt("base", [{"id": "A"}], "max_durability")

    assert "max damage" in damage and "100% on damage" in damage
    assert "Survivability carries no weight here" in damage
    assert "max durability" in durable and "80% on surviving" in durable
    assert "durability is worth nothing" in durable


def test_durability_and_damage_biases_pick_different_builds():
    """End-to-end proof that the blend reaches the answer, not just the score.

    The pool is bounded to keep this a test rather than a 30-second search: it
    holds a crit core, an on-hit core and real defensive options, which is
    enough for the two objectives to disagree if the blend works at all.
    """
    pool = [
        "infinity-edge", "the-collector", "stormrazor", "runaans-hurricane",
        "lord-dominiks-regards", "mortal-reminder", "bloodthirster",
        "phantom-dancer", "blade-of-the-ruined-king", "immortal-shieldbow",
        "guardian-angel", "maw-of-malmortius", "death's-dance", "sterak's-gage",
        "black-cleaver", "trinity-force",
    ]
    pool = [slug for slug in pool if slug in adv.ITEMS]
    picks = {}
    for bias in ("max_damage", "max_durability"):
        challenger, meta = adv._engine_challenger(
            "Jinx", JINX_CANDIDATES, role="adc", enemies_known=False,
            skill_level="average", build_bias=bias, allowed_items=pool)
        assert challenger, f"{bias} found no challenger"
        assert meta["blend"] == {"damage": adv._tournament_blend(bias)[0],
                                 "survival": adv._tournament_blend(bias)[1]}
        picks[bias] = set(challenger["items"])

    assert picks["max_damage"] != picks["max_durability"]


# ---------------------------------------------------------------------------
# THE ARCHETYPE GATE
#
# Validated against a known-wrong answer rather than ladder data: Dusk and Dawn
# must not appear in Jinx's maximum-damage build. It did, because
# `_item_supports_archetype` OR'd attack speed into the AD paths, so a pure AP
# item with zero AD and zero crit was eligible for an ad-crit search.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("slug", ["dusk-and-dawn", "nashors-tooth",
                                  "rabadons-deathcap"])
def test_pure_ap_items_are_not_eligible_for_ad_paths(slug):
    for path in ("ad-crit", "ad-on-hit", "ad-caster"):
        assert not adv._item_supports_archetype(slug, path), f"{slug} in {path}"
    assert adv._item_supports_archetype(slug, "ap-caster")


@pytest.mark.parametrize("slug", ["infinity-edge", "blade-of-the-ruined-king",
                                  "terminus"])
def test_physical_items_are_not_eligible_for_ap_paths(slug):
    assert not adv._item_supports_archetype(slug, "ap-caster")
    assert not adv._item_supports_archetype(slug, "ap-on-hit")


def test_attack_speed_alone_does_not_qualify_a_crit_path():
    """At Wit's End has no AD, no AP and no crit: on-hit yes, crit no."""
    assert adv._item_supports_archetype("wits-end", "ad-on-hit")
    assert not adv._item_supports_archetype("wits-end", "ad-crit")


def test_an_item_carrying_both_stats_stays_eligible_for_both():
    """Guinsoo's is what the hybrid roster actually needs."""
    for path in ("ad-on-hit", "ap-on-hit", "hybrid-on-hit"):
        assert adv._item_supports_archetype("guinsoos-rageblade", path)


def test_the_engine_cannot_put_dusk_and_dawn_in_a_jinx_damage_build():
    """The owner's oracle: this item in this build is known-wrong."""
    pool = [slug for slug, meta in adv.ITEMS.items() if not meta.get("removedIn")]
    eligible = [slug for slug in pool
                if adv._item_supports_archetype(slug, "ad-crit")]

    assert "dusk-and-dawn" not in eligible
    assert "nashors-tooth" not in eligible
    assert "infinity-edge" in eligible


def test_the_eligibility_gate_is_the_only_defence_here():
    """The combo gate does NOT catch a stat-wasting passenger, so the
    per-item filter above is load-bearing rather than belt-and-braces.

    `ad-crit` asks for two crit items and two AD items across the five. IE and
    Runaan's satisfy both counts by themselves, so Dusk and Dawn rides along
    unexamined. Anything that widens `_item_supports_archetype` puts the bug
    straight back.
    """
    assert adv._combo_matches_archetype(
        ("dusk-and-dawn", "runaans-hurricane", "infinity-edge",
         "wits-end", "terminus"), "ad-crit")
