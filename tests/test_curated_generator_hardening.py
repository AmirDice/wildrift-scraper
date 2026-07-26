"""Regression tests for reviewed build paths and deterministic generation."""
from __future__ import annotations

import scripts.build_champions_llm as curated
from web import build_advisor as live_advisor
from web.advisor import profiles


LIVE_CALL = live_advisor._call


def _fake_item(slug: str, category: str, **stats) -> dict:
    return {
        "slug": slug,
        "category": category,
        "categories": [category],
        "stats": {name: {"value": value} for name, value in stats.items()},
        "passives": [],
        "tags": [],
    }


def _core(*slugs: str) -> list[dict]:
    return [{"slug": slug} for slug in slugs]


def test_every_primary_variant_uses_reviewed_identity_not_coarse_scaling_tags():
    items = {
        **{f"ap-{i}": _fake_item(f"ap-{i}", "Magic", ap=80) for i in range(5)},
        **{f"tank-{i}": _fake_item(f"tank-{i}", "Defense", armor=50) for i in range(5)},
    }
    ap_core = _core(*(f"ap-{i}" for i in range(5)))
    for variant in ("standard", "damage", "tanky"):
        rammus = curated._path_errors(
            variant, ap_core, items, profiles.build_identity_profile("Rammus"))
        nasus = curated._path_errors(
            variant, ap_core, items, profiles.build_identity_profile("Nasus"))
        assert rammus, variant
        assert nasus, variant
    assert not curated._path_errors(
        "standard", _core(*(f"tank-{i}" for i in range(5))), items,
        profiles.build_identity_profile("Rammus"))


def test_ap_fiora_and_irelia_are_rejected_but_nunu_ap_alternative_is_approved():
    items = {f"ap-{i}": _fake_item(f"ap-{i}", "Magic", ap=80) for i in range(5)}
    ap_core = _core(*(f"ap-{i}" for i in range(5)))
    for name in ("Fiora", "Irelia"):
        assert curated._path_errors(
            "standard", ap_core, items, profiles.build_identity_profile(name))
    assert not curated._path_errors(
        "offmeta", ap_core, items, profiles.build_identity_profile("Nunu & Willump"))


def test_master_yi_routes_to_carry_variants_and_rejects_lethality_stack():
    assert curated.variants_for("Master Yi", "Assassin", "Jungle") == [
        "standard", "dps", "crit", "antitank",
    ]
    items = {item["slug"]: item for item in curated._load(curated.ITEMS)}
    identity = profiles.build_identity_profile("Master Yi")
    lethality = _core("youmuus-ghostblade", "duskblade-of-draktharr",
                      "edge-of-night", "seryldas-grudge", "guardian-angel")
    assert curated._path_errors("standard", lethality, items, identity)

    on_hit = _core("blade-of-the-ruined-king", "wits-end", "terminus",
                   "nashors-tooth", "deaths-dance")
    assert curated._path_errors("standard", on_hit, items, identity) == []


def _score() -> dict:
    return {
        "overall": 80, "burst": 75, "sustainedDamage": 70,
        "survivability": 70, "mobility": 65, "utility": 65,
        "earlyPower": 70, "confidence": 75, "reason": "coherent tested path",
    }


def _raw_build(items: list[str], boots: str, tree: str = "Precision") -> dict:
    if tree == "Domination":
        keystone = "Electrocute"
        minors = ["Cheap Shot", "Chain Assault", "Eyeball Collector"]
        flex = "Transcendence"
    else:
        keystone = "Conqueror"
        minors = ["Brutal", "Last Stand", "Legend: Alacrity"]
        flex = "Celerity"
    return {
        "summary": "A coherent build.",
        "coreBuild": [{"slug": slug, "reason": "core"} for slug in items],
        "boots": {"slug": boots, "reason": "best default"},
        "situationalBoots": [],
        "buildScore": _score(),
        "situational": [],
        "situationalRunes": [],
        "runes": {
            "keystone": {"name": keystone, "reason": "fits the combat loop"},
            "primaryTree": tree,
            "treeMinors": [{"name": name, "reason": "fits"} for name in minors],
            "flexMinor": {"name": flex, "reason": "fits"},
        },
    }


def _validate_one(name: str, champ_class: str, role: str, variant: str, build: dict):
    items = curated._load(curated.ITEMS)
    runes = curated._load(curated.RUNES)
    rules = curated._load(curated.RULES) or {}
    item_by_slug = {item["slug"]: item for item in items}
    rune_by_name = {rune["name"]: rune for rune in runes}
    mutex = {key: set(value) for key, value in curated.hard_exclusive_groups(rules).items()}
    return curated._validate(
        {"synergyNotes": ["tested"], "builds": {variant: build}}, [variant],
        item_by_slug, rune_by_name, mutex, [], role, champ_class, name,
    )


def test_curated_situational_boots_survive_validation_with_upgrade_pair():
    build = _raw_build(
        ["black-cleaver", "trinity-force", "deaths-dance", "steraks-gage",
         "guardian-angel"],
        "ionian-boots-of-lucidity",
    )
    build["situationalBoots"] = [
        {"boots": "plated-steelcaps", "when": "vs repeated AD basic attacks"},
        {"boots": "mercurys-treads", "when": "vs AP damage and hard crowd control"},
    ]
    clean, errors, _warnings = _validate_one(
        "Hecarim", "Bruiser", "Jungle", "standard", build)
    assert errors == []
    assert clean["builds"]["standard"]["situationalBoots"] == [
        {"boots": "plated-steelcaps", "bootsUpgrade": "armored-advance",
         "when": "vs repeated AD basic attacks"},
        {"boots": "mercurys-treads", "bootsUpgrade": "chainlaced-crushers",
         "when": "vs AP damage and hard crowd control"},
    ]


def test_validated_nunu_alternative_emits_frontend_approval_marker():
    build = _raw_build(
        ["ludens-echo", "rabadons-deathcap", "liandrys-torment", "riftmaker",
         "horizon-focus"],
        "boots-of-mana", tree="Domination",
    )
    clean, errors, _warnings = _validate_one(
        "Nunu & Willump", "Tank", "Jungle", "offmeta", build)
    assert errors == []
    alternative = clean["builds"]["offmeta"]
    assert alternative["alternativePathApproved"] is True
    assert alternative["pathLabel"] == "AP Burst"


class _Response:
    status_code = 200
    ok = True
    text = ""

    def json(self):
        return {"choices": [{"finish_reason": "stop", "message": {"content": '{"ok": true}'}}]}


def test_curated_deepseek_request_sends_temperature_and_keeps_thinking(monkeypatch):
    seen = {}

    def fake_post(_url, **kwargs):
        seen.update(kwargs["json"])
        return _Response()

    monkeypatch.setattr(curated.requests, "post", fake_post)
    llm = object.__new__(curated.LLM)
    llm.provider = "deepseek"
    llm.model = "test"
    llm._key = "test"
    assert llm.generate(["prompt"], 0.0) == '{"ok": true}'
    assert seen["temperature"] == 0.0
    assert seen["thinking"] == {"type": "enabled"}
    assert seen["reasoning_effort"] == "high"


def test_live_deepseek_request_is_temperature_zero_and_keeps_thinking(monkeypatch):
    seen = {}

    def fake_post(_url, **kwargs):
        seen.update(kwargs["json"])
        return _Response()

    monkeypatch.setattr(live_advisor.requests, "post", fake_post)
    assert LIVE_CALL("test", "prompt") == {"ok": True}
    assert seen["temperature"] == 0
    assert seen["thinking"] == live_advisor.THINKING
    assert seen["reasoning_effort"] == "high"
