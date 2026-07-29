"""Shared fixtures. No test in this suite may reach the DeepSeek API.

Everything under test is deterministic: profile derivation, filtering, prompt
assembly and validation. The model call is the one thing we do not exercise, so
a test that needs a build supplies one as a fixture.
"""
from __future__ import annotations

import pytest

from web import build_advisor as advisor
from web.advisor import validate as validate_mod


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Fail loudly if anything tries to call the model."""
    def explode(*_args, **_kwargs):
        raise AssertionError("a test attempted a live DeepSeek call")
    monkeypatch.setattr(advisor, "_call", explode)


def make_build(**overrides) -> dict:
    """A valid Hecarim-shaped build, as a starting point for mutation.

    Tests override one field at a time so a failure names exactly one cause.
    """
    build = {
        "items": ["black-cleaver", "trinity-force", "deaths-dance",
                  "steraks-gage", "guardian-angel"],
        "boots": "ionian-boots-of-lucidity",
        "candidateItemScores": [
            {"item": s, "score": 80, "reason": "core"} for s in
            ["black-cleaver", "trinity-force", "deaths-dance", "steraks-gage",
             "guardian-angel", "sundered-sky", "goredrinker", "dead-mans-plate",
             "thornmail", "sunfire-aegis", "warmogs-armor", "randuins-omen"]
        ],
        "mandatoryAuditScores": [],
        "runes": {
            "keystone": "Conqueror", "primaryTree": "Precision",
            "minors": ["Brutal", "Last Stand", "Legend: Alacrity"],
            "flex": "Celerity",
        },
        "summoners": ["Flash", "Smite"],
        # Names an item AND a rune from the page above, which is what the
        # playGuide check requires: a guide that could be pasted onto any build
        # for this champion is filler, and one that only discusses items is
        # describing a third of what was chosen.
        "playGuide": {
            "earlyGame": "Clear to level four before looking for a gank, using Conqueror "
                         "stacks from repeated hits rather than one burst window.",
            "powerSpike": "Black Cleaver at one item is the spike; the armour shred turns "
                          "a losing dive into a winning one.",
            "teamfight": "Open on the target Trinity Force can reach, then hold Last Stand "
                         "range rather than retreating early.",
            "pitfall": "Spending the engage before Conqueror is stacked wastes the whole "
                       "build, which pays out over a long fight rather than instantly.",
        },
        "situational": [],
        "situationalRunes": [],
        "situationalBoots": [],
        "snowballSwap": None,
        "buildScore": {
            "overall": 80, "burst": 70, "sustainedDamage": 80, "survivability": 75,
            "mobility": 90, "utility": 60, "earlyPower": 70, "confidence": 70,
            "reason": "solid all-round bruiser build",
        },
        "why": ["moves fast", "sticks to targets"],
    }
    build.update(overrides)
    return build


def check(build: dict, **kwargs) -> validate_mod.Report:
    """Validate with the wiring build_advisor uses, so tests match production."""
    defaults = dict(
        champion_class="Bruiser", role="Jungle", mode="studio", enemies_known=False,
        resolve_item=advisor._resolve_item,
        resolve_summoner=lambda n: advisor.SUMMONER_CANON.get(
            advisor._canon(str(n or ""))),
        summoner_icons={n: "icon" for n in advisor.SUMMONERS},
    )
    defaults.update(kwargs)
    return validate_mod.validate(build, **defaults)


@pytest.fixture
def build():
    return make_build()
