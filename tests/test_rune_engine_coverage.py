"""Regression checks for the model-free rune engine audit."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from web.build_advisor import _engine_major_coverage_gaps
from web.fight_engine import (TARGETS, resolve_stats, rotation,
                              rune_mechanics_coverage)


def _damage(champion: str, items: list[str], runes: list[str], target=None,
            window: float = 8.0) -> float:
    st = resolve_stats(champion, 15, items, runes)
    return rotation(champion, st, target or TARGETS["bruiser"], window, 15)["total"]


def test_patch_73_catalogue_values() -> None:
    curated = json.loads((ROOT / "data" / "rune_effects.json").read_text(encoding="utf-8"))
    engine = json.loads((ROOT / "data" / "rune_engine.json").read_text(encoding="utf-8"))
    lethal = curated["keystones"]["Lethal Tempo"]
    assert lethal["asPctPerStackMelee"] == 8
    assert lethal["asPctPerStackRanged"] == 6.4
    assert curated["minors"]["Legend: Alacrity"]["asPctAvg"] == 18
    assert engine["Legend: Haste"]["hasteFlat"] == 15
    assert engine["Ingenious Hunter"]["itemHasteFlat"] == 0
    assert engine["Legend: Tenacity"]["tenacityPct"] == 0


def test_lethal_tempo_ramps_and_fires_bullets() -> None:
    items = ["infinity-edge", "runaans-hurricane"]
    base = resolve_stats("Jinx", 15, items, [])
    lethal = resolve_stats("Jinx", 15, items, ["Lethal Tempo"])
    # It is not a permanent stat granted before combat.
    assert lethal["as"] == base["as"]
    assert _damage("Jinx", items, ["Lethal Tempo"]) > _damage("Jinx", items, [])


def test_conqueror_uses_adaptive_stat() -> None:
    ap = resolve_stats("Ahri", 15, ["rabadons-deathcap"], ["Conqueror"])
    ap_base = resolve_stats("Ahri", 15, ["rabadons-deathcap"], [])
    ad = resolve_stats("Jinx", 15, ["bloodthirster"], ["Conqueror"])
    ad_base = resolve_stats("Jinx", 15, ["bloodthirster"], [])
    assert ap["ap"] > ap_base["ap"] and ap["bonusAd"] == ap_base["bonusAd"]
    assert ad["bonusAd"] > ad_base["bonusAd"] and ad["ap"] == ad_base["ap"]


def test_grasp_scales_from_own_health_not_target_health() -> None:
    items = ["warmogs-armor"]
    low = {"hp": 1800, "armor": 100, "mr": 80, "bonusHp": 0}
    high = {"hp": 6000, "armor": 100, "mr": 80, "bonusHp": 4200}
    low_gain = (_damage("Alistar", items, ["Grasp of the Undying"], low)
                - _damage("Alistar", items, [], low))
    high_gain = (_damage("Alistar", items, ["Grasp of the Undying"], high)
                 - _damage("Alistar", items, [], high))
    assert abs(low_gain - high_gain) < 1e-6


def test_cc_gated_runes_do_not_proc_on_no_cc_champion() -> None:
    no_cc = resolve_stats("Master Yi", 15, ["warmogs-armor"], ["Ice Overlord"])
    has_cc = resolve_stats("Alistar", 15, ["warmogs-armor"], ["Ice Overlord"])
    assert not any(p.get("label") == "Ice Overlord" for p in no_cc["procs"])
    assert any(p.get("label") == "Ice Overlord" for p in has_cc["procs"])


def test_empowered_attack_applies_ranged_penalty() -> None:
    ranged = resolve_stats("Jinx", 15, [], ["Empowered Attack"])
    melee = resolve_stats("Olaf", 15, [], ["Empowered Attack"])
    ranged_flat = next(p["flat"] for p in ranged["procs"] if p["label"] == "Empowered Attack")
    melee_flat = next(p["flat"] for p in melee["procs"] if p["label"] == "Empowered Attack")
    assert abs(ranged_flat / melee_flat - 0.8) < 1e-9


def test_partial_rune_blocks_authoritative_engine_gate() -> None:
    coverage = rune_mechanics_coverage(["Fleet Footwork", "Triumph", "Legend: Haste"])
    assert coverage["engineAuthoritative"] is False
    assert coverage["majorGapCount"] == 2
    gaps = _engine_major_coverage_gaps({"engine": {
        "runeCoverageGaps": coverage["gaps"],
    }})
    assert any("Fleet Footwork" in gap for gap in gaps)
    assert not any("Triumph" in gap for gap in gaps)


if __name__ == "__main__":
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            value()
            print(f"PASS {name}")
