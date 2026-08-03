"""Canonical rune names, their art, and which captured names are real.

THE CATALOGUE IS GROUND TRUTH. data/wrmeta_runes.json holds the 53 runes
that exist in Wild Rift, each with local art. A rune name coming out of the
build extractor that is NOT in that catalogue is an EXTRACTION ERROR, not a
missing icon -- proven the hard way: 17 such names were chased down and art
was fetched for all of them before the owner confirmed that not one of those
runes is in the game. The vision model had been substituting names from its
League PC and legacy Wild Rift knowledge (Conditioning, Aftershock, Glacial
Augment, Sweet Tooth, Pathfinder, Press the Attack...) whenever it could not
read a rune icon, and 983 of 4,200 captured rune slots carry those inventions.

So this module does two things:

RENAMES. Three captured names are real runes under an older name, confirmed
by the owner: Giant Slayer is now Cut Down, Hunter - Genius was reworked into
Ingenious Hunter, and Press the Attack is Empowerment. Those are mapped.

VALIDATION. `is_known_rune` gates everything else. Unknown names are never
rendered as art and never counted in rune consensus; they are reported so the
extraction rework has a target list. Nothing is guessed: a name that could be
two different runes stays unknown.
"""
from __future__ import annotations

import functools
import json
import re
from pathlib import Path

_CATALOGUE = Path(__file__).resolve().parent.parent / "data" / "wrmeta_runes.json"

#: captured spelling -> the real rune it is. Only owner-confirmed renames and
#: unambiguous spelling variants; never a guess at what a misread meant.
_RENAMES = {
    "giant slayer": "Cut Down",
    "cutdown": "Cut Down",
    "hunter - genius": "Ingenious Hunter",
    "hunter-genius": "Ingenious Hunter",
    "hunter genius": "Ingenious Hunter",
    "press the attack": "Empowerment",
    "eyeball collection": "Eyeball Collector",
    "transcending": "Transcendence",
    "transcendent": "Transcendence",
    "transcendance": "Transcendence",
    "legend tenacity": "Legend: Tenacity",
    "legend alacrity": "Legend: Alacrity",
    "legend bloodline": "Legend: Bloodline",
}

#: canonical name -> art filename stem, where slugifying the name misses
_ART_STEMS = {
    "grasp of the undying": "grasp-of-undying",
    "eyeball collector": "eyeball-collection",
}


def _key(name: str) -> str:
    """Lowercase, normalise every dash variant, collapse whitespace."""
    s = (name or "").lower().replace("—", "-").replace("–", "-")
    s = re.sub(r"\s*-\s*", " - ", s)
    return re.sub(r"\s+", " ", s).strip()


@functools.lru_cache(maxsize=1)
def _catalogue() -> dict[str, str]:
    """{normalised name: canonical name} for every rune that exists."""
    if not _CATALOGUE.exists():
        return {}
    runes = json.loads(_CATALOGUE.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for r in runes:
        out[_key(r["name"])] = r["name"]
        out[_key(r["name"]).replace(":", "")] = r["name"]
    return out


def canonical_rune(name: str | None) -> str:
    """The spelling this rune should be counted and rendered under.

    Unknown names are returned unchanged (stripped) so callers can report
    them; use `is_known_rune` to tell the two apart."""
    if not name:
        return ""
    k = _key(name)
    if k in _RENAMES:
        return _RENAMES[k]
    flat = k.replace(" - ", "-")
    if flat in _RENAMES:
        return _RENAMES[flat]
    cat = _catalogue()
    return cat.get(k) or cat.get(k.replace(":", "")) or name.strip()


def is_known_rune(name: str | None) -> bool:
    """True when the name resolves to a rune that exists in Wild Rift."""
    if not name:
        return False
    return _key(canonical_rune(name)) in _catalogue()


def art_slug(name: str) -> str:
    """Filename stem for a canonical rune name."""
    k = _key(canonical_rune(name))
    if k in _ART_STEMS:
        return _ART_STEMS[k]
    return re.sub(r"[^a-z0-9]+", "-", k.replace("'", "").replace(":", " ")).strip("-")
