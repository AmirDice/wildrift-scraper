"""Apply patch 7.3's rune changes.

Five runes move, and one of them is a replacement rather than an edit:

  Lethal Tempo      reworked: flat stacks, and a bullet at max stacks that
                    scales with the attack speed you brought yourself.
  Conqueror         Ability Power per stack standardised against its own
                    Attack Damage (1.667x, so 5 - 8.33 instead of 4 - 8).
  Legend: Tenacity  REPLACED by Legend: Haste, because Mercury's Treads now
                    carries enough tenacity on its own.
  Demolish          renumbered for the new turret plating.
  Ingenious Hunter  removed for now.

A rune that leaves the game keeps its record, marked, exactly as a removed
item does: the August ladder pages still name Legend: Tenacity, and a rune the
catalogue cannot resolve draws an empty square with no name. Anything that
RECOMMENDS a rune filters on removedIn.

Four files carry a rune: data/runes.json (the site's rune pages),
data/wrmeta_runes.json (an advisor source), data/rune_engine.json (what the
engines simulate) and data/rune_scaling.json (the fully-scaled sheet). Miss one
and the rune page and the build advisor disagree about the same rune.

Run:
    python -m scripts.apply_patch_7_3_runes
    python -m scripts.apply_patch_7_3_runes --write

Then: python -m scripts.export_engine_data
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PATCH = "7.3"

RUNES = DATA / "runes.json"
WRMETA = DATA / "wrmeta_runes.json"
ENGINE = DATA / "rune_engine.json"
SCALING = DATA / "rune_scaling.json"

#: name -> the description after 7.3, transcribed from the notes.
DESCRIPTIONS = {
    "Lethal Tempo":
        "Landing basic attacks on enemy champions grants stacking Attack Speed, 8% for melee "
        "and 6.4% for ranged, up to 6 stacks for 6 seconds. At max stacks, attacks also fire a "
        "bullet dealing 9 - 30 adaptive damage for melee and 6 - 24 for ranged. Each 1% bonus "
        "Attack Speed increases that damage by 1% for melee and 0.67% for ranged.",
    "Conqueror":
        "Basic attacks and abilities generate stacks of Conqueror on enemy champions hit, up to "
        "one per attack or cast. Each stack lasts 6 seconds and grants 3 - 5 (based on level) "
        "bonus Attack Damage or 5 - 8.33 Ability Power (Adaptive), stacking up to 6 times. At "
        "full stacks, melee champions heal for 9% of the damage they deal to champions and "
        "ranged champions for 6%.",
    "Demolish":
        "After hitting a turret with 3 basic attacks, melee champions deal 85 + 28% maximum "
        "Health bonus physical damage, and ranged champions 50 + 20% maximum Health.",
}

#: The rune that replaces Legend: Tenacity. Same tree and slot; it is a new
#: rune, not a renamed one, so it gets its own record.
LEGEND_HASTE = {
    "slug": "legend-haste",
    "name": "Legend: Haste",
    "tree": "Precision",
    "type": "Minor",
    "description": "Takedowns and killing monsters and minions grant 1.5 Ability Haste per "
                   "stack, up to 15 Ability Haste.",
    # PC League's art: Riot has published no Wild Rift icon for it yet, and an
    # empty square in the rune picker is worse. Fetched by
    # scripts/fetch_pc_rune_icons.py.
    "icon": "/items/legend-haste.png",
    "addedIn": PATCH,
}

REMOVED = {
    "Legend: Tenacity": "Replaced by Legend: Haste in 7.3, with Mercury's Treads now carrying "
                        "the tenacity.",
    "Ingenious Hunter": "Removed in 7.3: its item synergies were too strong in some hands and "
                        "did nothing in others.",
}

#: What the engines simulate. Same idiom as the item overrides: a key written
#: back as 0 is a key the patch took away.
ENGINE_FX = {
    "Lethal Tempo": {
        "asPctPassive": 48,
        "_why": "8% per stack, six stacks, melee. Ranged is 6.4% (38.4%), and the engine "
                "carries one figure. The bullet at max stacks is adaptive damage that scales "
                "with your own bonus attack speed, which has no key here.",
    },
    "Conqueror": {
        "adaptiveAp": {"lvlRange": [30, 50]},
        "bonusAp": {"lvlRange": [30, 50]},
        "_why": "Ability Power per stack is standardised to 1.667x the Attack Damage figure: "
                "5 - 8.33 per stack, six stacks.",
    },
    "Legend: Haste": {
        "hasteFlat": 15,
        "_why": "1.5 Ability Haste per stack, ten stacks. Replaces Legend: Tenacity.",
    },
    "Legend: Tenacity": {
        "tenacityPct": 0,
        "_why": "Removed from the game in 7.3. Zeroed rather than deleted so a build saved "
                "before the patch scores what it actually does now, which is nothing.",
    },
    "Ingenious Hunter": {
        "itemHasteFlat": 0,
        "_why": "Removed from the game in 7.3.",
    },
    "Demolish": {
        "_why_turret": "Turret damage only, which the engine does not simulate; the numbers "
                       "changed in 7.3 (85 + 28% max Health melee, 50 + 20% ranged) and the "
                       "effect on a champion fight is still nothing.",
    },
}

#: The fully-scaled sheet the site shows beside a build.
SCALING_ROWS = {
    "Lethal Tempo": {
        "stats": [{"stat": "attackSpeedPct", "melee": 48, "ranged": 38.4,
                   "note": "6 stacks: 8% melee or 6.4% ranged per stack"}],
        "effects": [{"label": "Bullet at max stacks", "value": "9 - 30 adaptive (melee)",
                     "note": "6 - 24 ranged, +1% per 1% bonus Attack Speed (0.67% ranged)"}],
        "evidence": "8% for melee and 6.4% for ranged, up to 6 stacks",
    },
    "Legend: Haste": {
        "stats": [{"stat": "abilityHaste", "value": 15,
                   "note": "1.5 per stack, ten stacks"}],
        "evidence": "up to a maximum of 15 Ability Haste, with each stack granting 1.5",
    },
    "Conqueror": {
        "stats": [{"stat": "adaptive", "ad": 30, "ap": 50,
                   "note": "6 stacks at level 15: 5 AD or 8.33 AP per stack"},
                  {"stat": "omnivamp", "melee": 9, "ranged": 6,
                   "note": "at full stacks"}],
        "evidence": "3 - 5 bonus Attack Damage or 5 - 8.33 Ability Power per stack",
    },
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    runes = json.loads(RUNES.read_text(encoding="utf-8"))
    wrmeta = json.loads(WRMETA.read_text(encoding="utf-8"))
    engine = json.loads(ENGINE.read_text(encoding="utf-8"))
    scaling = json.loads(SCALING.read_text(encoding="utf-8"))

    by_name = {r["name"]: r for r in runes}
    applied: list[str] = []
    problems: list[str] = []

    for name, text in DESCRIPTIONS.items():
        if name not in by_name:
            problems.append(f"{name}: not in runes.json")
            continue
        by_name[name]["description"] = text
        applied.append(f"{name}: description rewritten")

    for name, why in REMOVED.items():
        if name not in by_name:
            problems.append(f"{name}: not in runes.json")
            continue
        by_name[name]["removedIn"] = PATCH
        by_name[name]["removedWhy"] = why
        applied.append(f"{name}: marked removed in {PATCH}")

    if LEGEND_HASTE["name"] not in by_name:
        record = {"id": max(r["id"] for r in runes) + 1, **LEGEND_HASTE}
        # Beside the rune it replaces, so the Precision minors stay in slot
        # order on the page.
        at = next((i for i, r in enumerate(runes) if r["name"] == "Legend: Tenacity"), len(runes) - 1)
        runes.insert(at + 1, record)
        applied.append(f'{LEGEND_HASTE["name"]}: added')

    # wr-meta's copy, which the advisor reads.
    wr_by_name = {r.get("name"): r for r in wrmeta}
    for name, text in DESCRIPTIONS.items():
        if name in wr_by_name:
            wr_by_name[name]["text"] = text
    for name, why in REMOVED.items():
        if name in wr_by_name:
            wr_by_name[name]["removedIn"] = PATCH
    if LEGEND_HASTE["name"] not in wr_by_name:
        wrmeta.append({
            "name": LEGEND_HASTE["name"], "slug": LEGEND_HASTE["slug"],
            "tagline": "Takedowns grant Ability Haste",
            "tree": LEGEND_HASTE["tree"], "type": LEGEND_HASTE["type"],
            "text": LEGEND_HASTE["description"], "image": LEGEND_HASTE["icon"],
        })
        applied.append(f'{LEGEND_HASTE["name"]}: added to the advisor rune source')

    for name, fx in ENGINE_FX.items():
        entry = dict(engine.get(name) or {})
        entry.update(fx)
        engine[name] = entry
        applied.append(f"{name}: engine effects updated")

    for name, row in SCALING_ROWS.items():
        scaling.setdefault("runes", {})[name] = row
        applied.append(f"{name}: scaling row updated")
    for name in REMOVED:
        scaling.get("runes", {}).pop(name, None)
    scaling["targetPatch"] = PATCH

    print(f"APPLIED ({len(applied)})")
    for line in applied:
        print(f"  {line}")
    if problems:
        print(f"\nPROBLEMS ({len(problems)}):")
        for line in problems:
            print(f"  {line}")
        return 1

    if args.write:
        for path, payload in ((RUNES, runes), (WRMETA, wrmeta), (ENGINE, engine), (SCALING, scaling)):
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("\nwrote runes.json, wrmeta_runes.json, rune_engine.json, rune_scaling.json")
    else:
        print("\ndry run: pass --write to save")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
