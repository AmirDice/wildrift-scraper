"""Audit extracted ability formulas for abilities the engine sees as EMPTY.

An ability modelled as dealing nothing is the worst failure mode we have,
because nothing downstream reports it: the champion still simulates, still
scores, still produces a build. It just quietly fights without that ability.

That is not hypothetical. The verbatim grounding filter deleted:
  - Gwen's Snip Snip (her primary damage): its max-stack total is never printed
  - Graves' New Destiny (his SHOTGUN passive): ratios 144%/280% not literal
  - Hecarim's Spirit of Dread
and the existing _damage_type_ok guard could not catch any of them -- it checks
the magic/physical SPLIT, and a missing ability barely moves a split.

An ability is only legitimately empty when it does no damage at all (a pure
shield/dash/buff), so this separates those from real losses by looking for
damage words in the source text.

Run:
    python -m scripts.audit_formulas
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORMULAS = ROOT / "data" / "ability_formulas.json"
CHAMPS = ROOT / "data" / "champions_wr.json"

# An ability that DAMAGES states a number attached to a damage type. Matching
# the bare word "damage" instead flagged all 53 shields in the game, because a
# shield "absorbs 200 magic damage" -- 90 reported losses of which 4 were real,
# which is noise dense enough that the real ones have to be found by hand.
DMG_RE = re.compile(
    r"\d[\d\s/.,%]*\)?\s*(?:\([^)]*\)\s*)?(?:physical|magic|true)\s+damage", re.I)
# Absorb clauses state a damage number that the ability soaks rather than deals.
ABSORB_RE = re.compile(r"[^.]*(?:absorb|aborb)\w*[^.]*\.", re.I)

# Abilities whose damage genuinely cannot be expressed in the schema, checked
# by hand. Listing them keeps the audit's output actionable: anything printed
# outside this set is a regression, not a known limit.
KNOWN_GAPS = {
    ("Amumu", "P"): "damage amplification (+10% true from incoming magic), not damage",
    ("Kayn", "P"): "form-gated conditional amp (+52-66% magic, 3s, Shadow Assassin only)",
    ("Smolder", "P"): "stack-gated empowerment of Q/W/E; no stack count in the tooltip",
    ("Volibear", "4"): "the stated 300/500/700 is damage to TOWERS; champions are only slowed",
}


def _text_of(champ: dict, slot: str) -> str:
    for a in champ.get("abilities") or []:
        if str(a.get("slot")) == str(slot):
            return a.get("text") or ""
    return ""


def _deals_damage(text: str) -> bool:
    """Does the tooltip state damage this ability DEALS (not damage it absorbs)?"""
    return bool(DMG_RE.search(ABSORB_RE.sub(" ", text)))


def main() -> None:
    F = json.loads(FORMULAS.read_text(encoding="utf-8"))
    C = json.loads(CHAMPS.read_text(encoding="utf-8"))
    C = list(C.values()) if isinstance(C, dict) else C
    by_name = {c["name"]: c for c in C}

    hard: list[tuple] = []   # states damage it deals, but no component -> real loss
    soft: list[tuple] = []   # states no damage -> legitimately empty
    known: list[tuple] = []  # real loss, but out of schema by decision
    ungrounded: list[tuple] = []

    for champ, rec in sorted(F.items()):
        if champ.startswith("_"):
            continue
        ch = by_name.get(champ) or {}
        for slot, ab in (rec.get("abilities") or {}).items():
            n_dmg = len(ab.get("damage") or [])
            txt = _text_of(ch, slot)
            for u in ab.get("unmodeled") or []:
                if "ungrounded" in u:
                    ungrounded.append((champ, slot, ab.get("name"), u))
            if n_dmg:
                continue
            if not _deals_damage(txt):
                soft.append((champ, slot, ab.get("name"), txt[:90]))
            elif (champ, slot) in KNOWN_GAPS:
                known.append((champ, slot, ab.get("name"), KNOWN_GAPS[(champ, slot)]))
            else:
                hard.append((champ, slot, ab.get("name"), txt[:90]))

    print(f"{'='*70}\nEMPTY ABILITIES THAT SHOULD DEAL DAMAGE  ({len(hard)})\n{'='*70}")
    for champ, slot, name, txt in hard:
        print(f"  {champ:<10} [{slot}] {str(name)[:26]:<26}")
        print(f"       text: {txt}...")
    if not hard:
        print("  none -- every ability that states damage it deals has a component")

    print(f"\n{'='*70}\nKNOWN GAPS (out of schema, accepted)  ({len(known)})\n{'='*70}")
    for champ, slot, name, why in known:
        print(f"  {champ:<13}[{slot}] {str(name)[:26]:<26} {why}")
    stale = sorted(set(KNOWN_GAPS) - {(c, s) for c, s, _, _ in known})
    if stale:
        print("  -- no longer empty, drop from KNOWN_GAPS: " + ", ".join(f"{c}[{s}]" for c, s in stale))

    print(f"\n{'='*70}\nEMPTY BUT LEGITIMATE (pure utility)  ({len(soft)})\n{'='*70}")
    for champ, slot, name, _ in soft:
        print(f"  {champ:<10} [{slot}] {name}")

    print(f"\n{'='*70}\nNUMBERS THE GROUNDING FILTER STILL REJECTS  ({len(ungrounded)})\n{'='*70}")
    for champ, slot, name, u in ungrounded:
        print(f"  {champ:<10} [{slot}] {str(name)[:24]:<24} {u[:70]}")
    if not ungrounded:
        print("  none")


if __name__ == "__main__":
    main()
