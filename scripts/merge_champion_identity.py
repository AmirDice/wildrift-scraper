"""Rebuild data/champion_identity.json: what each kit NEEDS, not what to buy.

WHY

    The old cards named items. 420 archetype notes across 141 champions read
    like "Combines high attack damage, critical chance, and lifesteal using
    essence-reaver, bloodthirster, and infinity-edge", and the block presented
    that to the model as a hard constraint -- "this CONSTRAINS which archetype
    the build may express ... never outside them", "PRIMARY anchors the
    default build".

    So the model recited. Every Graves build came back as essence-reaver,
    bloodthirster, infinity-edge, which is the PRIMARY note verbatim, and the
    one flourish an explicit "build the strongest loadout you can" objective
    produced was Guardian Angel fifth -- listed on the same card as an
    accepted flex, in that exact slot. Asking for the best possible build
    could not work while the answer was in the question.

    The supplied identity file states needs as CATEGORIES and names no item
    anywhere: penetration_vs_resists, anti_heal_vs_healing, tenacity_vs_cc.
    Those already map onto the response categories in itemmeta, so the
    champion says what it needs and items_answering() decides which item in
    its own legal pool provides it.

WHAT IS KEPT FROM THE OLD CARDS

    The `never` verdicts and avoidStats, and nothing else. Those are facts
    about the kit rather than opinions about the meta -- Graves has no AP
    ratios at any level of ambition -- and the validator enforces them after
    generation. statPriorities survives too: it is a stat ordering, not an
    item list.

    signatureItems and flexPatterns are dropped on purpose. They are the
    prescription this migration exists to remove.

TRAITS ARE STORED, NOT USED

    The supplied file carries 21 traits per champion on a 0-1 scale. They are
    written to `traitPriors` and deliberately not put in the prompt. Checked
    against our own derived data they correlate at rho=0.45 with measured hard
    crowd-control depth -- Dr. Mundo reads cc 0.73 with zero hard crowd
    control because his cleaver is a slow, Jinx reads 0.15 with a root. They
    answer "how much does this champion bring to a fight", which is a
    different question from the one the deriver answers, and the deriver is
    measured (57/57, 27/27). Anything the advisor can measure keeps coming
    from the measurement.

    They are here because draft-score.ts wants exactly this shape and
    currently reads a separately generated draftKit. That migration is a
    separate job.

    python -m scripts.merge_champion_identity            # write it
    python -m scripts.merge_champion_identity --dry-run  # report only
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OURS = ROOT / "data" / "champion_identity.json"
SUPPLIED = Path.home() / "Downloads" / "wildrift_141_champion_identities.json"


def summary(entry: dict) -> str:
    """One line, from the supplied strengths and weaknesses."""
    good = ", ".join(entry.get("strengths") or [])
    bad = ", ".join(entry.get("weaknesses") or [])
    out = good[:1].upper() + good[1:] if good else ""
    if bad:
        out = f"{out}. Weak at: {bad}" if out else f"Weak at: {bad}"
    return out.rstrip(".") + "." if out else ""


def merge(name: str, supplied: dict, old: dict) -> dict:
    # Only the hard limits survive from the old card. Everything else it said
    # about how to build is what this migration is removing.
    never = [a for a in (old.get("archetypes") or [])
             if str(a.get("status", "")).lower() == "never"]
    card = {
        "roles": supplied.get("roles") or [],
        "classes": supplied.get("classes") or [],
        "identitySummary": summary(supplied),
        "combat": supplied.get("combat_identity") or {},
        "teamComp": supplied.get("team_comp_identity") or {},
        # Needs, not items. This is the whole point of the migration.
        "itemizationNeeds": supplied.get("itemization_identity") or {},
        "hardLimits": {
            "neverArchetypes": [
                {"path": a.get("path", ""), "why": a.get("note", "")}
                for a in never
            ],
            "avoidStats": old.get("avoidStats") or [],
        },
        # Stored, not prompted. See the module docstring.
        "traitPriors": supplied.get("traits") or {},
    }
    if old.get("statPriorities"):
        card["statPriorities"] = old["statPriorities"]
    return card


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--supplied", type=Path, default=SUPPLIED)
    args = ap.parse_args()

    if not args.supplied.exists():
        print(f"no supplied identity file at {args.supplied}", file=sys.stderr)
        return 1
    src = json.loads(args.supplied.read_text(encoding="utf-8"))
    supplied = {c["champion"]: c for c in src["champions"]}
    old_doc = json.loads(OURS.read_text(encoding="utf-8"))
    old = old_doc["champions"]

    out, carried, kept_limits = {}, [], 0
    for name in sorted(set(old) | set(supplied)):
        o = old.get(name, {})
        s = supplied.get(name)
        if s is None:
            # Transform forms are keyed separately by the advisor and are not
            # in the supplied roster. Kayn (Rhaast) inherits base Kayn's
            # identity and keeps its OWN hard limits, which differ: Rhaast is
            # the bruiser half.
            base = name.split(" (")[0]
            s = supplied.get(base)
            if s is None:
                print(f"  [warn] {name}: no supplied entry and no base match; "
                      f"carrying the old card unchanged")
                out[name] = o
                continue
            carried.append(name)
        card = merge(name, s, o)
        kept_limits += len(card["hardLimits"]["neverArchetypes"])
        out[name] = card

    doc = {
        "_meta": {
            "generatedOn": date.today().isoformat(),
            "identitySource": args.supplied.name,
            "hardLimitsSource": "carried from the previous cards",
            "note": ("Needs, not items. traitPriors are stored and NOT put in "
                     "the prompt; anything the advisor can measure is measured."),
            "statuses": old_doc.get("_meta", {}).get("statuses"),
        },
        "champions": out,
    }
    named = sum(1 for c in out.values()
                for a in (c.get("hardLimits", {}).get("neverArchetypes") or [])
                if "-" in str(a.get("why", "")))
    print(f"champions        : {len(out)}")
    print(f"inherited a base : {', '.join(carried) or 'none'}")
    print(f"never verdicts   : {kept_limits} kept")
    print(f"notes still naming a slug (in `why` prose only): {named}")
    if args.dry_run:
        print("\n--dry-run: nothing written")
        return 0
    shutil.copy2(OURS, OURS.with_suffix(".json.pre-merge"))
    OURS.write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {OURS.relative_to(ROOT)}  (backup: champion_identity.json.pre-merge)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
