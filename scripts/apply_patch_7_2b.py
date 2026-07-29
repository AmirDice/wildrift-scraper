"""Apply patch 7.2b balance changes on top of the 7.2 / 7.2a data.

Transcribed from the official notes, not from wr-meta, which lags:

    https://wildrift.leagueoflegends.com/en-sg/news/game-updates/wild-rift-patch-notes-7-2b/

RANKED ONLY. The 7.2b notes carry a long AAA ARAM / ARAM section (Bard, Rakan,
Irelia, Nocturne, Diana, Riven, Vex, Kennen, Zilean, Xin Zhao, Jarvan IV, Ahri,
Galio, Lissandra, Pyke, Nasus and the mode's own augments). None of it applies
to the mode this site models, and the same exclusion was made for 7.2a.

Every edit asserts the CURRENT value first. If the source data shifts under us
(a re-scrape, a 7.2c), the assert fails loudly rather than silently doing
nothing and leaving a nerf unlanded.

Run:
    python -m scripts.apply_patch_7_2b            # dry run
    python -m scripts.apply_patch_7_2b --write
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

PATCH = "7.2b"

# (slug, old_cost, new_cost)
COST_CHANGES = [
    ("iceborn-gauntlet", 3100, 3000),
    ("navori-quickblades", 2800, 2700),
]

# (slug, stat_key, old, new)
STAT_CHANGES = [
    ("iceborn-gauntlet", "hp", 250.0, 300.0),
    ("lord-dominiks-regard", "ad", 25.0, 30.0),
]

# (slug, stat_key, new) -- the stat is ABSENT from our scrape, so there is no
# old value to assert. Magnetic Blaster's notes say "Attack Damage: 25 -> 30",
# but our 7.2 data carries only crit and attack speed for it: the scrape missed
# the AD entirely. The post-patch value is known, so it is set rather than
# adjusted, and the gap is recorded here rather than hidden.
STAT_ADDITIONS = [
    ("magnetic-blaster", "ad", 30.0),
]

# (slug, old_substring, new_substring) -- item passive text, so the effect
# extractor reads 7.2b numbers rather than 7.2 ones.
TEXT_CHANGES = [
    ("ludens-echo", "an additional 110 + 10% [ap] magic damage",
     "an additional 140 + 15% [ap] magic damage"),
    ("ludens-echo", "(10s Cooldown)", "(9s Cooldown)"),
]

# (rune_name, old_substring, new_substring)
RUNE_TEXT = [
    ("Botanist", "gain 30 gold", "gain 10 gold"),
]

# (champion, stat_key, old, new) -- base stats
CHAMP_BASE = [
    ("Jayce", "armor", 46.0, 37.0),
    ("Nidalee", "armor", 46.0, 37.0),
    ("Nidalee", "mr", 40.0, 36.0),
]

# (champion, ability_name_fragment, old_substring, new_substring)
CHAMP_TEXT = [
    ("Nidalee", "Prowl", "15%", "10%"),          # both brush and marked-enemy lines
    ("Ambessa", "Public Execution", "30% / 40% / 50%", "10% / 20% / 30%"),
    ("Aurora", "Twofold Hex", "35 / 65 / 95 / 125", "40 / 70 / 100 / 130"),
    ("Aurora", "Twofold Hex", "30% AP", "33% AP"),
    ("Aurora", "The Weirding", "75 / 125 / 175 / 225", "80 / 130 / 180 / 230"),
    ("Sona", "Aria of Perseverance", "45 / 60 / 75 / 90", "35 / 50 / 65 / 80"),
    ("Ekko", "Z-Drive Resonance", "70% AP", "80% AP"),
    ("Kayle", "Radiant Blast", "70 / 120 / 170 / 220", "60 / 100 / 140 / 180"),
    ("Kayle", "Celestial Blessing", "95 / 125 / 155 / 185", "60 / 95 / 130 / 165"),
    ("Kayle", "Celestial Blessing", "40% AP", "30% AP"),
    ("Hecarim", "Rampage", "30%", "18%"),
    ("Lee Sin", "Safeguard", "80 / 140 / 200 / 260", "100 / 160 / 220 / 280"),
    # The text percent-signs each rank ("16% / 24% / ..."), not just the last.
    ("Lee Sin", "Safeguard", "16% / 24% / 32% / 40%", "20% / 30% / 40% / 50%"),
    # Our scrape reads 70 / 100 / 210 / 280; the notes say the PRE-patch value
    # was 70/140/210/280, so rank 2 was wrong before this patch touched it.
    # Matching on what we actually have and writing the post-patch sequence
    # fixes the typo and applies the nerf in one edit.
    ("Zilean", "Time Bomb", "70 / 100 / 210 / 280", "60 / 125 / 190 / 255"),
]

# (champion, ability_name_fragment, old_cooldowns, new_cooldowns)
CHAMP_CDS = [
    ("Sona", "Crescendo", ["80", "70", "60"], ["80", "75", "70"]),
    ("Zilean", "Chronoshift", ["100", "85", "70"], ["110", "95", "80"]),
]

# Changes the data model cannot express, recorded rather than dropped.
UNAPPLIED = [
    "Kayle / Radiant Blast + Celestial Blessing mana costs (we store no mana costs)",
    "Ambessa / Public Execution base damage 20/30/40% -> 10/17.5/25% of Health lost "
    "(the text carries no percent-of-health-lost term to edit)",
    "Ekko / Parallel Convergence missing-Health 2% + 0.015% AP -> 3% + 0.025% AP "
    "(not present in the scraped text)",
    "Champion Bounty System: bounty accrual per gold 20 -> 25, per kill 3 -> 3.5 "
    "(no bounty model)",
    "AAA ARAM / ARAM champion and augment changes (out of scope: ranked only)",
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

    # ---- items -------------------------------------------------------------
    items = json.loads((DATA / "items.json").read_text(encoding="utf-8"))
    by_slug = {i["slug"]: i for i in items}

    print("ITEMS")
    for slug, old, new in COST_CHANGES:
        item = by_slug.get(slug)
        if item and item.get("cost") == old:
            item["cost"] = new
            ok(f"{slug} cost {old} -> {new}")
        else:
            bad(f"{slug} cost expected {old}, found {item and item.get('cost')}")

    for slug, key, old, new in STAT_CHANGES:
        stat = (by_slug.get(slug, {}).get("stats") or {}).get(key)
        if stat and stat.get("value") == old:
            stat["value"] = new
            ok(f"{slug} {key} {old} -> {new}")
        else:
            bad(f"{slug} {key} expected {old}, found {stat and stat.get('value')}")

    for slug, key, new in STAT_ADDITIONS:
        item = by_slug.get(slug)
        if not item:
            bad(f"{slug} not found"); continue
        stats = item.setdefault("stats", {})
        if key in stats:
            bad(f"{slug} {key} already present ({stats[key].get('value')}); "
                f"expected it missing -- check the notes against the scrape")
        else:
            stats[key] = {"value": new, "percent": False}
            ok(f"{slug} {key} set to {new} (absent from the scrape)")

    for slug, old, new in TEXT_CHANGES:
        item = by_slug.get(slug)
        hit = False
        for i, passive in enumerate(item.get("passives") or []) if item else []:
            if old in passive:
                item["passives"][i] = passive.replace(old, new)
                hit = True
        ok(f"{slug} text {old!r} -> {new!r}") if hit else bad(f"{slug} text {old!r} not found")

    # ---- runes -------------------------------------------------------------
    print("\nRUNES")
    runes = json.loads((DATA / "wrmeta_runes.json").read_text(encoding="utf-8"))
    for name, old, new in RUNE_TEXT:
        rune = next((r for r in runes if r.get("name") == name), None)
        if rune and old in (rune.get("text") or ""):
            rune["text"] = rune["text"].replace(old, new)
            ok(f"{name}: {old!r} -> {new!r}")
        else:
            bad(f"{name}: {old!r} not found")

    # ---- champions ---------------------------------------------------------
    print("\nCHAMPIONS")
    raw = json.loads((DATA / "champions_wr.json").read_text(encoding="utf-8"))
    champ_list = list(raw.values()) if isinstance(raw, dict) else raw
    champs = {c["name"]: c for c in champ_list}

    for name, key, old, new in CHAMP_BASE:
        stat = ((champs.get(name) or {}).get("baseStats") or {}).get(key)
        if stat and stat.get("base") == old:
            stat["base"] = new
            # lvl15 is base + 14 growths; keep them consistent.
            if "perLevel" in stat:
                stat["lvl15"] = new + stat["perLevel"] * 14
            ok(f"{name} base {key} {old} -> {new}")
        else:
            bad(f"{name} base {key} expected {old}, found {stat and stat.get('base')}")

    def abilities(name):
        champ = champs.get(name) or {}
        return (champ.get("abilities") or []) + [
            a for f in (champ.get("forms") or []) for a in (f.get("abilities") or [])]

    for name, frag, old, new in CHAMP_TEXT:
        hit = False
        for a in abilities(name):
            if frag.lower() in (a.get("name") or "").lower() and old in (a.get("text") or ""):
                a["text"] = a["text"].replace(old, new)
                hit = True
        ok(f"{name}/{frag}: {old!r} -> {new!r}") if hit else \
            bad(f"{name}/{frag}: {old!r} not found")

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
              "be 7.2b while carrying 7.2 numbers.")
        raise SystemExit(1)

    (DATA / "items.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA / "wrmeta_runes.json").write_text(
        json.dumps(runes, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA / "champions_wr.json").write_text(
        json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    # The patch label the whole site reads.
    for path in ("champion_stat_overrides.json", "item_stat_rules.json"):
        p = DATA / path
        d = json.loads(p.read_text(encoding="utf-8"))
        if "targetPatch" in d:
            d["targetPatch"] = PATCH
            p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nwritten. Now re-run: python -m scripts.export_engine_data")


if __name__ == "__main__":
    main()
