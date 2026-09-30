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
