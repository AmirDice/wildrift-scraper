"""Apply the patch 7.2c ITEM changes.

Separate from apply_patch_7_2c.py because that script shipped believing 7.2c
had no item changes. It does: the notes open with "champion and item balance
updates", and the ITEMS section rebalances the whole boots tier plus five
legendaries. The champion script only ever read `championChanges`, which does
not carry them.

    https://wildrift.leagueoflegends.com/en-us/news/game-updates/wild-rift-patch-notes-7-2c/

Every edit asserts the CURRENT value first and the script refuses to write if
any one of them misses, so running it twice is safe: the second run fails loudly
rather than applying a delta on top of itself.

Run:
    python -m scripts.apply_patch_7_2c_items            # dry run
    python -m scripts.apply_patch_7_2c_items --write

NOT APPLIED, because the data model has no place for them:
  * Sunfire Aegis build path (Bami's Cinder + Ruby Crystal + Cloth Armor + 600
    -> Bami's Cinder + Chain Vest + 700). items.json stores a total cost, not
    components, and the total is unchanged at 2900 either way.
  * Elemental Dragon and Dragon Soul buffs, and the Baron Lane minion damage
    reduction revert. Neither dragons nor minions are modelled.
  * AAA ARAM changes: out of scope, ranked only, same as 7.2a and 7.2b.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

PATCH = "7.2c"

# (slug, stat_key, old, new)
STAT_CHANGES = [
    # Tier 2 boots, buffed.
    ("berserkers-greaves", "attackSpeed", 30.0, 35.0),
    ("mercurys-treads", "tenacity", 15.0, 30.0),
    # Tier 3 boots, trimmed.
    ("chainlaced-crushers", "mr", 35.0, 30.0),
    ("armored-advance", "armor", 35.0, 30.0),
    ("spellslingers-shoes", "ap", 40.0, 35.0),
    # Legendaries.
    ("sunfire-aegis", "hp", 425.0, 350.0),
    ("sunfire-aegis", "armor", 20.0, 40.0),
    ("stridebreaker", "attackSpeed", 15.0, 25.0),
    ("mikaels-blessing", "healShieldPower", 6.0, 9.0),
    ("kaenic-rookern", "mr", 75.0, 80.0),
]

# (slug, old_substring, new_substring) -- passive text, so the effect extractor
# reads 7.2c numbers rather than 7.2b ones.
TEXT_CHANGES = [
    ("plated-steelcaps", "deal 6% reduced damage", "deal 10% reduced damage"),
    # The notes give the pre-patch ranged value as 12%; our scrape says 10%.
    # Matching what we actually have and writing the post-patch pair fixes the
    # discrepancy and lands the nerf in one edit, as with Zilean in 7.2b.
    ("gunmetal-greaves",
     "(15% for melee champions / 10% for ranged champions)",
     "(10% for melee champions / 7% for ranged champions)"),
    # "Big Bully" is a passive on Spellslinger's Shoes, not an item of its own.
    ("spellslingers-shoes", "22 bonus true damage", "18 bonus true damage"),
    # Likewise "Magebane" is Kaenic Rookern's passive.
    ("kaenic-rookern",
     "70-180 + 10% of max Health", "50-150 + 14% of max Health"),
    ("mikaels-blessing", "(90s Cooldown)", "(75s Cooldown)"),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    applied, failed = [], []

    def ok(msg):
        applied.append(msg)
        print(f"  OK   {msg}")

    def bad(msg):
        failed.append(msg)
        print(f"  MISS {msg}")

    items = json.loads((DATA / "items.json").read_text(encoding="utf-8"))
    by_slug = {i["slug"]: i for i in items}

    print("ITEM STATS")
    for slug, key, old, new in STAT_CHANGES:
        stat = (by_slug.get(slug, {}).get("stats") or {}).get(key)
        if stat and stat.get("value") == old:
            stat["value"] = new
            ok(f"{slug} {key} {old} -> {new}")
        else:
            bad(f"{slug} {key} expected {old}, found {stat and stat.get('value')}")

    print("\nITEM TEXT")
    for slug, old, new in TEXT_CHANGES:
        item = by_slug.get(slug)
        hit = False
        for i, passive in enumerate(item.get("passives") or []) if item else []:
            if old in passive:
                item["passives"][i] = passive.replace(old, new)
                hit = True
        ok(f"{slug}: {old!r} -> {new!r}") if hit else bad(f"{slug}: {old!r} not found")

    print(f"\n{len(applied)} applied, {len(failed)} not applied")

    if not args.write:
        print("\nDRY RUN -- nothing written. Re-run with --write.")
        return
    if failed:
        print("\nREFUSING TO WRITE: some edits did not match. Fix them first -- a "
              "partial patch is worse than none, because the data then claims to "
              "be 7.2c while carrying 7.2b item numbers.")
        raise SystemExit(1)

    (DATA / "items.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nwritten. Now re-run: python -m scripts.export_engine_data")


if __name__ == "__main__":
    main()
