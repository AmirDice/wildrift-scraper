"""Summoner spells: chosen by the model, guaranteed by code.

These were a pure lookup for a while, and the reasoning was sound at the time --
the jungler takes Smite, the enchanter takes Heal -- so asking the model bought
nothing and cost a way for a good build to fail validation.

What changed is the input. The lookup is static: it reads the champion, the role
and the class, and nothing else. It cannot see that the enemy comp is four
point-and-click stuns, which is what makes Cleanse right, or that the lane opponent
is an assassin, which is what makes Barrier right. In counter mode we hand the
model the entire enemy team and it demonstrably uses it -- it found the one AP
anti-shield item in the pool unprompted. Summoner choice off a known comp is the
same kind of judgement, and the lookup was throwing that information away.

So the model picks, within limits it cannot violate:

  * Jungle: Smite is not a choice. It is forced into the loadout regardless of
    what the model returns, and the partner slot is restricted to Ghost or
    Flash.
  * Every other lane: free choice of two, except Smite, which is junglers-only.

The old table stays as the fallback. If the model returns something illegal and
the repair does not fix it, the build keeps its items and takes the lookup's
spells rather than failing -- which is the original objection, answered.
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


# Smite is the jungler's, and only the jungler's. Everything else is open.
JUNGLE_SPELL = "Smite"
# The partner slot in the jungle. Deliberately just these two: Ghost for the
# champions that win by running you down, Flash for everyone else. A jungler
# giving up one of those for Ignite is not a build the site should suggest.
JUNGLE_PARTNERS = ("Ghost", "Flash")

_CANON = {name.lower(): name for name in SPELLS}


def canon(name: object) -> str | None:
    """The pool's spelling of a name, or None if it is not a summoner spell."""
    return _CANON.get(str(name or "").strip().lower())


def icons_for(names: list[str]) -> list[dict]:
    """Frontend-shaped spells: [{name, icon}]."""
    return [{"name": n, "icon": f"{_DD_SPELL}/{SPELLS[n]['dd']}.png"} for n in names]


def enforce(picks: list[str], role: str) -> list[str] | None:
    """The model's picks, with the jungle rules imposed. None if unusable.

    Smite is not repaired by asking again: a jungle build without it is fixed
    here by inserting it, because there is no version of the answer where the
    jungler does not have Smite. What the model actually chooses in the jungle
    is the partner, and if that partner is not Ghost or Flash there is nothing
    to salvage, so the caller falls back to the lookup.
    """
    seen: list[str] = []
    for pick in picks or []:
        name = canon(pick)
        if name and name not in seen:
            seen.append(name)

    if (role or "").strip().lower() == "jungle":
        partner = next((n for n in seen if n in JUNGLE_PARTNERS), None)
        if partner is None:
            return None
        # Smite first or second is cosmetic; the lookup renders it second.
        return [partner, JUNGLE_SPELL]

    # Outside the jungle, Smite is not selectable at all.
    usable = [n for n in seen if n != JUNGLE_SPELL]
    return usable[:2] if len(usable) >= 2 else None


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
