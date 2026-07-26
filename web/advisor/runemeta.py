"""Structured rune metadata and page legality.

A Wild Rift rune page is 1 keystone + 3 minors drawn from ONE tree, one per
slot, + 1 flex from anywhere. That is a small, closed rule set, so there is no
excuse for an illegal page reaching the user -- and equally no reason to throw
away an otherwise good build because one minor sits in the wrong slot. This
module supplies the legality facts for both: what the model is shown, and what
the validator checks it against.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DATA = ROOT / "data"


def _load(name: str, default=None):
    path = DATA / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


RUNES: list[dict] = _load("wrmeta_runes.json", []) or []
TREES: dict[str, dict] = (_load("rune_slots.json", {}) or {}).get("trees", {})
RUNE_SCALING: dict = (_load("rune_scaling.json", {}) or {})


def _canon(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


BY_NAME: dict[str, dict] = {r["name"]: r for r in RUNES}
CANON: dict[str, str] = {_canon(n): n for n in BY_NAME}


def slot_index() -> dict[str, tuple[str, int]]:
    """rune name -> (tree, slot). The single source of slot truth."""
    out: dict[str, tuple[str, int]] = {}
    for tree, slots in TREES.items():
        for index, names in slots.items():
            for name in names:
                out[name] = (tree, int(index))
    return out


SLOT_OF = slot_index()


def resolve(name: str) -> str | None:
    """Canonical rune name from whatever spelling the model produced."""
    return CANON.get(_canon(name or ""))


def metadata(name: str) -> dict:
    """Everything structurally true about one rune."""
    rune = BY_NAME.get(name) or {}
    tree, slot = SLOT_OF.get(name, (rune.get("tree", ""), 0))
    scaling = (RUNE_SCALING.get("runes") or {}).get(name) or {}
    stats = [entry.get("stat") for entry in scaling.get("stats") or [] if entry.get("stat")]
    return {
        "name": name,
        "type": rune.get("type", ""),
        "tree": tree,
        "slot": slot,
        "statDependencies": stats,
        "modelled": bool(scaling),
        "alwaysOn": any(
            entry.get("note") == "always on" for entry in scaling.get("stats") or []
        ),
    }


def keystones() -> list[str]:
    return sorted(r["name"] for r in RUNES if r.get("type") == "Keystone")


def minors_by_tree(tree: str) -> dict[int, list[str]]:
    """Legal minors for a tree, grouped by the slot each one occupies."""
    out: dict[int, list[str]] = {}
    for index, names in (TREES.get(tree) or {}).items():
        out[int(index)] = sorted(names)
    return out


def trees() -> list[str]:
    return sorted(TREES)


def page_errors(page: dict) -> list[str]:
    """Every way a rune page can be structurally wrong, as fixable messages.

    Returns [] for a legal page. The messages are written to be handed straight
    to a repair prompt, so each one names the offending rune and the rule it
    broke rather than merely reporting that something is invalid.
    """
    errors: list[str] = []
    keystone = resolve(page.get("keystone", ""))
    minors = [resolve(m) for m in (page.get("minors") or [])]
    flex = resolve(page.get("flex", ""))
    tree = page.get("primaryTree", "")

    if not keystone:
        errors.append(f"keystone {page.get('keystone')!r} is not a known rune")
    elif BY_NAME.get(keystone, {}).get("type") != "Keystone":
        errors.append(f"{keystone} is not a keystone")

    if len(minors) != 3:
        errors.append(f"exactly 3 minors are required, got {len(minors)}")
    unknown = [raw for raw, got in zip(page.get("minors") or [], minors) if not got]
    if unknown:
        errors.append(f"unknown minor rune names: {unknown}")

    if tree and tree not in TREES:
        errors.append(f"primaryTree {tree!r} is not one of {sorted(TREES)}")

    known_minors = [m for m in minors if m]
    if tree in TREES and len(known_minors) == 3:
        wrong_tree = [m for m in known_minors if SLOT_OF.get(m, ("", 0))[0] != tree]
        if wrong_tree:
            errors.append(
                f"minors must all come from the primary tree {tree}; "
                f"{wrong_tree} are not in it")
        else:
            slots = sorted(SLOT_OF[m][1] for m in known_minors)
            if slots != [1, 2, 3]:
                errors.append(
                    f"minors must occupy slots 1, 2 and 3 of {tree}, one each; "
                    f"got slots {slots}. Legal options: "
                    + "; ".join(f"slot {i}: {', '.join(names)}"
                                for i, names in sorted(minors_by_tree(tree).items())))

    if not flex:
        errors.append(f"flex rune {page.get('flex')!r} is not a known rune")
    elif flex in known_minors or flex == keystone:
        errors.append(f"flex rune {flex} is already on the page; the flex must be a "
                      "rune the page does not already run")
    else:
        # The flex (secondary) rune must come from a DIFFERENT tree than the
        # primary. A Resolve page cannot take a Resolve flex -- a page runs two
        # trees, not one. This was previously unchecked, so a same-tree flex
        # (Bard: Resolve primary + Resolve flex) validated.
        flex_tree = SLOT_OF.get(flex, ("", 0))[0]
        if tree in TREES and flex_tree == tree:
            other = [t for t in sorted(TREES) if t != tree]
            errors.append(
                f"flex rune {flex} is in the primary tree {tree}; the flex must come from a "
                f"DIFFERENT tree (one of {other}) -- a rune page runs two trees, not one")

    return errors


def legal_swap_error(incoming: str, outgoing: str, page: dict) -> str | None:
    """Why a rune-for-rune situational swap is illegal, or None if it is fine.

    Minors are slot-locked: swapping one means bringing in another rune from the
    same tree AND the same slot. The keystone may only be replaced by another
    keystone. The flex is free EXCEPT that it must stay out of the primary tree.
    """
    minors = [resolve(m) for m in (page.get("minors") or [])]
    keystone = resolve(page.get("keystone", ""))
    flex = resolve(page.get("flex", ""))
    tree = page.get("primaryTree", "")

    if outgoing == keystone:
        if BY_NAME.get(incoming, {}).get("type") != "Keystone":
            return f"{incoming} is not a keystone, so it cannot replace keystone {outgoing}"
        return None

    if outgoing == flex:
        # A flex swap may bring in any rune, but it still cannot pull the page
        # into a single tree: the replacement must stay off the primary tree.
        if tree in TREES and SLOT_OF.get(incoming, ("", 0))[0] == tree:
            return (f"{incoming} is in the primary tree {tree}; a flex replacement must stay "
                    "in a different tree")
        return None

    if outgoing in minors:
        from_slot = SLOT_OF.get(outgoing)
        to_slot = SLOT_OF.get(incoming)
        if from_slot and to_slot and from_slot != to_slot:
            legal = minors_by_tree(from_slot[0]).get(from_slot[1], [])
            return (f"{incoming} sits in {to_slot[0]} slot {to_slot[1]} and cannot replace "
                    f"minor {outgoing} in {from_slot[0]} slot {from_slot[1]}; a minor swap "
                    f"must stay in the same tree and slot. Legal here: {', '.join(legal)}")
        return None

    return None


def pool_text() -> str:
    """The rune pool as the model sees it, tagged with tree and slot."""
    rows = []
    for rune in RUNES:
        tree, slot = SLOT_OF.get(rune["name"], (rune.get("tree", "?"), "?"))
        text = " ".join((rune.get("text") or "").split())
        rows.append(f"{rune['name']} [{rune['type']} | {tree} slot {slot}]: {text}")
    return "\n".join(rows)


def pool_text_block() -> str:
    """The rune pool with the page-construction rule stated alongside it."""
    return ("RUNES (page = 1 keystone + 3 minors from ONE tree, one from each of that "
            "tree's 3 slots, + 1 flex from any tree):\n" + pool_text())
