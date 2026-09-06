"""Hard crowd control, derived from ability text.

Hard crowd control is the part of a composition that decides whether tenacity,
Mercury's Treads or a cleanse is worth a slot, and whether a pick that walks
through lockdown is worth a tier of meta strength. Both of those questions are
answered by a COUNT of enemies who can actually stop you acting, so the count
has to be right.

It was not. The same regex lived in two files -- the advisor's threat model and
the overlay's bundle exporter -- and tagged 97 of 141 champions, which makes an
average five-stack read as "three sources of lockdown" no matter who is in it.
A tenacity rune went onto a build whose only real crowd control was Sona.

Four things were wrong, and all four are fixed here:

  * The negative filter looked back 90 characters through the champion's
    abilities CONCATENATED, so a word from a different ability could veto a
    real effect. Pantheon's "stunning" was thrown away by the word "reduced"
    in his passive's monster-damage clause.
  * It vetoed on "ally", which is right for an effect an ally applies and
    wrong for Lulu, whose ultimate enlarges an ALLY and knocks up ENEMIES.
  * `knock\\s?up` never matched the verb forms the tooltips actually use --
    "knocks up", "knocking the target back" -- so Fizz, Wukong, Jayce and
    Shyvana all read as having no crowd control.
  * Ability NAMES were matched along with their text, so Kha'Zix was a
    crowd-control threat on the strength of "Taste Their Fear".

The vocabulary also simply missed effects: sleep (Zoe, Lillia), and the pulls
and launches that are Orianna's, Diana's, Darius's and Mordekaiser's entire
reason for existing.

What this deliberately does NOT count is slows. A slow is real and it belongs
in a threat profile, but it is not what tenacity is for, and counting it is how
`cc` ended up describing two thirds of the roster.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent


def _overrides() -> tuple[dict, dict]:
    """Owner corrections, for tooltips the scrape truncated.

    Three of them at the time of writing, and every one is a sentence that
    stops mid-clause exactly where the crowd control was. Kept as data rather
    than as more regex, because no pattern can read text that is absent.
    """
    path = _ROOT / "data" / "hard_cc_overrides.json"
    if not path.exists():
        return {}, {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, {}
    return raw.get("add") or {}, raw.get("remove") or {}


_ADD, _REMOVE = _overrides()

#: Words that name an effect which stops a champion acting. Matching one of
#: these inside a single ability's text is enough on its own.
_STRONG = re.compile(
    r"\b("
    r"stun\w*"
    r"|roots?\b|rooted|rooting"
    r"|snar\w*"
    r"|taunt\w*"
    r"|charm\w*"
    r"|suppress\w*"
    r"|immobiliz\w*"
    r"|airborne"
    r"|asleep|sleeps?\b|sleeping|drows\w*|slumber\w*"
    r"|stasis"
    r"|entangl\w*"
    # Amumu's ultimate is the reason. It "entangles surrounding enemy units"
    # and renders them "unable to attack or move", and neither phrase used a
    # word this knew -- so the most famous teamfight lockdown in the game
    # counted for nothing and a poke comp out-scored a wombo comp on crowd
    # control.
    r"|unable to (?:attack|move|act)"
    r"|polymorph\w*"
    r"|silenc\w*"
    # `flee\w*` is gone: it matched Sivir's "Fleet of Foot". Fear covers the
    # effect anyway.
    r"|fears?\b|feared|fearing|terrif\w*"
    # "knocks up", "knocking the target back", "Knocks a target and enemies
    # near them backwards". The verb and its particle run up to six words
    # apart in real tooltips, which is why the old fixed `knock\s?up` matched
    # almost none of them.
    r"|knock\w*(?:\s+\w+){0,6}\s+(?:up|back\w*|aside|away|airborne)\b"
    # "into the air" only. Plain "in the air" is where a thrown dagger spends
    # its travel time, and it made Katarina a lockdown threat.
    r"|into\s+the\s+air"
    r")", re.I)

#: Verbs that are crowd control only when they act on somebody. "Launches a
#: fish" is Fizz's ultimate in flight; "launching nearby enemies toward the
#: Ball" is Orianna's. Requiring a target word nearby separates them.
#: `drag\w*` is spelled out because the stem matched Smolder's "Dragon
#: Practice", and `toss` is absent because the only tosses that are crowd
#: control say "into the air" and are caught above -- the rest are Talon's
#: daggers.
_DISPLACE = re.compile(
    r"\b(pull\w*|drags?\b|dragged|dragging|launch\w*|lift\w*|yank\w*"
    r"|fling\w*|haul\w*|draws? in|reels? in)", re.I)

#: "them" earns its place here despite being a common word: Nautilus hooks by
#: "pulling them and Nautilus together", and without it his hook -- the entire
#: reason anyone picks him -- was not crowd control. The window this is
#: searched over is 25 characters, which is what keeps it honest.
_TARGET = re.compile(
    r"\b(enem\w*|opponent\w*|target\w*|foes?\b|victim\w*"
    # NOT the "champions" inside "Non-champions", which otherwise cancels the
    # minion veto below by looking like the very target it is there to deny.
    r"|(?<!non-)(?<!non)champions?\b|them\b|they\b)", re.I)

#: An effect that only moves minions is not an effect on you. Graves' passive
#: says "Non-champions struck by multiple bullets are knock back slightly" and
#: it made him a lockdown threat.
#:
#: Checked over the SENTENCE the effect is in rather than a character window.
#: A window wide enough to reach "Non-champions" also reached back into the
#: previous sentence -- "Bullets cannot pass through enemy units." -- and the
#: word "enemy" there cancelled the veto, which is precisely the confusion
#: sentence scoping exists to prevent.
_MINIONS_ONLY = re.compile(r"\b(non-?champion\w*|minions?\b|monsters?\b)", re.I)

#: The effect must be one this champion APPLIES, not one it removes, resists or
#: shortens. Kept deliberately narrow and checked over a short window inside a
#: single ability, because the broad version is what silently deleted
#: Pantheon's stun.
_NOT_MINE = re.compile(
    r"\b(immune|immunity|cleanse\w*|tenacity|cannot be|shrug\w*|unstoppable"
    r"|resistant to|resists?\b|removes? all|duration (?:is )?reduc\w*"
    r"|reduc\w* the duration)", re.I)

#: How far back inside one ability a disqualifier can reach. Long enough for
#: "removes all crowd control effects", short enough that it cannot cross a
#: sentence boundary into an unrelated clause.
_VETO_WINDOW = 45

#: How far after a displacement verb its object may sit. Short on purpose:
#: Kai'Sa "Launches 6 missiles that split evenly among nearby enemies" put a
#: target word 45 characters out, Orianna's "launching nearby enemies" puts one
#: at 10, and the gap between those two numbers is the whole discrimination.
_TARGET_WINDOW = 25

#: An effect an ALLY applies is not this champion's. Kai'Sa's passive reads
#: "Nearby allies apply 1 stack to champions they Immobilize" and counted her
#: as lockdown. But Lulu's ultimate "Enlarges an ally champion, knocking nearby
#: enemies into the air" is hers, and a flat ally veto deleted it -- which is
#: why an ally nearby only disqualifies an effect that does not go on to name
#: who it hits.
_ALLY = re.compile(r"\ball(?:y|ies|ied)\b", re.I)
_ALLY_WINDOW = 60

#: Passive voice puts the victim BEFORE the verb: Aatrox's chain says "they
#: will be dragged back to the center", and looking only forward for a target
#: missed it. Checked narrowly -- the auxiliary has to sit right against the
#: verb -- because a bare backward search would take "damage to enemies" from
#: the front of the same sentence as consent for anything after it.
_PASSIVE = re.compile(r"\b(?:are|is|was|were|be|being|gets?)\s+(?:\w+\s+){0,1}$", re.I)
_PASSIVE_WINDOW = 30
_BACK_TARGET_WINDOW = 55


def _clause(text: str, at: int) -> str:
    """The text from the start of this sentence up to the match."""
    cut = max(text.rfind(". ", 0, at), text.rfind(" : ", 0, at))
    return text[cut + 1:at] if cut >= 0 else text[:at]


def _vetoed(text: str, end: int, at: int) -> bool:
    if _NOT_MINE.search(text[max(0, at - _VETO_WINDOW):at]):
        return True
    clause = _clause(text, at)
    if _MINIONS_ONLY.search(clause) and not _TARGET.search(clause):
        return True
    if _ALLY.search(text[max(0, at - _ALLY_WINDOW):at]):
        return not _TARGET.search(text[end:end + _TARGET_WINDOW])
    return False


def ability_has_hard_cc(text: str, champion: str = "") -> bool:
    """Whether one ability's text describes hard crowd control it applies.

    `champion` catches self-displacement. Graves' ultimate "knocks Graves back
    from recoil", which is recoil, not crowd control -- and the champion's own
    name sitting inside the matched span is the tell.
    """
    if not text:
        return False
    for m in _STRONG.finditer(text):
        if champion and champion.lower() in m.group().lower():
            continue
        if not _vetoed(text, m.end(), m.start()):
            return True
    for m in _DISPLACE.finditer(text):
        if _vetoed(text, m.end(), m.start()):
            continue
        if _TARGET.search(text[m.end():m.end() + _TARGET_WINDOW]):
            return True
        at = m.start()
        if _PASSIVE.search(text[max(0, at - _PASSIVE_WINDOW):at]):
            before = _clause(text, at)[-_BACK_TARGET_WINDOW:]
            if _TARGET.search(before):
                return True
    return False


def hard_cc_abilities(abilities, champion: str = "") -> list[str]:
    """Names of the abilities that apply hard crowd control.

    Matched per ability and on TEXT ONLY. Both matter: per ability so a veto
    cannot reach across into an unrelated skill, and text-only so an ability
    called "Taste Their Fear" is not mistaken for a fear.

    `champion` is optional and only enables the override lookup; without it
    the answer is whatever the tooltips say, which is what the exporter wants
    when it is checking whether an override is still needed.
    """
    names = [a.get("name") or "" for a in abilities or [] if isinstance(a, dict)]
    # Tooltips quote the champion's OTHER abilities by name, so matching text
    # alone was not enough: Kha'Zix's Evolved Reaper Claws mentions "Taste
    # Their Fear" twice and he scored as a fear threat on it. Blanking his own
    # skill names leaves only what the ability actually does.
    quoted = sorted((n for n in names if len(n) > 3), key=len, reverse=True)
    out = []
    for a in abilities or []:
        if not isinstance(a, dict):
            continue
        text = a.get("text") or ""
        for n in quoted:
            text = text.replace(n, " ")
        if ability_has_hard_cc(text, champion):
            out.append(a.get("name") or "")
    if champion:
        drop = set(_REMOVE.get(champion) or [])
        if drop:
            out = [n for n in out if n not in drop]
        for extra in _ADD.get(champion) or []:
            if extra not in out:
                out.append(extra)
    return out


def has_hard_cc(abilities, champion: str = "") -> bool:
    return bool(hard_cc_abilities(abilities, champion))


def hard_cc_depth(abilities, champion: str = "") -> int:
    """How MANY of a champion's abilities lock somebody down.

    Presence alone put Sona -- one stun, on her ultimate -- level with Alistar,
    who has three and can land them on demand. The count is what separates a
    composition that happens to contain crowd control from one built around it.
    """
    return len(hard_cc_abilities(abilities, champion))
