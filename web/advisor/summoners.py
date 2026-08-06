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
import re
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

# Whether the kit can reposition on its own. Used only to NUDGE -- a champion
# with no dash is told to consider Flash and Ghost seriously, because those two
# are the only substitutes for mobility it does not have.
#
# The signal is approximate and knowingly so. A keyword scan over ability text
# misses Ezreal's Arcane Shift and Vayne's Tumble outright, which is why the
# curated marksman list has to be consulted as well, and it still cannot see
# Malphite's ultimate. Getting this right across the roster wants the same
# treatment `rangeProfile` got: classified per champion, not pattern-matched.
# Until then a miss costs a nudge, not a wrong build.
_MOBILITY_TEXT = re.compile(
    r"\b(dash(?:es|ing)?|blink(?:s|ing)?|leaps?|lunges?|vaults?|teleports?|"
    r"flies|flying|jumps?|charges? (?:toward|at|forward))\b", re.I)


def has_mobility(champion: str, abilities_text: str = "") -> bool:
    """Whether this kit can reposition without a summoner spell."""
    if champion in MOBILE_MARKSMEN or champion in RUN_DOWN:
        return True
    return bool(_MOBILITY_TEXT.search(abilities_text or ""))


def canon(name: object) -> str | None:
    """The pool's spelling of a name, or None if it is not a summoner spell."""
    return _CANON.get(str(name or "").strip().lower())


def icons_for(names: list[str]) -> list[dict]:
    """Frontend-shaped spells: [{name, icon}]."""
    return [{"name": n, "icon": f"{_DD_SPELL}/{SPELLS[n]['dd']}.png"} for n in names]


# Heal is a SUPPORT spell. It heals the ally it is cast on as well as the
# caster, and that second half is the whole reason to bring it -- a solo laner
# gets a worse Barrier. The model gave Jinx Heal on a standard build, which is
# what made this explicit rather than assumed.
SUPPORT_ONLY = frozenset({"Heal"})

# With no NAMED enemy team the studio does not go blind: the prompt tells the
# model to assume the typical ranked comp (tank/bruiser top, bruiser/tank/AD
# assassin jungle, mage or assassin mid, marksman bot, enchanter or tank
# support -- prompt.UNKNOWN_ENEMY_BLOCK). The pool is what that comp can
# justify. Flash, Ghost, Exhaust and Cleanse answer things every typical comp
# has: escapes to make, targets to reach, a carry to blunt, some crowd
# control. Barrier is in because the typical comp GUARANTEES one serious
# magic/burst threat mid, so shielding the spike is a read of the assumed
# comp, not a blind bet. Ignite stays out: it is a bet on a specific kill
# lane, and an archetype cannot tell you the lane is killable. Heal is
# support-only everywhere (see SUPPORT_ONLY).
STUDIO_POOL = frozenset({"Flash", "Exhaust", "Ghost", "Cleanse", "Barrier"})


def allowed_pool(role: str, enemies_known: bool) -> frozenset[str]:
    """Which spells this request may choose from, before the jungle rule."""
    pool = set(SPELLS) if enemies_known else set(STUDIO_POOL)
    if (role or "").strip().lower() != "support":
        pool -= SUPPORT_ONLY
    else:
        pool |= SUPPORT_ONLY          # a support keeps Heal in either mode
    pool.discard(JUNGLE_SPELL)        # Smite is imposed, never chosen
    return frozenset(pool)


def enforce(picks: list[str], role: str, enemies_known: bool = True) -> list[str] | None:
    """The model's picks, with the rules imposed. None if unusable.

    Smite is not repaired by asking again: a jungle build without it is fixed
    here by inserting it, because there is no version of the answer where the
    jungler does not have Smite. That is keyed on the REQUESTED role, so a
    champion who is not normally a jungler still gets Smite when someone asks
    for a jungle build.

    Everything else is filtered against `allowed_pool` before the pick is
    accepted, so a spell the request should never offer cannot arrive by the
    model returning it anyway.
    """
    is_jungle = (role or "").strip().lower() == "jungle"
    pool = allowed_pool(role, enemies_known)

    seen: list[str] = []
    for pick in picks or []:
        name = canon(pick)
        if name and name not in seen:
            seen.append(name)

    if is_jungle:
        # The partner must be legal for the request as well as a jungle partner:
        # Ghost and Flash are both in every pool, so this is belt and braces.
        partner = next((n for n in seen if n in JUNGLE_PARTNERS and n in pool), None)
        if partner is None:
            return None
        # Smite first or second is cosmetic; the lookup renders it second.
        return [partner, JUNGLE_SPELL]

    usable = [n for n in seen if n in pool]
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


# Preference order when the lookup's answer is not legal for this request and a
# slot has to be filled. Flash first because it is never wrong; Heal last
# because it only reaches this list for a support.
_FALLBACK_ORDER = ("Flash", "Ghost", "Exhaust", "Cleanse", "Barrier", "Ignite", "Heal")


def _legalise(names: list[str], pool: frozenset[str]) -> list[str]:
    """Two spells from `pool`, keeping the lookup's answer where it is legal.

    The lookup predates the pool rules and can return spells this request may
    not offer -- Barrier to a mobile marksman, Heal to a support-shaped kit --
    so filtering it is not optional. Falling back must not become a way around
    the rule the model is held to.
    """
    out = [n for n in names if n in pool]
    for candidate in _FALLBACK_ORDER:
        if len(out) >= 2:
            break
        if candidate in pool and candidate not in out:
            out.append(candidate)
    return out[:2]


def resolved(champion: str, role: str, champion_class: str,
             enemies_known: bool = True) -> tuple[list[dict], str]:
    """Frontend-shaped summoners: [{name, icon}], plus the reason."""
    names, reason = summoners_for(champion, role, champion_class)
    legal = _legalise(names, allowed_pool(role, enemies_known))
    if (role or "").strip().lower() == "jungle":
        partner = next((n for n in legal if n in JUNGLE_PARTNERS), "Flash")
        legal = [partner, JUNGLE_SPELL]
    if legal != names:
        reason = (f"{' and '.join(legal)}: the default pairing for this kit, kept within "
                  f"the spells this request may offer.")
    return [{"name": n, "icon": f"{_DD_SPELL}/{SPELLS[n]['dd']}.png"} for n in legal], reason
