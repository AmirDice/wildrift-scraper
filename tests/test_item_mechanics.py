"""Regression coverage for item passive mechanics shared by both engines."""

from web import fight_engine as fe


def test_requested_item_channels_resolve():
    slugs = [
        "bloodthirster", "essence-reaver", "goredrinker", "ludens-echo",
        "sunfire-aegis", "fimbulwinter", "mantle-of-the-twelfth-hour",
        "rapid-firecannon", "statikk-shiv", "fiendhunter-bolts",
    ]
    st = fe.resolve_stats("Jinx", 15, slugs, [])

    assert st["overhealShieldCap"] > 0
    assert st["spellbladeBaseAdPct"] == 135
    assert st["spellbladeCritFlatPerCrit"] == 80
    assert st["spellbladeCanCrit"] == 1
    assert st["activeHealAdPct"] == 0.20
    assert st["activeHealMissingHpPct"] == 0.10
    assert st["dotDps"] > 20  # Sunfire's 1.5% bonus-health term is live.
    assert st["shieldPctMana"] == 0.045
    assert st["triggeredHp"] > 0 and st["triggeredHeal"] > 0
    assert st["attackRangeBonus"] == 150
    assert st["attackRangeBonusPct"] == 35
    assert st["aoeProcAppliesOnHit"] == 1
    assert st["burstAoeProcs"]
    assert st["ultAttackCount"] == 3
    assert st["ultAttackAsPct"] == 50


def test_ludens_and_shiv_have_separate_multi_target_channels():
    ludens = fe.resolve_stats("Ahri", 15, ["ludens-echo"], [])
    duel = fe.rotation("Ahri", ludens, fe.TARGETS["bruiser"], 8.0)
    tri = fe.rotation("Ahri", ludens, fe.TARGETS["bruiser"], 8.0,
                      secondary_targets=2)
    assert tri["boltDmg"] > duel["boltDmg"]

    shiv = fe.resolve_stats("Jinx", 15, ["statikk-shiv", "wits-end"], [])
    one = fe.rotation("Jinx", shiv, fe.TARGETS["bruiser"], 8.0,
                      secondary_targets=0)
    three = fe.rotation("Jinx", shiv, fe.TARGETS["bruiser"], 8.0,
                        secondary_targets=2)
    assert three["boltDmg"] > one["boltDmg"]


def test_conditional_healing_and_overheal_shield_enter_metrics():
    plain = fe.metrics("Jinx", [], [])
    blood = fe.metrics("Jinx", ["bloodthirster"], [])
    assert blood["ehp"] > plain["ehp"]
    assert blood["sustain"] > plain["sustain"]

    gore = fe.metrics("Darius", ["goredrinker"], [])
    assert gore["sustain"] > fe.metrics("Darius", [], [])["sustain"]


def test_divine_sunderer_uses_melee_ranged_hp_split_and_real_cooldown():
    melee = fe.resolve_stats("Hecarim", 15, ["divine-sunderer"], [])
    ranged = fe.resolve_stats("Jinx", 15, ["divine-sunderer"], [])
    assert melee["spellbladePctMaxHp"] == 10
    assert melee["spellbladeHealPctMaxHp"] == 6
    assert ranged["spellbladePctMaxHp"] == 7
    assert ranged["spellbladeHealPctMaxHp"] == 2.5

    detail = fe.rotation("Hecarim", melee, fe.TARGETS["bruiser"], 8.0)
    # Six procs is the 1.5s cooldown cap over an 8-second reference fight;
    # it must not fire once per auto or once per ability without a cooldown.
    assert detail["spellbladeProcs"] == 6
    expected = 0.06 * fe.TARGETS["bruiser"]["hp"] * 6
    assert fe.analyze_build("Hecarim", ["divine-sunderer"], [])[
        "healing"]["spellblade"] == round(expected)


