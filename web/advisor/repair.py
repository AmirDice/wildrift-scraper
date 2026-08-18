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
    "boots": ("boots", "bootsUpgrade", "bootsUpgradeAfter", "bootsUpgradeReason", "situationalBoots"),
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
        return "LEGAL BOOTS (tier-2 only; the tier-3 follows automatically):\n" + "\n".join(rows)

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


def repair_prompt(section: str, build: dict, errors: list[str],
                  allowed_items: list[str]) -> str:
    """One section, its errors, and the pool required to fix them."""
    keys = REPAIRABLE[section]
    current = {key: build.get(key) for key in keys}
    return "\n\n".join([
        f"Your previous answer was valid except for one section: {section}.",
        "THE INVALID SECTION, exactly as you returned it:\n"
        + json.dumps(current, ensure_ascii=False, indent=2),
        "WHAT IS WRONG WITH IT:\n- " + "\n- ".join(errors),
        _pool_for(section, build, allowed_items),
        "Return ONLY a JSON object containing the corrected "
        + " and ".join(f"`{k}`" for k in keys)
        + ". Do not restate or change any other part of the build -- the rest of it was "
          "accepted and will be kept. Do not explain; return the JSON object alone.",
    ])


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
    if not changed:
        print(f"[advisor] repair for {section} returned none of {REPAIRABLE.get(section)}; "
              f"got keys {sorted(patch)}", file=sys.stderr)
    return changed


def plan(sections: list[str]) -> tuple[list[str], list[str]]:
    """Split failing sections into ones we can patch and ones we cannot."""
    targeted = [s for s in sections if s in REPAIRABLE]
    blocking = [s for s in sections if s not in REPAIRABLE]
    return targeted, blocking
