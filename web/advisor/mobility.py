"""Whether a champion can move itself a long way, quickly.

`dash` decides who counts as a diver, how much backline access a composition
has, and therefore the dive and backline numbers the whole draft ranker reads.
It was a keyword scan over the champion's abilities -- dash, blink, leap,
lunge, vault, teleport, charge -- and it tagged 96 of 141 champions.

Unlike `cc`, most of that is correct: Wild Rift champions really are mobile.
The failures are narrow and have exactly two causes, both visible in the data:

  "charge" is usually not a movement. It is a stored ability charge ("Bandage
  Toss charges are stored every 13 seconds"), or part of an ability's NAME
  (Nautilus's Depth Charge, Viktor's Turbocharge). Only "charges toward
  something" is a gap closer.

  A dash in the text is not always the champion's own. Jinx's Flame Chompers
  reads "interrupting their dashes and rooting them", which made the most
  famously immobile marksman in the game register as mobile -- and being
  immobile is exactly what the draft ranker needs to know about her, because
  it decides whether she can survive a dive.

Same shape as hardcc.py, and for the same reasons: matched per ability so a
word cannot leak across skills, on TEXT with the champion's own ability names
blanked, and with a guard for effects that belong to somebody else.
"""
from __future__ import annotations

import re

#: Unambiguous self-movement. These words do not mean anything else.
_MOVE = re.compile(
    r"\b(dash\w*|blink\w*|leap\w*|lunge\w*|vault\w*|teleport\w*"
    r"|somersault\w*|hops?\b|hopping|rolls?\b|rolling|pounce\w*|warp\w*"
    # Champions describe the same movement in their own vocabulary:
    # Alistar "rams a target", Poppy "tackles an enemy", Kindred "rolls in a
    # target direction", Evelynn "warping backwards", Corki "flies a short
    # distance". A keyword list assembled from the word "dash" alone reads
    # only the champions who happen to share its author\'s vocabulary.
    r"|rams?\b|ramming|tackle\w*"
    # Not a bare "flies": a bomb flies too. The distance phrase is what
    # makes it the champion moving rather than a projectile.
    r"|fl(?:y|ies|ying)\s+(?:a\s+)?(?:short|long|forward|toward|in\b)"
    # "charges to the target area" is Malphite's ultimate; "charges are
    # stored" is a cooldown mechanic. The preposition is the difference.
    r"|charg(?:es|ing)\s+(?:to|toward|towards|into|at|forward|through|in)\b"
    r"|(?:leaps?|jumps?|lunges?|propels?|launches?|flings?)\s+(?:himself|herself|itself|themselves)"
    r"|shadowstep\w*|blink)", re.I)

#: The movement has to be the CHAMPION'S. Jinx interrupts dashes, she does not
#: have one, and Sivir's spell shield text mentions enemy movement too.
_NOT_MINE = re.compile(
    r"\b(their|enemy|enemies|enemy's|opponents?|opposing|allied|ally|allies"
    r"|interrupt\w*|cancel\w*|block\w*|stops?\b|prevent\w*|immune"
    # A pet moving is not the champion moving. Annie reads "ordering
    # Tibbers to pounce on a target" and Kindred "directs Wolf to pounce",
    # and both registered as mobile champions on the strength of it.
    r"|ordering|orders|commands?|directs?|summon\w*)", re.I)

#: How far back the disqualifier may sit. Short, and inside one ability.
_WINDOW = 40


def _clause(text: str, at: int) -> str:
    cut = max(text.rfind(". ", 0, at), text.rfind(" : ", 0, at))
    return text[cut + 1:at] if cut >= 0 else text[:at]


def ability_has_dash(text: str) -> bool:
    if not text:
        return False
    for m in _MOVE.finditer(text):
        # Scoped to the SENTENCE, not a character window. A fixed window wide
        # enough to catch "interrupting their dashes" also reached back over a
        # full stop -- Aatrox reads "physical vamp against enemy champions.
        # Active : Dashes forward", and the word "enemy" in the previous
        # sentence deleted his dash.
        if _NOT_MINE.search(_clause(text, m.start())[-_WINDOW:]):
            continue
        return True
    return False


def dash_abilities(abilities, champion: str = "") -> list[str]:
    """Names of the abilities that move this champion a distance."""
    names = [a.get("name") or "" for a in abilities or [] if isinstance(a, dict)]
    # Only names long enough, or multi-word enough, to be unambiguous. Kha'Zix
    # has an ability CALLED "Leap", and blanking it turned "Leaps to target
    # area" into " s to target area" -- deleting the very verb being looked
    # for. "Depth Charge" and "Turbocharge" still go, which is the point.
    quoted = sorted((n for n in names if " " in n or len(n) >= 8),
                    key=len, reverse=True)
    out = []
    for a in abilities or []:
        if not isinstance(a, dict):
            continue
        text = a.get("text") or ""
        # Blanking the champion's own skill names is what stops "Depth Charge"
        # and "Turbocharge" reading as movement.
        for n in quoted:
            text = text.replace(n, " ")
        if champion:
            text = text.replace(champion, " ")
        if ability_has_dash(text):
            out.append(a.get("name") or "")
    return out


def has_dash(abilities, champion: str = "") -> bool:
    return bool(dash_abilities(abilities, champion))
