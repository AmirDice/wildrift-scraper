"""Run the TypeScript engine's behavioural checks as part of the normal suite.

WHY A WRAPPER RATHER THAN A TS TEST RUNNER

    web-next has no test runner and adding one for a single file is a
    dependency the repo does not otherwise need. scripts/engine_parity.py
    already drives a TS script from Python for exactly this reason, so this
    follows it: `pytest tests/` runs everything, including the half of the
    engine that only exists in TypeScript.

WHAT IT GUARDS

    engine_parity covers what BOTH engines do, and covers it well. It cannot
    touch duel(), mutualDuel(), championTarget(), kitSustain(), supportValue()
    or the crowd-control and enemy model, because none of them has a Python
    twin to diff against. Those were verified by hand once and then had nothing
    holding them in place. web-next/scripts/engine_model_check.ts is that
    something; this makes it run.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from web import fight_engine as fe

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web-next"
CHECK = WEB / "scripts" / "engine_model_check.ts"


@pytest.mark.skipif(not CHECK.exists(), reason="engine_model_check.ts is absent")
@pytest.mark.skipif(shutil.which("npx") is None, reason="npx is not on PATH")
@pytest.mark.skipif(not (WEB / "node_modules").is_dir(),
                    reason="web-next dependencies are not installed")
def test_engine_model_behaviour():
    """The TS-only engine model behaves the way it was built to behave."""
    # NO shell=True. With a LIST of arguments its behaviour is platform
    # specific: Windows joins the list, so this worked on the dev machine for
    # months, while POSIX runs only the first element and passes the rest as
    # $0, $1 -- so CI executed a bare `npx`, which prints usage and exits 0.
    # The test then saw returncode 0 with empty stdout and failed on every
    # push since 2026-09-10. shutil.which resolves npx.cmd on Windows, so
    # dropping the shell costs nothing there.
    result = subprocess.run(
        [shutil.which("npx"), "tsx", "scripts/engine_model_check.ts"],
        cwd=WEB, capture_output=True, text=True, timeout=600,
    )
    output = f"{result.stdout}\n{result.stderr}".strip()
    # The script prints one FAIL line per broken behaviour and exits non-zero,
    # so the whole readout is the failure message worth seeing.
    assert result.returncode == 0, f"engine model checks failed:\n{output}"
    assert "checks passed" in result.stdout, output


# ---------------------------------------------------------------------------
# SPELLBLADE CHARGING
#
# Three abilities deliver all their damage through basic attacks and carry the
# placeholder 1.0 cooldown. Read as a real one-second cooldown they are 8-9
# casts per eight-second window, which saturated Spellblade for free and made
# Dusk and Dawn -- a 60 AP item on a champion with no AP scaling -- score as
# Jinx's best fifth item, because every proc also re-applied Blade of the
# Ruined King and Kraken on-hits.
# ---------------------------------------------------------------------------


def _spellblade_procs(champion: str) -> int:
    stats = fe.resolve_stats(champion, 15, ["dusk-and-dawn", "berserkers-greaves"], [])
    result = fe.rotation(champion, stats, fe.target_profiles(15)["bruiser"], 8.0,
                         level=15)
    row = next((p for p in result["parts"] if p[0].startswith("spellblade")), None)
    return int(row[0].split("x")[1]) if row else 0


@pytest.mark.parametrize("champion,slot", [
    ("Jinx", "1"), ("Vi", "3"), ("Heimerdinger", "1"),
])
def test_placeholder_cooldown_attack_riders_do_not_charge_spellblade(champion, slot):
    ability = fe.FORMULAS[champion]["abilities"][slot]

    assert all(float(c) == 1.0 for c in ability["cooldowns"]), "fixture changed"
    assert fe.charges_spellblade(ability) is False


@pytest.mark.parametrize("champion,slot", [
    ("Gwen", "3"), ("Garen", "1"), ("Camille", "1"), ("Xin Zhao", "1"),
])
def test_real_cooldown_attack_empowers_still_charge_spellblade(champion, slot):
    """These empower an attack too, but they are genuine casts on a real CD."""
    assert fe.charges_spellblade(fe.FORMULAS[champion]["abilities"][slot]) is True


def test_a_weapon_swap_cannot_saturate_spellblade():
    """Jinx's Q is a stance toggle; only Zap, Chompers and the rocket count."""
    cap = 1 + int(8.0 / fe.SPELLBLADE_CD)

    assert _spellblade_procs("Jinx") < cap
    assert _spellblade_procs("Vi") < cap


