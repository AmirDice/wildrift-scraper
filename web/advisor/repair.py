"""Targeted repair: fix the broken section, keep the rest.

The old behaviour on a validation failure was to re-send the entire ~65 KB
prompt with the errors appended and take whatever came back. That is expensive,
slow, and destructive: a single illegal minor rune would produce a completely
different five-item build, discarding work that was already correct.

So a repair now asks for one section back. The prompt carries the invalid
section, the exact validation errors, the pool needed to fix it, and an explicit
instruction not to touch anything else. What returns is merged into the existing
build rather than replacing it.

Full regeneration remains the fallback for failures that are not localised --
if the five items are wrong, everything downstream of them is suspect too.
"""
from __future__ import annotations

import json
import sys

from web.advisor import itemmeta, runemeta

# Sections we can repair in isolation, mapped to the response keys a repair is
# allowed to return. A section missing from here falls back to regeneration.
REPAIRABLE: dict[str, tuple[str, ...]] = {
    "runes": ("runes",),
    # bootsReason rides with the boots: a repair that swaps the boots and keeps
    # the old justification shipped "Immortal Treads -- Plated Steelcaps
    # mitigate physical damage" to a reader (7 such builds in the cache).
    "boots": ("boots", "bootsReason", "bootsUpgrade", "bootsUpgradeAfter",
              "bootsUpgradeReason", "situationalBoots"),
    "situational": ("situational",),
    "situationalRunes": ("situationalRunes",),
    "snowball": ("snowballSwap",),
    # Scores describe the build without being it: a missing row or a malformed
    # buildScore can be asked for again while the five items stand. This was
    # originally excluded alongside `items`, and the first live run paid for
    # that -- one incomplete score list triggered a full regeneration.
    "scores": ("candidateItemScores", "mandatoryAuditScores", "itemScores", "buildScore"),
    # The counter summary is commentary on the build, so it repairs in isolation.
    "counterSummary": ("counterSummary",),
    # Same for the play guide: it describes the build without being it, so a
    # thin guide is worth one more ask and never worth the five items.
    "playGuide": ("playGuide",),
}

# `items` is deliberately absent: the item selection is the spine of the build,
# and repairing it in isolation would leave the scores, swaps and rune reasoning
# describing a build that no longer exists.
MAX_ATTEMPTS = 2


def _completed_non_boots(slug: str) -> bool:
    item = itemmeta.ITEMS.get(slug) or {}
    return (item.get("category") != "Boots"
            and not (set(item.get("categories") or []) & {"Basic", "MidTier"}))


def mechanical_item_repair(build: dict, pool_slugs: list[str], enemies_known: bool,
                           locked_items: list[str]) -> list[str]:
    """Deterministic last-resort repair of the ITEMS list.

    The LLM repair budget can run out with the model still insisting on an
    illegal pair (a prod Riven run 502'd twice on Black Cleaver + Serylda's
    despite the pool stamping the group on both rows). The violations this
    handles are all mechanical -- two items from one exclusive group, two
    actives, a reactive item with no enemy known, a non-completed item, an
    item from outside the pool -- so the server fixes them mechanically:
    keep the best-scored offender, drop the rest, refill from the model's own
    scored alternatives. Returns log notes; empty means nothing was changed
    (either no mechanical fault was found, or a legal refill was impossible)
    and the caller's refusal stands.
    """
    items = [s for s in (build.get("items") or []) if isinstance(s, str)]
    if len(items) != 5:
        return []
    locked = set(locked_items or [])
    scores = {c.get("item"): c.get("score") or 0
              for c in (build.get("candidateItemScores") or []) if isinstance(c, dict)}

    def preference(slug: str) -> tuple:
        # Locked beats scored beats earlier-listed (items are purchase order).
        return (slug in locked, scores.get(slug, 0), -items.index(slug))

    drops: list[str] = []
    notes: list[str] = []

    def drop_all_but_best(members: list[str], why: str) -> bool:
        if len(members) < 2:
            return True
        if sum(1 for m in members if m in locked) > 1:
            return False  # two locked items conflict: nothing mechanical can fix that
        keep = max(members, key=preference)
        for m in members:
            if m is not keep and m not in drops:
                drops.append(m)
                notes.append(f"dropped {m} ({why}; kept {keep})")
        return True

    for name, group in itemmeta.HARD_EXCLUSIVE.items():
        if not drop_all_but_best([s for s in items if s in group], f"exclusive group {name}"):
            return []
    if not drop_all_but_best(itemmeta.active_items_in(items), "only one active allowed"):
        return []
    for s in items:
        if s in drops or s in locked:
            continue
        if not _completed_non_boots(s):
            drops.append(s); notes.append(f"dropped {s} (boots or component in item slots)")
        elif pool_slugs and s not in pool_slugs:
            drops.append(s); notes.append(f"dropped {s} (outside the supplied pool)")
        elif not enemies_known and s in itemmeta.SITUATIONAL_ONLY:
            drops.append(s); notes.append(f"dropped {s} (reactive item with no enemy known)")
    if not drops:
        return []

    kept = [s for s in items if s not in drops]
    has_active = bool(itemmeta.active_items_in(kept))

    def legal_fill(slug: str) -> bool:
        if slug in kept or slug in drops or not _completed_non_boots(slug):
            return False
        if pool_slugs and slug not in pool_slugs:
            return False
        if not enemies_known and slug in itemmeta.SITUATIONAL_ONLY:
            return False
        if slug in itemmeta.LATE_STRATEGIC:
            return False  # position rules make these poor mechanical fills
        if has_active and itemmeta.active_items_in([slug]):
            return False
        return all(sum(1 for k in kept + [slug] if k in g) <= 1
                   for g in itemmeta.HARD_EXCLUSIVE.values())

    ranked = sorted(scores, key=lambda s: scores.get(s, 0), reverse=True)
    fill_order = [s for s in ranked if s] + [s for s in pool_slugs if s not in ranked]
    result = list(items)
    for dropped in drops:
        fill = next((s for s in fill_order if legal_fill(s)), None)
        if fill is None:
            return []  # cannot legally reach five items; let the refusal stand
        result[result.index(dropped)] = fill
        kept.append(fill)
        has_active = has_active or bool(itemmeta.active_items_in([fill]))
        notes.append(f"filled with {fill} (score {scores.get(fill, 0)})")
    build["items"] = result
    return notes


