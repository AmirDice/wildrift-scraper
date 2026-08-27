"""Apply patch 7.2d balance changes on top of the 7.2 / 7.2a / 7.2b / 7.2c data.

Transcribed from the official notes, not from wr-meta, which lags:

    https://wildrift.leagueoflegends.com/en-us/news/game-updates/wild-rift-patch-notes-7-2d/

Published 2026-08-26. Thirteen champions: Syndra, Yuumi, Vladimir, Veigar,
Pantheon, Mordekaiser, Twisted Fate, Fiora, Gwen, Yone, Renekton, Caitlyn,
Thresh. Two items: Edge of Night, Stormsurge. No rune changes.

Every edit asserts the CURRENT value first. If the source data shifts under us
(a re-scrape, a 7.2e), the assert fails loudly rather than silently doing
nothing and leaving a nerf unlanded.

Run:
    python -m scripts.apply_patch_7_2d            # dry run
    python -m scripts.apply_patch_7_2d --write
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

PATCH = "7.2d"

# (champion, stat_key, old, new) -- base stats
CHAMP_BASE = [
    ("Yone", "armor", 43.0, 37.0),
]

# (champion, ability_name_fragment, old_substring, new_substring)
CHAMP_TEXT = [
    # -- Syndra: mage-item compensation, damage scaling up across the kit
    ("Syndra", "Dark Sphere", "70 / 115 / 160 / 205", "80 / 130 / 180 / 230"),
    # Force of Will's OWN damage ratio only. The ability text also carries a
    # "+2% AP" on the Transcendent true damage, which the notes leave alone,
    # so the base-damage sequence rides along to keep the match unambiguous.
    ("Syndra", "Force of Will", "60 / 100 / 140 / 180 ( +45% AP )",
     "60 / 100 / 140 / 180 ( +60% AP )"),
    # Scatter the Weak states its ratio twice (the cone, then the spheres it
    # knocks back); both are the same 35% the notes raise. The second copy
    # carries a scrape typo ("1 90"), which is why this matches on the ratio
    # rather than the whole damage phrase.
    ("Syndra", "Scatter the Weak", "( +35% AP )", "( +50% AP )"),

    # -- Yuumi
    ("Yuumi", "You and Me", "6% / 7% / 8% / 9% ( +0.02% AP ) Heal and Shield Power",
     "8% / 9% / 10% / 11% ( +0.02% AP ) Heal and Shield Power"),
    ("Yuumi", "Zoomies", "85 / 110 / 135 / 160 ( +30% AP )",
     "80 / 110 / 140 / 170 ( +40% AP )"),

    # -- Vladimir: both halves of the Crimson Pact conversion
    ("Vladimir", "Crimson Pact", "4.5% of Health", "5% of Health"),
    ("Vladimir", "Crimson Pact", "140% Ability Power", "150% Ability Power"),
    ("Vladimir", "Transfusion", "75% bonus damage", "85% bonus damage"),
    ("Vladimir", "Tides of Blood",
     "20 / 40 / 60 / 80 ( +35% AP +2.5% of max Health )",
     "30 / 50 / 70 / 90 ( +35% AP +3% of max Health )"),

    # -- Pantheon: the execute threshold moves down, so the crit fires later
    ("Pantheon", "Comet Spear", "Enemies below 35% Health",
     "Enemies below 25% Health"),

    # -- Mordekaiser. Our scrape stores the rank-1 value of a per-rank
    # sequence ("Gains 1% Magic Pen"), the same shape as Rumble's Danger Zone
    # health cut in 7.2c: match what we hold, write the post-patch sequence.
    ("Mordekaiser", "Darkness Rise", "Gains 1% Magic Pen",
     "Gains 3% / 6% / 9% / 12% Magic Pen"),

    # -- Twisted Fate
    ("Twisted Fate", "Stacked Deck", "( +45% AP )", "( +35% AP )"),

    # -- Fiora
    ("Fiora", "Duelist's Dance", "3.5% ( +0.05% bonus AD )",
     "4% ( +0.055% bonus AD )"),

    # -- Gwen: per-snip ratio, final-snip ratio, and the jungle modifier
    ("Gwen", "Snip Snip", "( +7% AP )", "( +6% AP )"),
    ("Gwen", "Snip Snip", "( +35% AP )", "( +30% AP )"),
    ("Gwen", "Snip Snip", "Damage to monsters: 105%", "Damage to monsters: 100%"),

    # -- Renekton. Only the NORMAL-damage ratio moves; the Reign of Anger
    # line keeps its own 135%, so this matches the sequence with it.
    ("Renekton", "Cull the Meek", "80 / 130 / 180 / 230 ( +90% AD )",
     "80 / 130 / 180 / 230 ( +100% AD )"),
    ("Renekton", "Ruthless Predator", "24 / 48 / 72 / 96", "20 / 60 / 100 / 140"),
    ("Renekton", "Ruthless Predator", "36 / 72 / 108 / 144", "30 / 90 / 150 / 210"),

    # -- Caitlyn. Our text stores the level-scaled Headshot as its floor
    # ("50% AD"), so the floor is what moves; the crit coefficient is exact.
    ("Caitlyn", "Headshot", "50% AD + 125 Critical chance",
     "60% AD + 200 Critical chance"),
    ("Caitlyn", "Yordle Snap Trap", "Trap charging time: 27 / 22 / 17 / 12 seconds",
     "Trap charging time: 25 / 20 / 15 / 10 seconds"),

    # -- Thresh
    ("Thresh", "Death Sentence", "Cooldown is reduced by 3 seconds",
     "Cooldown is reduced by 2 seconds"),
]

# (champion, ability_name_fragment, old_cooldowns, new_cooldowns)
CHAMP_CDS = [
    ("Syndra", "Scatter the Weak", ["17", "17", "17", "17"], ["15", "15", "15", "15"]),
    ("Yuumi", "Zoomies", ["10", "10", "10", "10"], ["9", "9", "9", "9"]),
    # The notes give 17.5 / 15 / 12.5 / 10 pre-patch; our scrape rounded the
    # halves away (17 / 15 / 12 / 10). The post-patch sequence is whole
    # numbers, so writing it lands the buff and clears the rounding.
    ("Mordekaiser", "Death's Grasp", ["17", "15", "12", "10"], ["15", "13", "11", "9"]),
]

# (item_slug, field_path, old, new) -- field_path is dotted inside the item
ITEM_EDITS = [
    ("edge-of-night", "stats.physicalPenFlat.value", 8.0, 12.0),
    ("stormsurge", "cost", 2900, 2800),
]

# Changes the data model cannot express, recorded rather than dropped.
UNAPPLIED = [
    "Veigar / Baleful Strike range 7.75 -> 9: our ability text carries no range "
    "value at all (same shape as Kog'Maw's range in 7.2c), so there is nothing "
    "to edit. The buff is real and is simply invisible to our model.",
    "Yuumi / You and Me! cooldown 10/5/0s -> 8/4/0s: our scrape stores a flat 10 "
    "across all four ranks, while the notes describe a three-value ramp. Writing "
    "8/4/0 would invent a rank basis we do not hold, so the cooldown is left "
    "alone; the passive Heal and Shield Power buff on the same ability IS applied.",
    "Mordekaiser / Darkness Rise magic penetration is written as the full "
    "3/6/9/12% sequence even though our text held a single 1%, matching the "
    "7.2c Rumble precedent.",
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

    raw = json.loads((DATA / "champions_wr.json").read_text(encoding="utf-8"))
    champ_list = list(raw.values()) if isinstance(raw, dict) else raw
    champs = {c["name"]: c for c in champ_list}

    print("BASE STATS")
    for name, key, old, new in CHAMP_BASE:
        stat = ((champs.get(name) or {}).get("baseStats") or {}).get(key)
        if stat and stat.get("base") == old:
            stat["base"] = new
            if "perLevel" in stat:
                stat["lvl15"] = new + stat["perLevel"] * 14
            ok(f"{name} base {key} {old} -> {new} (lvl15 now {stat.get('lvl15')})")
        else:
            bad(f"{name} base {key} expected {old}, found {stat and stat.get('base')}")

    def abilities(name):
        champ = champs.get(name) or {}
        return (champ.get("abilities") or []) + [
            a for f in (champ.get("forms") or []) for a in (f.get("abilities") or [])]

    print("\nABILITY TEXT")
    for name, frag, old, new in CHAMP_TEXT:
        hit = False
        for a in abilities(name):
            if frag.lower() in (a.get("name") or "").lower() and old in (a.get("text") or ""):
                a["text"] = a["text"].replace(old, new)
                hit = True
        ok(f"{name}/{frag}: {old!r} -> {new!r}") if hit else \
            bad(f"{name}/{frag}: {old!r} not found")

    print("\nCOOLDOWNS")
    for name, frag, old, new in CHAMP_CDS:
        hit = False
        for a in abilities(name):
            if frag.lower() in (a.get("name") or "").lower() and a.get("cooldowns") == old:
                a["cooldowns"] = new
                hit = True
        ok(f"{name}/{frag} cooldowns {old} -> {new}") if hit else \
            bad(f"{name}/{frag} cooldowns expected {old}")

    print("\nITEMS")
    items_raw = json.loads((DATA / "items.json").read_text(encoding="utf-8"))
    item_list = list(items_raw.values()) if isinstance(items_raw, dict) else items_raw
    items = {i.get("slug"): i for i in item_list}
    for slug, path, old, new in ITEM_EDITS:
        node = items.get(slug)
        parts = path.split(".")
        for p in parts[:-1]:
            node = (node or {}).get(p)
        leaf = parts[-1]
        if node is not None and node.get(leaf) == old:
            node[leaf] = new
            ok(f"{slug} {path} {old} -> {new}")
        else:
            bad(f"{slug} {path} expected {old}, found {node and node.get(leaf)}")

    print(f"\n{len(applied)} applied, {len(failed)} not applied")
    if UNAPPLIED:
        print("\nDeliberately not applied:")
        for line in UNAPPLIED:
            print(f"  - {line}")

    if not args.write:
        print("\nDRY RUN -- nothing written. Re-run with --write.")
        return
    if failed:
        print("\nREFUSING TO WRITE: some edits did not match. Fix them first -- a "
              "partial patch is worse than none, because the data then claims to "
              "be 7.2d while carrying 7.2c numbers.")
        raise SystemExit(1)

    (DATA / "champions_wr.json").write_text(
        json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA / "items.json").write_text(
        json.dumps(items_raw, ensure_ascii=False, indent=2), encoding="utf-8")

    # The patch label the whole site reads.
    for path in ("champion_stat_overrides.json", "item_stat_rules.json", "stat_rules.json"):
        p = DATA / path
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        if "targetPatch" in d:
            d["targetPatch"] = PATCH
            p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"  targetPatch -> {PATCH} in data/{path}")

    print("\nwritten. Now re-run, in order:")
    print("  python -m scripts.extract_formulas --only \"Syndra,Yuumi,Vladimir,"
          "Pantheon,Mordekaiser,Twisted Fate,Fiora,Gwen,Renekton,Caitlyn,Thresh\"")
    print("  python -m scripts.audit_formulas")
    print("  python -m scripts.export_champion_details")
    print("  python -m scripts.export_engine_data")
    print("  bump web-next/src/lib/build-cache.ts, then redeploy the advisor")


if __name__ == "__main__":
    main()
