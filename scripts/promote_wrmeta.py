"""Promote the wr-meta scrape into data/items.json (the canonical dataset).

Our item data predates patch 7.2 and is stale in three ways the optimizer cares
about: wrong costs, wrong stats, and a dead Enchantment system. Patch 7.2 tied
active effects to champion classes ("Instead of being purchasable by every
champion, active effects are now tied to champion classes"), dissolving boot
enchantments into full items plus Tier 3 boots. So a 500g "Stridebreaker"
enchant is not a separate object to preserve: it is the old form of the 3100g
item that replaced it.

Rule (per the 7.2 notes, cross-checked against the scrape): the scrape is
authoritative and complete for real items. Anything of ours missing from it was
removed from the game and is deleted.

Slug direction matters: their "Dominik's Regards" is our "Lord Dominik's
Regard". We keep OUR slug and alias theirs onto it, because item_engine.json,
item_rules.json and builds.json all reference ours. Renaming would orphan them.

Components (MidTier/Basic) stay excluded: the optimizer builds from finished
items only, as it does today.

Run:
    python -m scripts.promote_wrmeta            # dry run, prints the diff
    python -m scripts.promote_wrmeta --write    # rewrite data/items.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# their slug -> our established slug (same item, different spelling)
ALIASES = {"dominiks-regards": "lord-dominiks-regard"}

# Patch 7.2: "Once the game time reaches 10:00, you can upgrade their boots into
# the corresponding Tier 3 version." Tier 3 is not a separate purchase competing
# for a slot: it is the same slot, later. Recorded so the optimizer can pick the
# tier-3 boot for a finished build and still order the tier-2 as an early buy.
BOOTS_UPGRADE = {
    "gluttonous-greaves": "immortal-treds",
    "berserkers-greaves": "gunmetal-greaves",
    "mercurys-treads": "chainlaced-crushers",
    "plated-steelcaps": "armored-advance",
    "ionian-boots-of-lucidity": "crimson-lucidity",
    "boots-of-mana": "spellslingers-shoes",
    "boots-of-dynamism": "armorcrusher-boots",
}

# categories that represent a finished, buyable item
KEEP = {"Physical", "Magic", "Defense", "Support", "Active", "Boots2", "Boots3"}
PRIMARY = ["Physical", "Magic", "Defense", "Support", "Boots", "Active"]


# Penetration comes in flat AND percent on the same item (Armorcrusher Boots:
# "+12 Armor Penetration" and "+6% Armor Penetration"). Keying stats by name
# alone let one silently overwrite the other, so split them deterministically:
# bare key = percent, "...Flat" = flat. The engine maps all four.
PEN = {"physicalPen", "magicPen"}


def stat_key(stat: str, percent: bool) -> str:
    if stat in PEN and not percent:
        return stat + "Flat"
    return stat


def primary_category(cats: list[str]) -> str:
    norm = ["Boots" if c in ("Boots2", "Boots3") else c for c in cats]
    for p in PRIMARY:
        if p in norm:
            return p
    return norm[0] if norm else "Active"


def build() -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    new = json.loads((DATA / "wrmeta_items.json").read_text(encoding="utf-8"))
    old = json.loads((DATA / "items.json").read_text(encoding="utf-8"))
    old_by = {i["slug"]: i for i in old}

    rows: list[dict] = []
    next_id = max((i.get("id") or 0) for i in old) + 1
    for it in new:
        if not (set(it["categories"]) & KEEP):
            continue                                   # component
        slug = ALIASES.get(it["slug"], it["slug"])
        prev = old_by.get(slug)
        stats = {stat_key(s["stat"], s["percent"]):
                 {"value": s["value"], "percent": s["percent"]}
                 for s in it["stats"]}
        if len(stats) != len(it["stats"]):
            raise SystemExit(f"stat key collision on {slug}: {it['stats']}")
        rec = {
            "id": prev["id"] if prev else next_id,
            "slug": slug,
            "name": prev["name"] if prev else it["name"],
            "category": primary_category(it["categories"]),
            "categories": ["Boots" if c in ("Boots2", "Boots3") else c
                           for c in it["categories"]],
            "cost": it["cost"],
            "stats": stats,
            # Named passives: the effect extractor gets "Wrath: ..." one at a
            # time instead of one run-on blob, which is what it choked on.
            "passives": [f"{p['name']}: {p['text']}" for p in it["passives"]],
            "tags": (prev or {}).get("tags", []),
            "icon": it["image"],
        }
        if "Boots3" in it["categories"]:
            rec["bootsTier"] = 3
        elif "Boots2" in it["categories"]:
            rec["bootsTier"] = 2
            if slug in BOOTS_UPGRADE:
                rec["upgradesTo"] = BOOTS_UPGRADE[slug]
        if not prev:
            next_id += 1
        rows.append(rec)

    keep_slugs = {r["slug"] for r in rows}
    removed = [i for i in old if i["slug"] not in keep_slugs]
    added = [r for r in rows if r["slug"] not in old_by]
    changed = []
    for r in rows:
        p = old_by.get(r["slug"])
        if not p:
            continue
        if p.get("cost") != r["cost"] or {k: v["value"] for k, v in (p.get("stats") or {}).items()} \
                != {k: v["value"] for k, v in r["stats"].items()}:
            changed.append((p, r))
    return rows, added, removed, changed


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    rows, added, removed, changed = build()
    print(f"items: {len(rows)}  (+{len(added)} new, -{len(removed)} removed, "
          f"{len(changed)} restated)\n")

    print(f"-- REMOVED ({len(removed)}) : not present in the 7.2 scrape")
    for i in sorted(removed, key=lambda x: x.get("category") or ""):
        print(f"   {i['slug']:32} {str(i.get('cost')):>5}g  {i.get('category')}")

    print(f"\n-- ADDED ({len(added)})")
    for i in sorted(added, key=lambda x: x["category"]):
        print(f"   {i['slug']:32} {str(i['cost']):>5}g  {i['category']}")

    print(f"\n-- RESTATED ({len(changed)}, first 10)")
    for p, r in changed[:10]:
        po = {k: v["value"] for k, v in (p.get("stats") or {}).items()}
        no = {k: v["value"] for k, v in r["stats"].items()}
        cost = f"{p.get('cost')}->{r['cost']}" if p.get("cost") != r["cost"] else "same"
        print(f"   {r['slug']:26} cost {cost:12} {po} -> {no}")

    if args.write:
        (DATA / "items.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
        print(f"\nwrote data/items.json ({len(rows)} items)")
    else:
        print("\n(dry run: pass --write to apply)")


if __name__ == "__main__":
    main()