def test_eclipse_uses_melee_ranged_proc_and_shield_scaling():
    melee = fe.resolve_stats("Hecarim", 15, ["eclipse"], [])
    ranged = fe.resolve_stats("Jinx", 15, ["eclipse"], [])
    melee_proc = next(p for p in melee["procs"] if p["label"] == "eclipse")
    ranged_proc = next(p for p in ranged["procs"] if p["label"] == "eclipse")
    assert melee_proc["pctMaxHp"] == 0.07
    assert ranged_proc["pctMaxHp"] == 0.035
    assert melee_proc["cd"] == 6
    assert melee_proc["arm"] == 1.8
    assert melee["shield"] == 140
    assert melee["shieldPctBonusAd"] == 0.35
    assert ranged["shield"] == 70
    assert ranged["shieldPctBonusAd"] == 0.18


def test_sundered_sky_first_hit_and_heal_are_not_global_crit_damage():
    stats = fe.resolve_stats("Sett", 15, ["sundered-sky"], [])
    assert stats["critMult"] == fe.BASE_CRIT_MULT
    assert stats["firstHitCritMult"] == 1.6
    assert stats["firstHitCritCdSec"] == 6
    assert stats["firstHitHealBaseAdPct"] == 125
    assert stats["firstHitHealMissingHpPct"] == 6
    detail = fe.rotation("Sett", stats, fe.TARGETS["bruiser"], 8.0)
    assert detail["firstHitProcs"] == 2
    assert fe.metrics("Sett", ["sundered-sky"], [])["sustain"] > fe.metrics(
        "Sett", [], [])["sustain"]


def test_frontline_item_gaps_use_their_real_damage_and_scaling_channels():
    sterak = fe.resolve_stats("Darius", 15, ["steraks-gage"], [])
    bare = fe.resolve_stats("Darius", 15, [], [])
    assert sterak["bonusAd"] == bare["bonusAd"] + 0.50 * bare["baseAd"]

    bloodmail = fe.resolve_stats("Darius", 15, ["overlords-bloodmail"], [])
    assert bloodmail["bonusAd"] == 32 + 30 + 0.025 * 450
    assert 0 < bloodmail["damageAmp"] < 0.09

    stride = fe.resolve_stats("Darius", 15, ["stridebreaker"], [])
    assert any(p["label"] == "stridebreaker" and p["type"] == "physical"
               and p["adRatio"] == 1.0 for p in stride["procs"])

    ice = fe.resolve_stats("Darius", 15, ["iceborn-gauntlet"], [])
    assert ice["spellbladeBonusArmorPct"] == 25

    heart = fe.resolve_stats("Darius", 15, ["heartsteel"], [])
    assert all(p["type"] == "physical" for p in heart["procs"])
    assert all(p["cd"] == 20 for p in heart["procs"])


def test_item_proc_healing_and_melee_deaths_dance_split():
    unending = fe.metrics("Rammus", ["unending-despair"], [])
    plain = fe.metrics("Rammus", [], [])
    assert unending["sustain"] > plain["sustain"]

    melee = fe.resolve_stats("Darius", 15, ["deaths-dance"], [])
    ranged = fe.resolve_stats("Jinx", 15, ["deaths-dance"], [])
    assert melee["dr"] == 0.30
    assert ranged["dr"] == 0.12


def test_contextual_frontline_effects_are_exposed_without_global_inflation():
    heart = fe.metrics("Darius", ["heartsteel"], [])
    plain = fe.metrics("Darius", [], [])
    assert heart["procMaxHealthGain"] > 0
    assert plain["procMaxHealthGain"] == 0

    fimbul = fe.resolve_stats("Sion", 15, ["fimbulwinter"], [])
    assert fimbul["shieldManaComponent"] > 0
    assert fimbul["shieldManaNearbyMult"] == 1.8
    scenario = fe.damage_scenarios("Sion", ["fimbulwinter"], [])
    assert scenario["oneVsThree"]["nearbyShieldBonus"] > 0


