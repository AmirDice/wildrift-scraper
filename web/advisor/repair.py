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