def test_the_rider_is_still_cast_and_still_shown():
    """It must leave the cast log alone: the combo tells the player to press it."""
    stats = fe.resolve_stats("Jinx", 15, ["berserkers-greaves"], [])
    result = fe.rotation("Jinx", stats, fe.target_profiles(15)["bruiser"], 8.0,
                         level=15)

    assert result["castLog"]["1"]["name"] == "Switcheroo!"
    assert result["castLog"]["1"]["casts"] > 1


def test_current_health_on_hit_decays_at_the_rate_a_dying_target_implies():
    """BotRK is charged against STARTING health, so the factor is the decay.

    A linear burn from full to zero averages 50% current health, and every one
    of the five reference profiles loses its whole health pool inside the eight
    second window, tank included. The value was 0.7, which is what a target
    losing only about 60% averages: a fight the engine never runs.
    """
    assert fe.CURRENT_HP_DECAY == 0.5

    bruiser = fe.target_profiles(15)["bruiser"]
    with_botrk = fe.resolve_stats(
        "Jinx", 15, ["blade-of-the-ruined-king", "berserkers-greaves"], [])
    without = fe.resolve_stats("Jinx", 15, ["berserkers-greaves"], [])

    assert with_botrk["onHitPctCurrentHp"] > 0
    assert without["onHitPctCurrentHp"] == 0
    # The channel is still worth real damage; this is a recalibration, not a
    # removal, and a regression to 0 would otherwise pass the assert above.
    gain = (fe.rotation("Jinx", with_botrk, dict(bruiser), 8.0, level=15)["total"]
            - fe.rotation("Jinx", without, dict(bruiser), 8.0, level=15)["total"])
    assert gain > 500


def test_both_engines_agree_on_the_decay_constant():
    """The browser engine carries its own copy; drift here is silent."""
    source = (Path(__file__).resolve().parents[1]
              / "web-next" / "src" / "lib" / "engine.ts").read_text(encoding="utf-8")

    assert f"const CURRENT_HP_DECAY = {fe.CURRENT_HP_DECAY};" in source
    assert "* 0.7" not in source.split("onHitPctCurrentHp")[1][:200]


# ---------------------------------------------------------------------------
# ONE-FIGHT CONTRACT AND CHAMPION-SPECIFIC INTERACTIONS
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("champion", ["Jax", "Miss Fortune", "Rammus", "Vayne"])
def test_an_ultimate_is_never_cast_twice_in_one_fight(champion):
    stats = fe.resolve_stats(champion, 15, [], [])
    result = fe.rotation(champion, stats, fe.target_profiles(15)["bruiser"],
                         20.0, level=15)
    ultimate = (result.get("castLog") or {}).get("4") or {}
    assert ultimate.get("casts", 0) <= 1


def test_guardian_angel_is_one_second_life_not_repeatable_value():
    stats = fe.resolve_stats("Caitlyn", 15, ["guardian-angel"], [])
    assert stats["shieldPctMaxHp"] == pytest.approx(0.5)


def test_jax_ultimate_attack_rider_uses_every_second_hit(monkeypatch):
    """Grandmaster-at-Arms is stored on slot 4, not passive slot P."""
    target = {"hp": 2600, "armor": 90, "mr": 60, "bonusHp": 900}
    items = ["titanic-hydra", "hullbreaker"]
    stats = fe.resolve_stats("Jax", 15, items, [])
    full = fe.rotation("Jax", stats, dict(target), 8.0, level=15)

    ultimate = fe.FORMULAS["Jax"]["abilities"]["4"]
    active_only = [row for row in ultimate["damage"]
                   if row.get("when") != "per auto"]
    monkeypatch.setitem(ultimate, "damage", active_only)
    without_rider = fe.rotation("Jax", stats, dict(target), 8.0, level=15)

    # Six autos during the eight-second active produce three, not six, riders.
    expected_one = 185 * (100 / (100 + target["mr"]))
    assert full["nAutos"] == 6
    assert full["total"] - without_rider["total"] == pytest.approx(
        expected_one * 3, rel=0.01)


def test_rammus_reflection_requires_incoming_attacks():
    stats = fe.resolve_stats("Rammus", 15, ["thornmail"], [])
    target = {"hp": 2600, "armor": 90, "mr": 60, "bonusHp": 900,
              "incomingAutoAttacksPerSec": 0.9}
    contact = fe.rotation("Rammus", stats, dict(target), 8.0, level=15)
    target["incomingAutoAttacksPerSec"] = 0
    no_contact = fe.rotation("Rammus", stats, dict(target), 8.0, level=15)

    assert contact["total"] > no_contact["total"]
    assert any(label == "reactive reflection" for label, _ in contact["parts"])


