"""Apply patch 7.2c balance changes on top of the 7.2 / 7.2a / 7.2b data.

Transcribed from the official notes, not from wr-meta, which lags:

    https://wildrift.leagueoflegends.com/en-us/news/game-updates/wild-rift-patch-notes-7-2c/

Published 2026-08-12. Nine champions: Cho'Gath, Jinx, Nilah, Leona, Rumble,
Nasus, Ryze, Warwick, Kog'Maw. No item or rune changes in this patch.

Every edit asserts the CURRENT value first. If the source data shifts under us
(a re-scrape, a 7.2d), the assert fails loudly rather than silently doing
nothing and leaving a nerf unlanded.

Run:
    python -m scripts.apply_patch_7_2c            # dry run
    python -m scripts.apply_patch_7_2c --write
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

PATCH = "7.2c"

# (champion, stat_key, old, new) -- base stats
CHAMP_BASE = [
    ("Jinx", "ad", 54.0, 58.0),
    ("Leona", "hp", 750.0, 690.0),
    ("Leona", "armor", 55.0, 50.0),
    ("Rumble", "hp", 690.0, 660.0),
    ("Nasus", "armor", 46.0, 40.0),
    ("Ryze", "hp", 660.0, 630.0),
    ("Ryze", "armor", 40.0, 37.0),
]

# (champion, stat_key, old_per_level, new_per_level)
#
# The notes give Leona and Rumble the SAME health per level, 120 -> 128. Our
# scrape has 112 and 89, and both are internally consistent with their stored
# lvl15 (750 + 112*14 = 2318; 690 + 89*14 = 1936). Two champions sharing Riot's
# stated 120 while our data holds two different numbers is a different growth
# BASIS, not a typo in one row, so writing Riot's 128 into both would flatten a
# real difference and make Leona and Rumble grow identically.
#
# The delta is applied instead of the absolute: +8 per level, which preserves
# the gap between them and lands the size of the buff. Called out in the summary
# because it is the one edit here that is not a straight transcription.
CHAMP_GROWTH = [
    ("Leona", "hp", 112.0, 120.0),
    ("Rumble", "hp", 89.0, 97.0),
]

# (champion, ability_name_fragment, old_substring, new_substring)
CHAMP_TEXT = [
    ("Cho'Gath", "Vorpal Spikes", "15 / 35 / 55 / 75", "20 / 45 / 70 / 95"),
    ("Cho'Gath", "Vorpal Spikes",
     "2.15% / 2.5% / 2.85% / 3.2% + 0.5% per Feast stack",
     "2.3% / 2.7% / 3.1% / 3.5% + 0.6% per Feast stack"),
    # Appears twice, on the champion line and the minion line.
    ("Cho'Gath", "Feast", "8% of Cho'Gath's bonus Health",
     "10% of Cho'Gath's bonus Health"),

    ("Jinx", "Get Excited", "12% Total Attack Speed", "25% Total Attack Speed"),

    ("Nilah", "Formless Blade", "35% of current Critical Strike Chance",
     "28% of current Critical Strike Chance"),
    ("Nilah", "Apotheosis", "60 / 120 / 180 ( +140% AD )",
     "60 / 110 / 160 ( +50% AD )"),

    # Armor and Magic Resist lines carry the same sequence; both are nerfed.
    ("Leona", "Eclipse", "40 / 60 / 80 / 100", "30 / 50 / 70 / 90"),

    ("Rumble", "Flamespitter", "120 / 160 / 200 / 240 ( +110% AP )",
     "100 / 140 / 180 / 220 ( +125% AP )"),
    ("Rumble", "Flamespitter", "6% / 8% / 10% / 12% of the target's max Health",
     "7% / 8% / 9% / 10% of the target's max Health"),
    ("Rumble", "Flamespitter", "180 / 240 / 300 / 360 ( +165% AP )",
     "150 / 210 / 270 / 330 ( +187.5% AP )"),
    # Our scrape carries a single 9% for the Danger Zone health cut where the
    # notes give a per-rank 9/12/15/18%. Same treatment as Zilean in 7.2b:
    # match what we actually have, write the post-patch sequence.
    ("Rumble", "Flamespitter", "plus 9% of the target's max Health",
     "plus 10.5% / 12% / 13.5% / 15% of the target's max Health"),
    ("Rumble", "Scrap Shield", "40 / 70 / 100 / 130 ( +6% of max Health",
     "40 / 80 / 120 / 160 ( +4% of max Health"),
    ("Rumble", "Scrap Shield", "60 / 105 / 150 / 195 ( +9% of max Health",
     "60 / 120 / 180 / 240 ( +6% of max Health"),
    ("Rumble", "Harpoon", "( +40% AP )", "( +50% AP )"),
    ("Rumble", "Harpoon", "( +60% AP )", "( +75% AP )"),

    ("Ryze", "Rune Prison", "70 / 110 / 150 / 190 ( + 65% AP + 4% bonus Mana )",
     "50 / 90 / 130 / 170 ( + 55% AP + 3% bonus Mana )"),

    ("Warwick", "Infinite Duress", "125 / 300 / 475", "100 / 275 / 450"),

    ("Kog'Maw", "Living Artillery", "100 / 140 / 180 ( +25% AP +75% bonus AD )",
     "80 / 120 / 160 ( +25% AP +75% bonus AD )"),
    ("Kog'Maw", "Living Artillery", "additional 40 Mana (max 400 Mana)",
     "additional 50 Mana (max 500 Mana)"),
]

# (champion, ability_name_fragment, old_cooldowns, new_cooldowns)
CHAMP_CDS = [
    # The notes say Feast was 80/70/60 pre-patch; our scrape has a flat 80/80/80,
    # so ranks 2 and 3 were already wrong. Writing the post-patch sequence fixes
    # the scrape and lands the buff in one edit.
    ("Cho'Gath", "Feast", ["80", "80", "80"], ["70", "60", "50"]),
    ("Leona", "Eclipse", ["14", "13", "12", "11"], ["13", "12", "11", "10"]),
    ("Nasus", "Fury of the Sands", ["75", "70", "65"], ["90", "80", "70"]),
    ("Warwick", "Infinite Duress", ["80", "70", "60"], ["100", "90", "80"]),
]

# Changes the data model cannot express, recorded rather than dropped.
UNAPPLIED = [
    "Kog'Maw / Living Artillery range 12/14/16 -> 11/13/15 (our text stores range "
    "as 'increases by 200 units with each rank', with no per-rank values)",
    "Leona + Rumble health per level: applied as the +8 delta rather than Riot's "
    "absolute 128, because our growth basis differs from theirs (see CHAMP_GROWTH)",
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
            ok(f"{name} base {key} {old} -> {new}")
        else:
            bad(f"{name} base {key} expected {old}, found {stat and stat.get('base')}")

    print("\nGROWTH")
    for name, key, old, new in CHAMP_GROWTH:
        stat = ((champs.get(name) or {}).get("baseStats") or {}).get(key)
        if stat and stat.get("perLevel") == old:
            stat["perLevel"] = new
            stat["lvl15"] = stat["base"] + new * 14
            ok(f"{name} {key} per level {old} -> {new} (lvl15 now {stat['lvl15']})")
        else:
            bad(f"{name} {key} perLevel expected {old}, found {stat and stat.get('perLevel')}")

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
              "be 7.2c while carrying 7.2b numbers.")
        raise SystemExit(1)

    (DATA / "champions_wr.json").write_text(
        json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    # The patch label the whole site reads.
    for path in ("champion_stat_overrides.json", "item_stat_rules.json"):
        p = DATA / path
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        if "targetPatch" in d:
            d["targetPatch"] = PATCH
            p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("\nwritten. Now re-run: python -m scripts.export_engine_data")


if __name__ == "__main__":
    main()