def test_high_payoff_rune_context_corrections_are_grounded():
    melee = fe.resolve_stats("Darius", 15, [], ["Conqueror"])
    ranged = fe.resolve_stats("Jinx", 15, [], ["Conqueror"])
    assert melee["conquerorHealPct"] == 0.09
    assert ranged["conquerorHealPct"] == 0.06
    assert fe.metrics("Darius", [], ["Conqueror"])["sustain"] > fe.metrics(
        "Darius", [], [])["sustain"]

    font = fe.resolve_stats("Jinx", 15, [], ["Font of Life"])
    assert font["runeHealPerSec"] > 0
    assert font["runeAllyHealPerSec"] > font["runeHealPerSec"]

    grasp = fe.resolve_stats("Jinx", 15, [], ["Grasp of the Undying"])
    assert grasp["graspPct"] == 3.3 * 0.6


def test_authoritative_patch_recipes_are_optional_and_not_invented():
    assert fe.item_components("infinity-edge") == [
        "B. F. Sword", "Pickaxe", "Brawler's Gloves"
    ]
    # A completed item absent from the patch's changed-path list is unknown,
    # not an empty recipe guessed from its gold cost.
    assert fe.item_components("guardian-angel") == []


def test_durability_pressure_includes_mixed_damage_and_true_damage():
    assert sum(fe.incoming_damage_mix("Rammus")) == 1
    assert fe.incoming_damage_mix("Rammus")[2] > fe.incoming_damage_mix("Jinx")[2]
    tank = fe.evaluation_vector("Rammus", ["amaranths-twinguard"], [], fast=True)
    carry = fe.evaluation_vector("Jinx", ["amaranths-twinguard"], [], fast=True)
    assert tank["compEhp"] > 0 and carry["compEhp"] > 0


def test_rammus_ball_curl_uses_ranked_defense_and_damage_amp():
    stats = fe.resolve_stats("Rammus", 15, [], [])
    # The active defense is duration-bound; it should not be baked into the
    # displayed base stat block before a fight window is chosen.
    assert stats["armor"] < 150 and stats["mr"] < 80
    assert any(row.get("armorPct") == 0.6 for row in stats["timedSteroids"])
    detail = fe.rotation("Rammus", stats, fe.TARGETS["bruiser"], 8.0)
    assert any("kit amp" in label for label, _ in detail["parts"])


def test_rammus_reactive_reflection_prices_contact_and_thornmail():
    bare = fe.resolve_stats("Rammus", 15, [], [])
    thorn = fe.resolve_stats("Rammus", 15, ["thornmail"], [])
    no_contact = dict(fe.TARGETS["bruiser"], incomingAutoAttacksPerSec=0)
    assert not any("reactive reflection" in label
                   for label, _ in fe.rotation("Rammus", bare, no_contact, 8.0)["parts"])
    reflected = fe.rotation("Rammus", thorn, fe.TARGETS["bruiser"], 8.0)
    assert any("reactive reflection" in label for label, _ in reflected["parts"])
    assert reflected["total"] > fe.rotation(
        "Rammus", bare, fe.TARGETS["bruiser"], 8.0)["total"]


def test_context_assumptions_are_disclosed_without_becoming_free_damage():
    panel = fe.damage_scenarios("Jinx", ["runaans-hurricane"], [], level=15)
    vector = fe.evaluation_vector("Jinx", ["runaans-hurricane"], [], fast=True)
    assert "positioning" in panel["contextAssumptions"]
    assert "takedownAvailability" in vector["contextAssumptions"]
    assert "enemyActions" in vector["contextAssumptions"]


def test_ranged_carries_do_not_rush_flat_pen_boots_on_unknown_armour():
    order = fe.optimal_purchase_order(
        "Caitlyn", ["infinity-edge", "lord-dominiks-regard", "rapid-firecannon",
                     "bloodthirster", "galeforce"], "boots-of-dynamism", [], "standard")
    assert order[0] != "boots-of-dynamism"