def anti_heal_repair(build: dict, pool_slugs: list[str],
                     locked_items: list[str]) -> list[str]:
    """Put Grievous Wounds into a build that needs it, without regenerating.

    The anti-heal gate is a REQUIREMENT rather than an illegality, so
    mechanical_item_repair -- which only ever drops offending items -- cannot
    satisfy it, and a miss cost a full regeneration. Regenerations dominate
    counter-mode latency, so this swaps instead: drop the weakest item the
    model itself scored lowest, and buy the best anti-heal option it is
    allowed to hold.

    Returns log notes; empty means no legal swap existed and the caller's
    regeneration stands.
    """
    from web.advisor.validate import GRIEVOUS_WOUNDS_ITEMS

    items = [s for s in (build.get("items") or []) if isinstance(s, str)]
    if len(items) != 5 or any(s in GRIEVOUS_WOUNDS_ITEMS for s in items):
        return []
    locked = set(locked_items or [])
    scores = {c.get("item"): c.get("score") or 0
              for c in (build.get("candidateItemScores") or []) if isinstance(c, dict)}

    from web.advisor.prompt import _crit_conflicts
    _disablers, _dependent = _crit_conflicts(list(items) + list(GRIEVOUS_WOUNDS_ITEMS))
    crit_dead = set(_dependent) if any(d in items for d in _disablers) else set()

    def legal(slug: str) -> bool:
        if slug in items or not _completed_non_boots(slug):
            return False
        if pool_slugs and slug not in pool_slugs:
            return False
        # An item whose value depends on critting is dead weight beside a core
        # that cancels crit -- Mortal Reminder's penetration does nothing
        # alongside Guinsoo's Rageblade, which is exactly why the model
        # skipped anti-heal on Vayne rather than taking the wrong answer.
        if slug in crit_dead:
            return False
        rest = [s for s in items if s not in locked]
        return any(
            all(sum(1 for k in [x for x in items if x is not drop] + [slug] if k in g) <= 1
                for g in itemmeta.HARD_EXCLUSIVE.values())
            for drop in rest)

    options = [s for s in GRIEVOUS_WOUNDS_ITEMS if legal(s)]
    if not options:
        return []
    # The model's own opinion first; failing that, the cheapest answer.
    pick = max(options, key=lambda s: (scores.get(s, 0),
                                       -(itemmeta.ITEMS.get(s) or {}).get("cost", 0)))
    droppable = [s for s in items if s not in locked]
    if not droppable:
        return []
    drop = min(droppable, key=lambda s: (scores.get(s, 0), -items.index(s)))
    build["items"] = [pick if s == drop else s for s in items]
    return [f"swapped {drop} for {pick} (enemy healing needs Grievous Wounds)"]


