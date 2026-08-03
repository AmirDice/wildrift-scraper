"""Accounts that advertise boosting services, and what to do with them.

Two separate reasons to act, and only one of them is about ethics:

STATISTICS. A boosting account is a strong player deliberately playing on a
weaker player's account, against opponents the account's rank attracts. Its
win rate measures a skill mismatch, not champion strength: the four accounts
found in EU sit at 71.9%, 92.0%, 93.8% and 94.5%. Feeding those into a
champion's average makes the tier list less accurate, so they are excluded
from every aggregate.

PROMOTION. The account NAME is the advertisement -- that is the whole point
of naming an account "Insta wrboost25". Rendering it on a public page is free
marketing for the service, and crowning it in the Hall of Fame is worse. The
leaderboard therefore keeps the row (ranks stay contiguous and the board stays
a faithful mirror) but replaces the name.

Detection is deliberately NARROW: a false positive publicly implies a real
player cheats. Only two signals qualify, both self-declared in the name:
  - "boost" anywhere ("Insta wrboost25", "Insta peaceboost")
  - a leading "insta" WORD ("Insta YushinWR"), the EU service prefix; the
    word boundary keeps "Instalock..." out, which is ordinary player slang.
Words like "carry" are NOT a signal: "LetMeCarry" (95 games) and "Support
Carry" are ordinary names, and flagging them would accuse real players.

Capture stays raw -- the scraper records exactly what the game shows. The
filtering happens here, at analysis and presentation time, so the raw record
remains auditable and the policy can change without re-scraping.
"""
from __future__ import annotations

import re

# self-declared advertising, nothing inferred from performance
_ADVERTISING = re.compile(r"boost|^insta\b", re.IGNORECASE)

#: what the leaderboard shows instead of the advertisement
HIDDEN_LABEL = "Name hidden"

HIDDEN_REASON = (
    "This account advertises a boosting service. Its name is hidden and its "
    "games are excluded from champion win rates and records."
)


def is_advertising_account(name: str | None) -> bool:
    """True when the account name itself advertises a boosting service."""
    if not name:
        return False
    return bool(_ADVERTISING.search(name.strip()))


def display_name(name: str | None) -> str:
    """The name to render publicly."""
    return HIDDEN_LABEL if is_advertising_account(name) else (name or "")
