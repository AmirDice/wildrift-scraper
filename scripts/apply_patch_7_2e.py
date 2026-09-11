"""Apply patch 7.2e balance changes on top of the 7.2 / a / b / c / d data.

Transcribed from the official notes, not from wr-meta, which lags:

    https://wildrift.leagueoflegends.com/en-us/news/game-updates/wild-rift-patch-notes-72e/

Published 2026-09-09. Five champions: Vi, Janna, Swain, Nautilus, Malphite.
Three items we carry: Seeker's Armguard, Eclipse, Unending Despair. No rune
changes.

NOTE ON WIN RATES. This patch gets its item and ability data applied and does
NOT get a ladder collection -- see web-next/src/lib/announcement.ts. That is a
deliberate split, and it is the normal shape of this site anyway: the patch
label follows the pipeline within hours, win rates only move when the boards
are re-scraped. PatchLagNotice already says so on every page that shows a win
rate, and it will now say it about 7.2e.

Every edit asserts the CURRENT value first. If the source data shifts under us
(a re-scrape, a 7.2f), the assert fails loudly rather than silently doing
nothing and leaving a nerf unlanded.

Run:
    python -m scripts.apply_patch_7_2e            # dry run
    python -m scripts.apply_patch_7_2e --write
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

PATCH = "7.2e"

# (champion, stat_key, old_per_level, new_per_level)
CHAMP_BASE = [
    # Notes say "Armor per level: 4.3 -> 5". Our scrape holds 4.0, not 4.3;
    # wr-meta rounds the tenth away, the same shape as Mordekaiser's cooldown
    # halves in 7.2d. The POST value is unambiguous, so 5 is written and the
    # rounding clears with it.
    ("Malphite", "armor", 4.0, 5.0),
]

# (champion, ability_name_fragment, old_substring, new_substring)
CHAMP_TEXT = [
    # -- Vi: both ends of Vault Breaker's charge scale down. Our text writes
    # these as "AD" where the notes say "bonus Attack Damage"; the numbers are
    # the same two ratios, so they are matched on the ratio itself.
    ("Vi", "Vault Breaker", "( +80% AD )", "( +60% AD )"),
    ("Vi", "Vault Breaker", "( +160% AD )", "( +120% AD )"),

    # -- Janna: shield base and ratio both up.
    ("Janna", "Eye Of The Storm", "65 / 90 / 115 / 140 ( +45% AP )",
     "80 / 120 / 160 / 200 ( +50% AP )"),

    # -- Swain: the ultimate's AP scaling is cut on both halves. Our scrape
    # holds "10 / 25 / 45" where the notes give 10/25/40 as the pre-patch base.
    # The post-patch sequence is stated exactly, so it is written and the
    # rank-3 discrepancy clears with it; see UNAPPLIED.
    ("Swain", "Demonic Ascension", "10 / 25 / 45 ( +15% AP )",
     "15 / 25 / 35 ( +6% AP )"),
    ("Swain", "Demonic Ascension", "20 / 30 / 40 ( +20% AP )",
     "15 / 30 / 45 ( +10% AP )"),

    # -- Nautilus: shield base and max-health ratio both up.
    ("Nautilus", "Titan's Wrath",
     "65 / 75 / 85 / 95 ( +9% / 10% / 11% / 12% max HP )",
     "70 / 80 / 90 / 100 ( +11% / 12% / 13% / 14% max HP )"),

    # -- Malphite
    ("Malphite", "Seismic Shard", "slowing the target by 15% / 20% / 25% / 30%",
     "slowing the target by 20% / 25% / 30% / 35%"),
    # Thunderclap's CONSECUTIVE-attack damage only. The first-attack line keeps
    # its own 40/60/80/100, so this matches the sequence with its ratios.
    ("Malphite", "Thunderclap",
     "attacks deal 10 / 20 / 30 / 40 ( +20% AP +20% Armor )",
     "attacks deal 20 / 30 / 40 / 50 ( +20% AP +20% Armor )"),
]

# (champion, ability_name_fragment, old_cooldowns, new_cooldowns)
CHAMP_CDS = [
    # The notes call Vi's ultimate "Cease and Desist"; our data, and the game
    # client, call it "Assault and Battery". Same ability, same cooldowns.
    ("Vi", "Assault and Battery", ["60", "55", "50"], ["80", "70", "60"]),
]

# (item_slug, dotted_field_path, old, new)
ITEM_EDITS = [
    ("eclipse", "cost", 3000, 2900),
    ("unending-despair", "stats.hp.value", 200.0, 300.0),
    ("unending-despair", "stats.armor.value", 45.0, 40.0),
    ("unending-despair", "stats.mr.value", 45.0, 40.0),
]

# Passive TEXT edits, which is where cooldowns and shield values live.
# (item_slug, old_substring, new_substring)
ITEM_TEXT = [
    ("seekers-armguard", "(120s Cooldown)", "(150s Cooldown)"),
    ("eclipse", "shield that absorbs damage equal to 140",
     "shield that absorbs damage equal to 150"),
]

# Stats that did not exist on the item before this patch.
# (item_slug, stat_key, value, percent)
ITEM_NEW_STATS = [
    ("unending-despair", "abilityHaste", 10.0, False),
]

# Changes the data model cannot express, recorded rather than dropped.
UNAPPLIED = [
    "Verdant Barrier / Annul passive cooldown 50s -> 65s: we do not carry this "
    "item at all. It is a mid-tier component and data/items.json holds only "
    "completed items plus boots, so there is nothing to edit. The completed "
    "items that share the Annul passive (Banshee's Veil, Edge of Night) are "
    "NOT changed by this patch and are correctly left alone.",
    "Eclipse / Ever Rising Moon bonus-AD ratio 35% -> 40%: our passive text "
    "stores the shield's flat base but truncates before the ratio, so only the "
    "140 -> 150 half is editable. The engine does not model Eclipse's shield "
    "either way (its itemFx carries the %max-HP proc, not the shield), so this "
    "is a display-text gap and not a numbers gap.",
    "Swain / Demonic Ascension pre-patch base: the notes give 10/25/40 and our "
    "scrape holds 10/25/45. The post-patch 15/25/35 is written regardless, so "
    "the data ends up correct whichever of the two was right about rank 3.",
    "Malphite / Armor per level: the notes move 4.3 -> 5 and our scrape held "
    "4.0. Written as 5.",
    "Unending Despair build path (Ruby Crystal -> Kindlegem): the total is "
    "3000 either way and we do not model component paths, so there is nothing "
    "to change. The Ability Haste the new path grants IS applied.",
    "ARAM 'Blood Price' augment and its Pyke exclusion: game-mode only, and "
    "the site models Summoner's Rift.",
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
        # Malphite's change is PER LEVEL, not the level-1 base.
        if stat and stat.get("perLevel") == old:
            stat["perLevel"] = new
            if "base" in stat:
                stat["lvl15"] = stat["base"] + new * 14
            ok(f"{name} {key} perLevel {old} -> {new} (lvl15 now {stat.get('lvl15')})")
        else:
            bad(f"{name} {key} perLevel expected {old}, "
                f"found {stat and stat.get('perLevel')}")

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

    for slug, key, value, percent in ITEM_NEW_STATS:
        it = items.get(slug)
        stats = (it or {}).get("stats")
        if stats is None:
            bad(f"{slug} has no stats block for new {key}")
        elif key in stats:
            bad(f"{slug} {key} already exists ({stats[key]}); expected it to be new")
        else:
            stats[key] = {"value": value, "percent": percent}
            ok(f"{slug} NEW stat {key} = {value}")

    for slug, old, new in ITEM_TEXT:
        it = items.get(slug)
        passives = (it or {}).get("passives") or []
        hit = False
        for i, p in enumerate(passives):
            if isinstance(p, str) and old in p:
                passives[i] = p.replace(old, new)
                hit = True
        ok(f"{slug} text {old!r} -> {new!r}") if hit else \
            bad(f"{slug} text {old!r} not found")

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
              "be 7.2e while carrying 7.2d numbers.")
        raise SystemExit(1)

    (DATA / "champions_wr.json").write_text(
        json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA / "items.json").write_text(
        json.dumps(items_raw, ensure_ascii=False, indent=2), encoding="utf-8")

    # The patch label the whole site reads.
    for path in ("champion_stat_overrides.json", "item_stat_rules.json",
                 "stat_rules.json"):
        p = DATA / path
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        if "targetPatch" in d:
            d["targetPatch"] = PATCH
            p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
            print(f"  targetPatch -> {PATCH} in data/{path}")

    print("\nwritten. Now re-run, in order:")
    print('  python -m scripts.extract_formulas --only "Vi,Janna,Swain,Nautilus,Malphite"')
    print("  python -m scripts.audit_formulas")
    print("  python -m scripts.export_champion_details")
    print("  python -m scripts.export_engine_data")
    print("  bump web-next/src/lib/build-cache.ts, then redeploy the advisor")


if __name__ == "__main__":
    main()
