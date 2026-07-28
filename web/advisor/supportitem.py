"""The free support item, which is not optional and not a recommendation.

A support starts the game by buying one of two 0-gold items and never sells it.
It is the role's income: Soulcast pays out 75 gold a minute and stacks adaptive
stats up to 250 Health and 20 AD / 40 AP. A support build that does not open
with one is not a stylistic choice, it is a build that has given up its gold
income for the whole game.

The model was never told any of this, so it never bought one. Every support
build the site produced was missing the single most important item in the role.

Which of the two is a real decision, so the model still makes it:

  * Bulwark of the Mountain -- 175 Health and 10 ability haste. The tanky one,
    for supports who take the damage themselves.
  * Black Mist Scythe -- 10 ability haste plus Versatile, an adaptive 14 AD or
    28 AP. The damage one, for supports who convert gold into threat.

But the presence and the position are guaranteed here rather than requested,
for the same reason Smite is: there is no version of a support build where this
slot is spent on something else, so a wrong answer is corrected instead of
being sent back to the model.
"""
from __future__ import annotations

# The two 0-gold support items. Both carry Soulcast; they differ in the stats
# bolted to it.
TANKY = "bulwark-of-the-mountain"
DAMAGE = "black-mist-scythe"
SUPPORT_ITEMS: frozenset[str] = frozenset({TANKY, DAMAGE})

# Classes that want the Health rather than the adaptive damage. An engage
# support is the one being hit, so 175 Health beats 14 AD.
_TANKY_CLASSES = frozenset({"Tank", "Bruiser", "Fighter"})


def is_support(role: str) -> bool:
    return (role or "").strip().lower() == "support"


def default_for(champion_class: str) -> str:
    """The support item to fall back on when the model did not choose one."""
    return TANKY if (champion_class or "").strip() in _TANKY_CLASSES else DAMAGE


def enforce(items: list[str], role: str, champion_class: str) -> tuple[list[str], bool]:
    """The item list with the support-item rule applied.

    Returns (items, changed). The list keeps its length: a support build is
    still five items plus boots, one of which is the support item, because that
    is what fits in the inventory.

    Outside the support role the item is removed rather than reordered. It is
    the support's income, and a solo laner holding one is not a spicy build --
    it is a slot spent on stats they will never stack.
    """
    original = list(items or [])
    present = [slug for slug in original if slug in SUPPORT_ITEMS]

    if not is_support(role):
        cleaned = [slug for slug in original if slug not in SUPPORT_ITEMS]
        return cleaned, cleaned != original

    # Keep the model's choice when it made one, otherwise pick by class. Two
    # support items is never right, so only the first survives.
    chosen = present[0] if present else default_for(champion_class)
    rest = [slug for slug in original if slug not in SUPPORT_ITEMS]
    # The support item is bought first, so it leads the purchase order. Trim
    # from the end: the fifth item is the one most likely never to be finished.
    result = ([chosen] + rest)[:max(len(original), 1)]
    return result, result != original
