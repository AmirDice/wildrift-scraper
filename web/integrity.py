"""Accounts that get special handling, and what each kind actually loses.

Two kinds, and they lose different things.

A BOOSTING ADVERT loses its NAME and nothing else. Naming an account
"Insta wrboost25" is the advertisement, and rendering it on a public page is
free marketing for the service -- worse still in the Hall of Fame. The
leaderboard keeps the row so ranks stay contiguous and the board stays a
faithful mirror; only the name is replaced.

Its win rate now COUNTS. It used to be excluded on the theory that a boosting
account is a strong player on a weaker player's account, so its number measures
a skill mismatch rather than the champion. The flaw is in the detection, not
the theory: the regex finds accounts that ADVERTISE, which is not the same as
accounts that are boosted. Plenty of the people advertising are simply good and
playing their own account, and excluding them assumed something about how the
account is played that a name cannot establish. Owner's call, 2026-08-06.

A PERMABANNED ACCOUNT is the reverse. It keeps its name and gains a visible
tag, because there the identity is the useful part and hiding it would rewrite
the board without saying so. What it loses is the credit for its number, in
every aggregate. That exclusion rests on a fact about the account rather than
an inference from its name.

Detection is deliberately NARROW. It costs an account its name on the page, so
a false positive erases a real player's identity from their own record. Only
two signals qualify, both self-declared in the name:
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

import json
import re
from functools import lru_cache
from pathlib import Path

def _fold(name: str | None) -> str:
    """Case- and punctuation-insensitive key, matching the player index. Shared
    by the advert exceptions and the ban list.

    Tolerates any input, not just str/None: these predicates get .apply()'d
    over pandas columns, where a missing name arrives as float NaN. `NaN or
    ""` is NaN (NaN is truthy), so the old str-only version crashed the whole
    loader on the first row with an unreadable name.
    """
    if not isinstance(name, str):
        return ""
    return "".join(c for c in name.casefold() if c.isalnum())


# self-declared advertising, nothing inferred from performance
_ADVERTISING = re.compile(r"boost|^insta\b", re.IGNORECASE)

#: what the leaderboard shows instead of the advertisement
HIDDEN_LABEL = "Name hidden"

HIDDEN_REASON = (
    "This account advertises a boosting service, so its name is hidden. Its "
    "games still count toward champion win rates and records."
)


_EXCEPTIONS_FILE = Path(__file__).resolve().parent.parent / "data" / "name_exceptions.json"


@lru_cache(maxsize=1)
def _name_shown_anyway() -> frozenset[str]:
    """Accounts the regex flags whose names the owner has chosen to show.

    The override lives beside the pattern rather than inside it. Widening the
    regex to let one account through would let others through with it, and the
    pattern's whole value is that it is narrow.
    """
    if not _EXCEPTIONS_FILE.exists():
        return frozenset()
    try:
        raw = json.loads(_EXCEPTIONS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return frozenset()
    return frozenset(_fold(e.get("name")) for e in (raw.get("showName") or [])
                     if _fold(e.get("name")))


def is_advertising_account(name: str | None) -> bool:
    """True when the account name itself advertises a boosting service.

    False for an account on the shown-anyway list, so callers that hide names
    and callers that reason about adverts agree: an exempted account is simply
    not treated as an advert anywhere.
    """
    if not isinstance(name, str) or not name:
        return False
    if not _ADVERTISING.search(name.strip()):
        return False
    return _fold(name) not in _name_shown_anyway()


def display_name(name: str | None) -> str:
    """The name to render publicly."""
    return HIDDEN_LABEL if is_advertising_account(name) else (name or "")


# --------------------------------------------------------------------------
# permabanned accounts
# --------------------------------------------------------------------------
#
# Detection is a LIST, not a heuristic. A ban is a fact about an account that
# only Riot and a human looking at the game can establish; nothing in a win
# rate proves it. Inferring it from the numbers would accuse real players of
# cheating for the crime of being good, which is the same mistake the narrow
# advertising regex exists to avoid.
#
# These accounts do keep their leaderboard row and their name. Hiding a banned
# account would silently rewrite the board, and the honest thing is to show the
# rank the game showed and say why the number beside it is not counted.

_BANNED_FILE = Path(__file__).resolve().parent.parent / "data" / "banned_players.json"

BANNED_LABEL = "Permabanned"

BANNED_REASON = (
    "This account has been permanently banned. Its row is shown as the game "
    "showed it, but its games are excluded from champion win rates and records."
)


@lru_cache(maxsize=1)
def _banned() -> dict[str, dict]:
    if not _BANNED_FILE.exists():
        return {}
    try:
        raw = json.loads(_BANNED_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    out = {}
    for entry in raw.get("players") or []:
        key = _fold(entry.get("name"))
        if key:
            out[key] = entry
    return out


def is_banned_account(name: str | None) -> bool:
    """True when this leaderboard name belongs to a permabanned account.

    Pass the name from the LEADERBOARD ROW (extracted.csv), never the one from
    the popup card. A popup that fails to dismiss between taps reports the
    PREVIOUS player's card, and one live session put a banned name on two
    innocent players' rows that way.
    """
    return _fold(name) in _banned()


def ban_reason(name: str | None) -> str | None:
    """Why this account is on the list ('wintrading', 'banned'), or None."""
    entry = _banned().get(_fold(name))
    return (entry or {}).get("reason")


def eligible_for_title(name: str | None) -> bool:
    """May this account be publicly CROWNED -- best player, a Hall of Fame
    record, any named showcase?

    Separate from counts_toward_aggregates on purpose, because the two answer
    different questions. An advert's games count toward champion averages (an
    average carries no name), but a title IS a name: "Insta wrboost25 leads
    the EU sample" is the module's own worst case, and the day adverts started
    counting toward aggregates, two champion spotlights and the Hall of Fame
    mastery record did exactly that.

    An account on the shown-anyway exception list is eligible: the owner chose
    to display that name, and a name fit for the board is fit for a title.
    """
    return not (is_advertising_account(name) or is_banned_account(name))


def counts_toward_aggregates(name: str | None) -> bool:
    """The single question every aggregate should ask about a row.

    Only a ban disqualifies a number. An advertising name says something about
    how the account is MARKETED, not about how it is played, so it no longer
    costs the account its statistics -- just its name on the page.
    """
    return not is_banned_account(name)
