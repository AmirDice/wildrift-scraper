"""Champion -> Wild Rift role mapping (STRICT single-role).

Wild Rift's five lane roles:
    Baron   - solo top lane
    Jungle  - the jungle role
    Mid     - mid lane
    Dragon  - bot lane carry / ADC
    Support - bot lane support

This file uses STRICT single-role assignments per the project owner's spec:
  - explicit Support / Jungle / Mid / Dragon lists below
  - everyone else falls back to Baron

Order of checks matters: Support -> Jungle -> Mid -> Dragon -> Baron.
A marksman explicitly placed in another role (e.g. Senna in Support,
Kindred / Nilah / Graves in Jungle) is caught by the earlier check and
never falls through to Dragon.
"""
from __future__ import annotations

# Canonical role labels (used as filter values everywhere).
ROLES: tuple[str, ...] = ("Baron", "Jungle", "Mid", "Dragon", "Support")


_SUPPORT: frozenset[str] = frozenset({
    "Alistar", "Bard", "Blitzcrank", "Braum", "Janna", "Karma", "Leona",
    "Lulu", "Maokai", "Milio", "Nami", "Nautilus", "Pyke", "Rakan",
    "Rell", "Senna", "Seraphine", "Sona", "Soraka", "Thresh", "Yuumi", "Zilean",
})

_JUNGLE: frozenset[str] = frozenset({
    "Amumu", "Diana", "Ekko", "Evelynn", "Fiddlesticks", "Fizz", "Gragas",
    "Graves", "Hecarim", "Jarvan IV", "Kayn", "Kha'Zix", "Kindred", "Lee Sin",
    "Lillia", "Master Yi", "Nidalee", "Nilah", "Nocturne", "Nunu & Willump",
    "Olaf", "Pantheon", "Rammus", "Rengar", "Shyvana", "Talon",
    "Vi", "Viego", "Warwick", "Xin Zhao",
})

_MID: frozenset[str] = frozenset({
    "Ahri", "Akali", "Akshan", "Annie", "Aurelion Sol", "Aurora", "Brand",
    "Galio", "Heimerdinger", "Kassadin", "Katarina", "Kennen", "Lissandra",
    "Lux", "Mel", "Morgana", "Norra", "Orianna", "Ryze", "Swain", "Syndra",
    "Taliyah", "Twisted Fate", "Veigar", "Vel'Koz", "Vex", "Viktor",
    "Vladimir", "Yasuo", "Zed", "Ziggs", "Zoe", "Zyra",
})

_DRAGON: frozenset[str] = frozenset({
    # Standard bot-lane ADCs / marksmen.
    "Aphelios", "Ashe", "Caitlyn", "Corki", "Draven", "Ezreal", "Jhin",
    "Jinx", "Kai'Sa", "Kalista", "Kog'Maw", "Lucian", "Miss Fortune",
    "Samira", "Sivir", "Smolder", "Tristana", "Twitch", "Varus", "Vayne",
    "Xayah", "Zeri",
})


def roles_for(champion: str) -> tuple[str, ...]:
    """Return the (single) role this champion is assigned to.

    Checks in order Support -> Jungle -> Mid -> Dragon -> Baron, so a
    marksman explicitly placed in another role (e.g. Kindred in Jungle,
    Senna in Support) is caught earlier and never falls to Dragon.
    Anything unmatched lands in Baron (top lane).
    """
    if champion in _SUPPORT:
        return ("Support",)
    if champion in _JUNGLE:
        return ("Jungle",)
    if champion in _MID:
        return ("Mid",)
    if champion in _DRAGON:
        return ("Dragon",)
    return ("Baron",)


def primary_role(champion: str) -> str:
    """The first (only, here) role for a champion."""
    return roles_for(champion)[0]


def champions_in_role(role: str) -> set[str]:
    """All champions assigned to `role`."""
    if role == "Support":
        return set(_SUPPORT)
    if role == "Jungle":
        return set(_JUNGLE)
    if role == "Mid":
        return set(_MID)
    if role == "Dragon":
        return set(_DRAGON)
    if role == "Baron":
        # Everything we know about that didn't land in another bucket.
        from src.champions import CHAMPIONS
        return set(CHAMPIONS) - _SUPPORT - _JUNGLE - _MID - _DRAGON
    return set()
