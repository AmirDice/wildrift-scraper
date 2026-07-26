"""Summoner spells, decided in code rather than asked of the model.

Summoner choice in Wild Rift is close to a lookup: the jungler takes Smite, the
enchanter support takes Heal, the champion whose entire pattern is running you
down takes Ghost. There is no comparison to make and no trade-off to reason
about, so putting it in the prompt bought nothing and cost something -- every
generation had to be checked for whether the jungler remembered Smite, and a
build that was otherwise perfect could fail validation over it.

So the rules live in data/summoner_rules.json and are applied here. The model is
no longer told about summoner spells at all, and the result is correct by
construction instead of correct after checking.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DATA = ROOT / "data"

_RULES = json.loads((DATA / "summoner_rules.json").read_text(encoding="utf-8"))

RUN_DOWN: set[str] = set(_RULES["runDownChampions"]["names"])
MOBILE_MARKSMEN: set[str] = set(_RULES["marksmenWithMobility"]["names"])
ENGAGE_SUPPORT_CLASSES: set[str] = set(_RULES["engageSupportClasses"]["classes"])
DEFAULT: list[str] = list(_RULES["default"]["spells"])

# Mirrored from scripts/build_champions_llm.py so both generators show the same
# spells with the same icons.
_DD_SPELL = "https://ddragon.leagueoflegends.com/cdn/16.11.1/img/spell"
SPELLS: dict[str, dict] = {
    "Flash": {"dd": "SummonerFlash", "desc": "Short-range blink."},
    "Ignite": {"dd": "SummonerDot", "desc": "True damage burn + 50% Grievous Wounds."},
    "Ghost": {"dd": "SummonerHaste", "desc": "Large move speed for 6s."},
    "Exhaust": {"dd": "SummonerExhaust", "desc": "Slows an enemy and cuts their damage 35%."},
    "Smite": {"dd": "SummonerSmite", "desc": "Monster/objective execute."},
    "Cleanse": {"dd": "SummonerBoost", "desc": "Removes CC and lowers further CC."},
    "Heal": {"dd": "SummonerHeal", "desc": "Burst heal + move speed for you and an ally."},
    "Barrier": {"dd": "SummonerBarrier", "desc": "Self shield."},
}


def summoners_for(champion: str, role: str, champion_class: str) -> tuple[list[str], str]:
    """The two spells for this champion, and why.

    Rules are applied in precedence order; the first match wins. The reason is
    returned so it can be shown to the player and logged, rather than the
    assignment looking arbitrary.
    """
    role = (role or "").strip().lower()
    champion_class = (champion_class or "").strip()

    # 1. Smite is not optional for a jungler; only the partner is in question.
    if role == "jungle":
        if champion in RUN_DOWN:
            return ["Ghost", "Smite"], (
                f"{champion} wins by closing distance and staying on a target, so Ghost is "
                "part of the kit rather than a preference; Smite is mandatory in the jungle.")
        return ["Flash", "Smite"], "Smite is mandatory in the jungle; Flash is the default partner."

    # 2. The run-down list outside the jungle.
    if champion in RUN_DOWN:
        return ["Ghost", "Flash"], (
            f"{champion} needs to reach and hold onto targets, which Ghost does better than "
            "any alternative; Flash covers the escapes it cannot.")

    # 3. Supports split by how they play the lane, not by damage type.
    if role == "support":
        if champion_class in ENGAGE_SUPPORT_CLASSES:
            return ["Ignite", "Flash"], (
                f"An engage support ({champion_class}) converts a successful engage into a "
                "kill, and Ignite is what closes it.")
        return ["Heal", "Flash"], (
            "A protective support gets more out of Heal, which saves the carry and adds "
            "movement speed to disengage with.")

    # 4. Marksmen outside the jungle, split on whether they can reposition.
    if champion_class == "Marksman":
        if champion in MOBILE_MARKSMEN:
            return ["Flash", "Barrier"], (
                f"{champion} already repositions with the kit, so the second slot is better "
                "spent surviving the burst that catches him mid-fight than on more movement.")
        return ["Ghost", "Flash"], (
            f"{champion} has no repositioning ability, so Ghost is how he holds attack range "
            "in a fight and escapes when he cannot.")

    # 5. Everything else.
    return list(DEFAULT), (
        "No specialised rule applies, so the standard laner pairing: Flash for safety and "
        "playmaking, Ignite for kill pressure.")


def resolved(champion: str, role: str, champion_class: str) -> tuple[list[dict], str]:
    """Frontend-shaped summoners: [{name, icon}], plus the reason."""
    names, reason = summoners_for(champion, role, champion_class)
    return [{"name": n, "icon": f"{_DD_SPELL}/{SPELLS[n]['dd']}.png"} for n in names], reason
