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

# Source slug -> canonical project slug. The wr-meta feed currently misspells
# Rocketbelt and Immortal Treads, so normalize them at the promotion boundary.
ALIASES = {
    "dominiks-regards": "lord-dominiks-regard",
    "hextech-roketbelt": "hextech-rocketbelt",
    "immortal-treds": "immortal-treads",
}

NAME_FIXES = {
    "hextech-rocketbelt": "Hextech Rocketbelt",
    "immortal-treads": "Immortal Treads",
}

ICON_FIXES = {
    "hextech-rocketbelt": "/items/hextech-rocketbelt.webp",
    "immortal-treads": "/items/immortal-treads.webp",
}

# Patch 7.2: "Once the game time reaches 10:00, you can upgrade their boots into
# the corresponding Tier 3 version." Tier 3 is not a separate purchase competing
# for a slot: it is the same slot, later. Recorded so the optimizer can pick the
# tier-3 boot for a finished build and still order the tier-2 as an early buy.
BOOTS_UPGRADE = {
    "gluttonous-greaves": "immortal-treads",
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


# The wr-meta 7.2 feed has several stale values and malformed tooltips. These
# are transcribed from Riot's official 7.2 notes and deliberately applied
# before scripts.apply_patch_7_2a adds the later hotfix deltas.
#
# Each entry may replace selected scalar stats, the purchase cost, display
# name, and/or the complete passive list. Keeping the corrections here makes a
# future re-promotion deterministic instead of reintroducing known bad data.
OFFICIAL_72_OVERRIDES: dict[str, dict] = {
    "bloodthirster": {
        "stats": {"physicalVamp": {"value": 8.0, "percent": True}},
    },
    "blade-of-the-ruined-king": {
        "stats": {"omnivamp": {"value": 10.0, "percent": True}},
        "passives": [
            "Thirst: [omnivamp] +10% Omni Vamp.",
            "Ruined Strikes: Attacks deal bonus physical damage equal to 7% of the enemy's current Health [hp] on-hit. (Melee attacks deal 10%). Minion damage: 15. Max damage vs monsters: 60.",
            "Drain: Hitting a champion with 3 attacks or abilities deals 30-100 bonus magic damage and steals 25% of their Move Speed [moveSpeed] for 2 seconds. (60s Cooldown)",
        ],
    },
    "goredrinker": {
        "stats": {"omnivamp": {"value": 8.0, "percent": True}},
        "passives": [
            "Thirsting Slash (Active): Deal physical damage equal to 175% Attack Damage [ad] to nearby enemies. Restore Health equal to 20% Attack Damage [ad] + 10% missing Health [hp] for each enemy champion hit. (12s cooldown)",
        ],
    },
    "youmuus-ghostblade": {
        "stats": {"physicalPenFlat": {"value": 15.0, "percent": False}},
    },
    "duskblade-of-draktharr": {
        "stats": {"physicalPenFlat": {"value": 18.0, "percent": False}},
    },
    "mortal-reminder": {
        "stats": {"physicalPen": {"value": 30.0, "percent": True}},
    },
    "seryldas-grudge": {
        "stats": {"physicalPen": {"value": 33.0, "percent": True}},
    },
    "edge-of-night": {
        "stats": {"physicalPenFlat": {"value": 8.0, "percent": False}},
    },
    "serpents-fang": {
        "stats": {"physicalPenFlat": {"value": 15.0, "percent": False}},
    },
    "the-collector": {
        "stats": {"physicalPenFlat": {"value": 10.0, "percent": False}},
    },
    "experimental-hexplate": {
        "scopedStats": {
            "ultimateAbilityHaste": {"value": 20.0, "percent": False},
        },
    },
    "spear-of-shojin": {
        "scopedStats": {
            "basicAbilityHaste": {"value": 20.0, "percent": False},
        },
        "passives": [
            "Dragonforce: Gain 20 Basic Ability Haste.",
            "Focused Will: Dealing damage to monsters or enemies with abilities increases your champion’s ability and passive damage by 3% for 6s. (Stacks 4 times).",
        ],
    },
    "quicksilver-sash": {
        "stats": {"mr": {"value": 30.0, "percent": False}},
    },
    "seekers-armguard": {"cost": 1400},
    "zhonyas-hourglass": {
        "passives": [
            "Stasis (Active): Become invulnerable and untargetable for 2.5 seconds, but unable to move, attack, cast abilities or use items. (120s Cooldown)",
        ],
    },
    "shurelyas-battlesong": {
        "stats": {"ap": {"value": 35.0, "percent": False}},
    },
    "malignance": {
        "scopedStats": {
            "ultimateAbilityHaste": {"value": 20.0, "percent": False},
        },
    },
    "plated-steelcaps": {
        "stats": {"armor": {"value": 25.0, "percent": False}},
        "passives": [
            "Block: Basic attacks from champions deal 6% reduced damage to you.",
        ],
    },
    "gluttonous-greaves": {
        "stats": {"omnivamp": {"value": 5.0, "percent": True}},
    },
    "ionian-boots-of-lucidity": {
        "scopedStats": {
            "summonerSpellHaste": {"value": 15.0, "percent": True},
        },
        "passives": ["Summoned: Gain 15% Summoner Spell Haste."],
    },
    "gunmetal-greaves": {
        "passives": [
            "Noxian Gait: Basic attacks against enemy champions grant Movement Speed (15% for melee champions / 10% for ranged champions) for 2 seconds.",
            "Blessed Blade: Basic attacks restore 12 Health on hit.",
        ],
    },
    "immortal-treads": {
        "stats": {"omnivamp": {"value": 5.0, "percent": True}},
    },
    "chainlaced-crushers": {
        "passives": [
            "Noxian Persistence: Taking magic damage from champions grants a magic shield equal to 20-140 (based on level) + 5% of your max Health [hp]. (12s Cooldown)",
        ],
    },
    "armored-advance": {
        "passives": [
            "Block: Basic attacks from champions deal 10% reduced damage to you.",
            "Noxian Endurance: Taking physical damage from champions grants a physical shield equal to 20-140 (based on level) + 5% of your max Health [hp]. (12s Cooldown)",
        ],
    },
    "crimson-lucidity": {
        "scopedStats": {
            "summonerSpellHaste": {"value": 20.0, "percent": True},
        },
        "passives": [
            "Summoned: Gain 20% Summoner Spell Haste.",
            "Noxian Haste: After damaging an enemy champion with an ability, shielding or healing an allied champion, or casting a Summoner Spell, gain Movement Speed (10% for melee champions / 8% for ranged champions) for 4 seconds. The same ability can only trigger this once every 4 seconds.",
        ],
    },
}


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
        # Fall back to the source slug when this promotion corrects a legacy
        # misspelling, preserving the established numeric id and tags.
        prev = old_by.get(slug) or old_by.get(it["slug"])
        stats = {stat_key(s["stat"], s["percent"]):
                 {"value": s["value"], "percent": s["percent"]}
                 for s in it["stats"]}
        if len(stats) != len(it["stats"]):
            raise SystemExit(f"stat key collision on {slug}: {it['stats']}")
        rec = {
            "id": prev["id"] if prev else next_id,
            "slug": slug,
            "name": NAME_FIXES.get(slug, prev["name"] if prev else it["name"]),
            "category": primary_category(it["categories"]),
            "categories": ["Boots" if c in ("Boots2", "Boots3") else c
                           for c in it["categories"]],
            "cost": it["cost"],
            "stats": stats,
            # Named passives: the effect extractor gets "Wrath: ..." one at a
            # time instead of one run-on blob, which is what it choked on.
            "passives": [f"{p['name']}: {p['text']}" for p in it["passives"]],
            "tags": (prev or {}).get("tags", []),
            "icon": ICON_FIXES.get(slug, it["image"]),
        }
        if "Boots3" in it["categories"]:
            rec["bootsTier"] = 3
        elif "Boots2" in it["categories"]:
            rec["bootsTier"] = 2
            if slug in BOOTS_UPGRADE:
                rec["upgradesTo"] = BOOTS_UPGRADE[slug]

        override = OFFICIAL_72_OVERRIDES.get(slug) or {}
        if "cost" in override:
            rec["cost"] = override["cost"]
        if "name" in override:
            rec["name"] = override["name"]
        rec["stats"].update(override.get("stats") or {})
        if "scopedStats" in override:
            rec["scopedStats"] = dict(override["scopedStats"])
        if "passives" in override:
            rec["passives"] = list(override["passives"])
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
