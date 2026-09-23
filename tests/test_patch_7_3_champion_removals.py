"""Regression checks for mechanics Riot removed in Wild Rift patch 7.3.

These are deliberately assertions about both source layers. A removed mechanic
left in ``champions_wr.json`` is still printed on the champion page; one left
in ``ability_formulas.json`` is still simulated by the advisor and fight
engine even if the tooltip looks correct.
"""
from __future__ import annotations

import json
import copy
from pathlib import Path

from scripts.reconcile_patch_7_3_formulas import apply as apply_formula_corrections
from scripts.reconcile_patch_7_3_tooltips import apply as apply_tooltip_corrections


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def load(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def champion_text(name: str) -> str:
    champion = next(c for c in load("champions_wr.json") if c["name"] == name)
    return " ".join(a.get("text", "") for a in champion.get("abilities", []))


def test_removed_champion_mechanics_are_absent_from_tooltips():
    forbidden = {
        "Twitch": (
            "full stacks of Deadly Venom, Twitch gains",
            "attacks apply an additional stack of Deadly Venom",
        ),
        "Tryndamere": (
            "Attacking a champion grants 30% Attack Speed",
            "Increases Battle Fury's bonus Attack Speed",
            "Battle Fury's Attack Speed bonus increases",
        ),
        "Nunu & Willump": ("Deals 150% damage to monsters",),
        "Zed": ("Deals 80% damage to monsters", "Deals 60% damage to monsters"),
    }
    for champion, phrases in forbidden.items():
        text = champion_text(champion)
        for phrase in phrases:
            assert phrase not in text, f"{champion} still prints removed 7.3 mechanic: {phrase}"


def test_removed_champion_mechanics_are_absent_from_fight_formulas():
    formulas = load("ability_formulas.json")

    assert formulas["Tryndamere"]["abilities"]["P"]["steroids"] == []
    assert formulas["Tryndamere"]["abilities"]["1"]["steroids"] == []
    assert formulas["Tryndamere"]["abilities"]["4"]["steroids"] == []
    assert formulas["Twitch"]["abilities"]["P"]["steroids"] == []

    twitch_ambush = formulas["Twitch"]["abilities"]["1"]["steroids"]
    attack_speed = next(s for s in twitch_ambush if s.get("stat") == "attackSpeed")
    assert attack_speed["pct"] == [35, 40, 45, 50]
    assert attack_speed["durationS"] == 6

    stale = " ".join(
        note
        for champion in ("Twitch", "Tryndamere", "Nunu & Willump", "Zed")
        for ability in formulas[champion]["abilities"].values()
        for note in ability.get("unmodeled", [])
    )
    for phrase in (
        "additional stack of Deadly Venom",
        "Deals 150% damage to monsters",
        "Deals 80% damage to monsters",
        "Deals 60% damage to monsters",
    ):
        assert phrase not in stale


def test_tryndamere_current_7_3_values_are_in_the_tooltip_and_formula():
    text = champion_text("Tryndamere")
    assert "20% / 40% / 60% / 80%" in text
    assert "+100% bonus AD +80% AP" in text

    spinning_slash = load("ability_formulas.json")["Tryndamere"]["abilities"]["3"]
    ratios = {r["stat"]: r["pct"] for r in spinning_slash["damage"][0]["ratios"]}
    assert ratios == {"ad": 100.0, "ap": 80.0}


def test_twitch_contaminate_uses_the_7_3_split_damage_model():
    contaminate = load("ability_formulas.json")["Twitch"]["abilities"]["3"]["damage"]
    physical = next(c for c in contaminate if c["name"] == "Contaminate Per Stack")
    magic = next(c for c in contaminate if c["name"] == "Contaminate Magic Per Stack")
    assert physical["ratios"] == [{"stat": "bonusAd", "pct": 35}]
    assert magic["ratios"] == [{"stat": "ap", "pct": 35}]
    assert physical["hits"] == magic["hits"] == 5


def test_all_asserted_7_3_reconciliations_are_idempotent():
    champions = load("champions_wr.json")
    assert apply_tooltip_corrections(champions) == 0

    formulas = load("ability_formulas.json")
    before = copy.deepcopy(formulas)
    apply_formula_corrections(formulas)
    assert formulas == before


def test_frontend_ability_cards_match_the_canonical_tooltips():
    source = {c["slug"]: c for c in load("champions_wr.json")}
    frontend = json.loads(
        (ROOT / "web-next" / "src" / "data" / "champion_details.json")
        .read_text(encoding="utf-8")
    )
    for slug, champion in source.items():
        if slug not in frontend:
            continue
        expected = {a["slot"]: a.get("text", "") for a in champion.get("abilities", [])}
        actual = {a["slot"]: a.get("text", "") for a in frontend[slug].get("abilities", [])}
        assert actual == expected, f"{slug} frontend ability cards are stale"