def _pool_for(section: str, build: dict, allowed_items: list[str]) -> str:
    """The minimum context needed to fix this section, and nothing more."""
    if section == "runes":
        page = build.get("runes") or {}
        tree = page.get("primaryTree") or ""
        lines = ["LEGAL RUNE OPTIONS.",
                 "Keystones: " + ", ".join(runemeta.keystones())]
        for name in runemeta.trees():
            slots = runemeta.minors_by_tree(name)
            marker = "  <- your primary tree" if name == tree else ""
            lines.append(f"{name}{marker}: " + "; ".join(
                f"slot {i}: {', '.join(names)}" for i, names in sorted(slots.items())))
        lines.append("A page is 1 keystone + 3 minors from ONE tree, one from each of that "
                     "tree's 3 slots, + 1 flex from any tree that is not already on the page.")
        return "\n".join(lines)

    if section == "boots":
        rows = [f"{slug} -> upgrades to {item.get('upgradesTo')}"
                for slug, item in itemmeta.ITEMS.items() if item.get("bootsTier") == 2]
        return ("LEGAL BOOTS (tier-2 only; the tier-3 follows automatically):\n" + "\n".join(rows)
                + "\n\nWrite `bootsReason` and `bootsUpgradeReason` for the boots you return "
                  "NOW, naming them, in the context of this champion, this build and these "
                  "enemies; a reason written for a different pair of boots is wrong.")

    if section == "scores":
        chosen = build.get("items") or []
        return (
            "THE BUILD THESE SCORES DESCRIBE (do not change it):\n"
            f"  five items in purchase order: {', '.join(chosen)}\n"
            f"  boots: {build.get('boots')}\n\n"
            "Every one of those five items must appear in `candidateItemScores`, and every "
            "item named in the mandatory audit must appear in `mandatoryAuditScores`. Scores "
            "are 0-100 with a short reason. Items available to score: "
            + ", ".join(allowed_items))

    # The swap sections need the item pool and the current build to reason about.
    return ("ITEMS AVAILABLE: " + ", ".join(allowed_items)
            + "\nYOUR CURRENT FIVE, IN PURCHASE ORDER: "
            + ", ".join(build.get("items") or []))


ACCEPTED_KEYS = ("items", "boots", "bootsUpgrade", "runes", "summoners", "situational",
                 "situationalBoots", "snowballSwap")


def repair_prompt(section: str, build: dict, errors: list[str],
                  allowed_items: list[str], context: str = "") -> str:
    """One section, its errors, the pool required to fix them -- and the whole
    picture it has to fit.

    `context` is the ORIGINAL build prompt: champion, abilities, stat profile,
    identity, enemies, item pool. A repair used to get none of it, which is
    fine for choosing a legal rune page and wrong for writing a reason: "why
    these boots" cannot be answered without knowing who is wearing them and
    what else they bought. The accepted parts of the build are restated too,
    so the section is repaired to fit THIS build, not a build in general.
    """
    keys = REPAIRABLE[section]
    current = {key: build.get(key) for key in keys}
    accepted = {k: build.get(k) for k in ACCEPTED_KEYS if k in build and k not in keys}
    parts = []
    if context:
        parts.append("THE FULL BRIEF YOU ANSWERED (champion, kit, numbers, enemies, item pool):\n"
                     + context)
    parts += [
        f"Your previous answer was valid except for one section: {section}.",
        "THE REST OF YOUR BUILD, accepted and kept as is:\n"
        + json.dumps(accepted, ensure_ascii=False, indent=2),
        "THE INVALID SECTION, exactly as you returned it:\n"
        + json.dumps(current, ensure_ascii=False, indent=2),
        "WHAT IS WRONG WITH IT:\n- " + "\n- ".join(errors),
        _pool_for(section, build, allowed_items),
        "Return ONLY a JSON object containing the corrected "
        + " and ".join(f"`{k}`" for k in keys)
        + ". Do not restate or change any other part of the build -- the rest of it was "
          "accepted and will be kept. Do not explain; return the JSON object alone.",
    ]
    return "\n\n".join(parts)


def boots_reason_fits(build: dict) -> bool:
    """False when bootsReason names a different tier-2 boots than `boots`."""
    reason = str(build.get("bootsReason") or "").lower()
    if not reason:
        return True
    own = itemmeta.ITEMS.get(build.get("boots") or "", {}).get("name", "").lower()
    for slug, item in itemmeta.ITEMS.items():
        if item.get("bootsTier") == 2 and slug != build.get("boots"):
            name = item.get("name", "").lower()
            if name and name in reason and own not in reason:
                return False
    return True


def apply_repair(build: dict, section: str, patch: dict) -> bool:
    """Merge a repair response into the build. True when something changed.

    Only the keys the section owns are copied across. A model that ignores the
    instruction and returns a whole new build cannot overwrite the parts that
    already validated.
    """
    changed = False
    for key in REPAIRABLE.get(section, ()):
        if key in patch:
            build[key] = patch[key]
            changed = True
    if section == "boots" and not boots_reason_fits(build):
        # the repair returned new boots with the old justification (or none):
        # no reason beats a reason about different boots
        build["bootsReason"] = ""
        changed = True
    if not changed:
        print(f"[advisor] repair for {section} returned none of {REPAIRABLE.get(section)}; "
              f"got keys {sorted(patch)}", file=sys.stderr)
    return changed


def plan(sections: list[str]) -> tuple[list[str], list[str]]:
    """Split failing sections into ones we can patch and ones we cannot."""
    targeted = [s for s in sections if s in REPAIRABLE]
    blocking = [s for s in sections if s not in REPAIRABLE]
    return targeted, blocking
