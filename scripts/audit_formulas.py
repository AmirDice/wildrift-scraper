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

# Text that means "this ability damages something".
DMG_RE = re.compile(
    r"\b(damage|damages|deal|deals|dealing|burn|burns|execute|strikes?)\b", re.I)
# Abilities that legitimately deal nothing.
UTILITY_RE = re.compile(
    r"\b(shield|heal|dash|blink|cleanse|untargetable|invulnerab|stealth|vision|"
    r"movement speed|move speed)\b", re.I)


def _text_of(champ: dict, slot: str) -> str:
    for a in champ.get("abilities") or []:
        if str(a.get("slot")) == str(slot):
            return a.get("text") or ""
    return ""


def main() -> None:
    F = json.loads(FORMULAS.read_text(encoding="utf-8"))
    C = json.loads(CHAMPS.read_text(encoding="utf-8"))
    C = list(C.values()) if isinstance(C, dict) else C
    by_name = {c["name"]: c for c in C}

    hard: list[tuple] = []   # damage text, but no damage component -> real loss
    soft: list[tuple] = []   # no damage text -> legitimately empty
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
            has_dmg_text = bool(DMG_RE.search(txt))
            is_util = bool(UTILITY_RE.search(txt)) and not has_dmg_text
            (soft if (is_util or not has_dmg_text) else hard).append(
                (champ, slot, ab.get("name"), txt[:90]))

    print(f"{'='*70}\nEMPTY ABILITIES THAT SHOULD DEAL DAMAGE  ({len(hard)})\n{'='*70}")
    for champ, slot, name, txt in hard:
        print(f"  {champ:<10} [{slot}] {str(name)[:26]:<26}")
        print(f"       text: {txt}...")
    if not hard:
        print("  none -- every ability whose text mentions damage has a damage component")

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