# ---------------------------------------------------------------------------
# SECONDARY TARGET REACH
#
# The multi-target panel charged every secondary effect at full rate for the
# whole window: Runaan's fired at both secondaries on 100% of attacks and each
# bolt carried the entire on-hit bundle. On a two-item Caitlyn that was 13
# primary applications of BotRK and 26 more through bolts, and bolt damage on
# secondaries came out level with the primary target's whole damage.
# ---------------------------------------------------------------------------


def test_the_nearest_secondary_is_reachable_more_often_than_the_next():
    assert fe.secondary_reach(0) > fe.secondary_reach(1)
    assert fe.secondary_reach(0) < 1.0, "a flat 100% is what this replaced"
    assert fe.secondary_reach(-1) == 0.0


def test_reach_total_is_below_the_raw_target_count():
    assert fe.secondary_reach_total(0) == 0
    assert fe.secondary_reach_total(2) < 2
    assert fe.secondary_reach_total(5) < 5
    # Past the table the tail rate repeats rather than falling to zero.
    assert fe.secondary_reach_total(5) > fe.secondary_reach_total(2)


def test_bolts_no_longer_out_damage_the_primary_target():
    stats = fe.resolve_stats(
        "Caitlyn", 15, ["blade-of-the-ruined-king", "runaans-hurricane",
                        "berserkers-greaves"], [])
    result = fe.rotation("Caitlyn", stats, fe.target_profiles(15)["bruiser"],
                         8.0, level=15, secondary_targets=2)

    assert result["boltDmg"] > 0, "Runaan's must still be worth buying"
    assert result["boltDmg"] < result["total"] * 0.75


def test_statikk_chain_lightning_exists_in_both_engines():
    """It was modelled in Python only, and no battery case covered the gap."""
    stats = fe.resolve_stats("Jinx", 15, ["statikk-shiv", "berserkers-greaves"], [])
    assert stats["aoeProcFlat"] > 0

    source = (Path(__file__).resolve().parents[1]
              / "web-next" / "src" / "lib" / "engine.ts").read_text(encoding="utf-8")
    assert "aoeProcFlat" in source and "doAoeProc" in source


# ---------------------------------------------------------------------------
# MELEE-RANGE ACTIVES AND CRIT SHAPES
# ---------------------------------------------------------------------------


def test_goredrinker_pays_a_ranged_champion_less_than_a_melee_one():
    """Thirsting Slash is point-blank; a marksman rarely stands there."""
    def ratio(champion):
        stats = fe.resolve_stats(champion, 15, ["goredrinker", "berserkers-greaves"], [])
        return next(p["totalAdRatio"] for p in stats["procs"] if p["label"] == "goredrinker")

    assert ratio("Darius") == pytest.approx(1.75)
    assert ratio("Caitlyn") < ratio("Darius")
    assert ratio("Caitlyn") > 0, "a ranged champion can still use it sometimes"


def test_caitlyn_headshot_grows_with_crit_rate_and_crit_damage():
    """7.3 put Headshot on crit scaling; the model kept only its 60% AD ratio."""
    comp = next(c for c in fe.FORMULAS["Caitlyn"]["abilities"]["P"]["damage"]
                if c["name"] == "Headshot")
    assert comp["critAdBonus"]["perCritRate"] > 0

    target = fe.target_profiles(15)["bruiser"]
    no_crit = fe.resolve_stats("Caitlyn", 15, ["berserkers-greaves"], [])
    crit = fe.resolve_stats(
        "Caitlyn", 15, ["infinity-edge", "the-collector", "rapid-firecannon",
                        "berserkers-greaves"], [])

    assert no_crit["crit"] == 0 and crit["crit"] > 0.5
    per_auto_no_crit = fe.rotation("Caitlyn", no_crit, dict(target), 8.0, level=15)
    per_auto_crit = fe.rotation("Caitlyn", crit, dict(target), 8.0, level=15)
    assert per_auto_crit["total"] > per_auto_no_crit["total"]


def test_crit_damage_scaling_reaches_the_ultimates_that_gained_it():
    for champion, slot, comp_name in [
        ("Miss Fortune", "4", "Bullet Time"),
        ("Jhin", "4", "Curtain Call 4th Shot"),
    ]:
        comp = next(c for c in fe.FORMULAS[champion]["abilities"][slot]["damage"]
                    if c["name"] == comp_name)
        assert comp["critScale"]["perCritDamage"] > 0, f"{champion} {comp_name}"


def test_crit_corrections_live_in_the_overlay_not_the_extraction():
    """A re-extraction must not be able to drop them."""
    overlay = json.loads((Path(__file__).resolve().parents[1] / "data"
                          / "formula_corrections.json").read_text(encoding="utf-8"))
    caitlyn = overlay["champions"]["Caitlyn"]["abilities"]["P"]["components"]

    assert "critAdBonus" in caitlyn["Headshot"]
