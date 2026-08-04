"""Canonicalise the ranked tier read off a player's profile.

Two things go wrong with the tier and neither is the reader's fault.

THE POPUP HAS NOT FINISHED LOADING. The card animates in, and a screenshot
taken a beat early catches it before the tier line renders. 71 of 686 captured
players came back with no tier at all. The profile's STATS page prints the
same tier, and we already capture it, so a missing popup tier is answered from
there rather than lost.

THE GAME SHOWS THE WRONG LADDER. A player with no current ranked placement
displays their Adventure-mode rank in the same slot, and it reads exactly like
a ranked tier. That produced Iron IV and Gold II on champion leaderboards --
26 of 686 -- which is not credible: these are the top 50 players on a
champion, and nobody below Diamond is on that list. A tier below Diamond is
therefore evidence the game showed a DIFFERENT ladder, not evidence the player
is Gold, so it is dropped rather than published.

Both failures used to be invisible, because a wrong tier looks exactly like a
right one on the page.
"""
from __future__ import annotations

import re

#: Ranked ladder, low to high. Index is the comparison.
LADDER = [
    "Iron", "Bronze", "Silver", "Gold", "Platinum",
    "Emerald", "Diamond", "Master", "Grandmaster", "Challenger", "Sovereign",
]

#: The lowest tier that can credibly appear on a champion's top 50.
FLOOR = LADDER.index("Diamond")

_ROMAN = ("I", "II", "III", "IV", "V")


def _base_and_division(text: str) -> tuple[str | None, str | None, bool]:
    """(ladder name, roman division, is_legendary) for a cleaned tier string."""
    legendary = False
    if re.match(r"(?i)^legendary\b", text):
        # The Legendary queue runs its own high-elo ladder ("Legendary
        # Grandmaster IV", "Legendary Commander II"). Never floor those: they
        # sit above the main ladder, whatever name follows.
        legendary = True
        text = re.sub(r"(?i)^legendary\s+", "", text)
    parts = text.split()
    if not parts:
        return None, None, legendary
    division = parts[-1].upper() if parts[-1].upper() in _ROMAN else None
    name = " ".join(parts[:-1] if division else parts).strip()
    for known in LADDER:
        if name.lower() == known.lower():
            return known, division, legendary
    return (name or None) if legendary else None, division, legendary


def canonical_tier(raw: str | None) -> str | None:
    """A trustworthy tier string, or None when the reading cannot be trusted.

    None means "we do not know", which the site renders as nothing at all --
    an honest blank beats a confident Gold II that is really an Adventure
    rank.
    """
    if not raw:
        return None
    text = str(raw).strip()
    # High tiers carry a title after a colon ("Challenger: Peerless Blade"),
    # and a narrow crop truncates it to "Challenger: Peer...". The title is
    # decoration; the tier is what precedes the colon. Without this the
    # truncated forms fail to parse and the floor below would discard real
    # Challengers.
    text = text.split(":", 1)[0].strip()
    text = re.sub(r"[.…]+$", "", text).strip()
    text = re.sub(r"\s+", " ", text)
    if not text:
        return None

    name, division, legendary = _base_and_division(text)
    if not name:
        # A bare division ("II") names no ladder at all: unreadable, not low.
        return None
    if legendary:
        return f"Legendary {name}" + (f" {division}" if division else "")
    if LADDER.index(name) < FLOOR:
        return None
    return f"{name} {division}" if division else name


def resolve_tier(popup_tier: str | None, *stats_tiers: str | None) -> str | None:
    """The tier for a player: the popup's, else whatever the stats pages saw.

    The popup is preferred because it is the card built to show the rank; the
    stats pages are the fallback for when it had not painted yet. Each source
    is canonicalised on its own, so a stats page showing an Adventure rank
    cannot smuggle one in behind a blank popup.
    """
    best = canonical_tier(popup_tier)
    if best:
        return best
    for candidate in stats_tiers:
        found = canonical_tier(candidate)
        if found:
            return found
    return None
