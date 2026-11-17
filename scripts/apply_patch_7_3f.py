"""Apply Wild Rift patch 7.3f to the site's data.

Same discipline as scripts/apply_patch_7_3d.py, which this copies: every
change quotes a line of data/patch_notes_7_3f.json (scripts/parse_patch_notes.py
from Riot's page), the COVERAGE table accounts for every line in that parse,
each edit names RIOT'S "before" and REPORTS -- not aborts -- when ours was
something else, and every file is rendered before any is written.

7.3e is not applied by anything: its notes are AAA ARAM augments only.
Sylas, released in 7.3f, is added separately (scripts/add_sylas.py).

Judgment calls, reported again at run time:

    Irelia Ionian Fervor, Lucian Piercing Light   Riot names the ratio BONUS
        Attack Damage; ours used total AD. The formula's stat is changed to
        bonusAd along with the number.
    Lucian Piercing Light   the formula still carried a pre-7.3 per-rank AD
        ratio (65/85/105/125%) and a note saying so; both are replaced by
        Riot's single 120% bonus AD.
    Kassadin Force Pulse   ours already said 50% AP, Riot's "after"; no edit.

Not modelled, recorded in COVERAGE: Smite burn and Conservation gold (the
site has no jungle model), support-item gold income (Soulcast gold is text
only), and the AAA ARAM, QoL and bug-fix sections.

    python -m scripts.apply_patch_7_3f            # report only
    python -m scripts.apply_patch_7_3f --write    # apply

Then, per the patch checklist: export_engine_data, export_champion_details,
export_items, fetch_riot_patch_history.mjs, bump the build cache, redeploy
the advisor.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
NOTES = DATA / "patch_notes_7_3f.json"
PATCH = "7.3f"
PREV = "7.3d"

FILES = {
    "items": DATA / "items.json",
    "item_engine": DATA / "item_engine.json",
    "item_fx": DATA / "item_engine_overrides.json",
    "champions": DATA / "champions_wr.json",
    "formulas": DATA / "ability_formulas.json",
    "attack_speed": DATA / "champion_attack_speed.json",
    "item_rules": DATA / "item_stat_rules.json",
    "rune_rules": DATA / "rune_stat_rules.json",
    "stat_overrides": DATA / "champion_stat_overrides.json",
}

drift: list[str] = []
missing: list[str] = []
done: list[str] = []


def load(key):
    return json.loads(FILES[key].read_text(encoding="utf-8"))


def by_name(rows):
    return {r["name"]: r for r in rows}


def field(label, obj, keys, before, after):
    """Set obj[...keys] to `after`, reporting if it was not Riot's `before`."""
    cur = obj
    for k in keys[:-1]:
        cur = cur[k]
    found = cur.get(keys[-1]) if isinstance(cur, dict) else cur[keys[-1]]
    if found != before:
        drift.append(f"{label}: Riot's before was {before!r}, ours was {found!r}")
    cur[keys[-1]] = after
    done.append(label)


def text(label, obj, key, old, new):
    """Replace `old` with `new` in a text field, exactly once."""
    s = obj.get(key) or ""
    n = s.count(old)
    if n != 1:
        missing.append(f"{label}: {old!r} occurs {n} times")
        return
    obj[key] = s.replace(old, new)
    done.append(label)


def reword_note(label, ability, old, new):
    """Rewrite an existing unmodeled note that quotes a number the patch moved."""
    notes = ability.get("unmodeled") or []
    hits = [i for i, s in enumerate(notes) if old in s]
    if len(hits) != 1:
        missing.append(f"{label}: {old!r} in {len(hits)} unmodeled notes")
        return
    notes[hits[0]] = notes[hits[0]].replace(old, new)
    done.append(label)


def ability(champ, slot):
    for a in champ["abilities"]:
        if str(a.get("slot")) == slot:
            return a
    raise KeyError(f"{champ['name']} has no slot {slot}")


def dmg(formula_ability, name):
    for d in formula_ability["damage"]:
        if d["name"] == name:
            return d
    raise KeyError(f"no damage entry {name!r}")


def passive_line(item, prefix):
    for i, p in enumerate(item["passives"]):
        if p.startswith(prefix):
            return i
    raise KeyError(f"{item['name']} has no passive {prefix!r}")


def passive_text(label, item, prefix, old, new):
    idx = passive_line(item, prefix)
    holder = {"t": item["passives"][idx]}
    text(label, holder, "t", old, new)
    item["passives"][idx] = holder["t"]


def lvl15(stat):
    """Level-15 total, the way every baseStats block derives it."""
    return round(stat["base"] + 14 * stat["perLevel"], 4)


def base_stat(label, champ, stat, key, before, after):
    st = champ["baseStats"][stat]
    field(label, st, [key], before, after)
    st["lvl15"] = lvl15(st)


# ------------------------------------------------------------------- items --
def apply_items(items, item_engine, item_fx):
    I = by_name(items)

    # Luden's Echo (the override carries the live numbers; item_engine's
    # 110/10 base is overridden key by key and stays as extracted)
    le = I["Luden's Echo"]
    passive_text("Luden's first projectile (text)", le, "Echo",
                 "deals 75 + 8% [ap] magic damage", "deals 80 + 9% [ap] magic damage")
    passive_text("Luden's subsequent projectile (text)", le, "Echo",
                 "additional 20 + 1.2% [ap] magic damage", "additional 22.5 + 1.4% [ap] magic damage")
    fx = item_fx["ludens-echo"]
    field("Luden's first projectile (engine)", fx, ["burstProcFlat"], 75, 80)
    field("Luden's first projectile AP (engine)", fx, ["burstProcApPct"], 8, 9)
    field("Luden's area projectile (engine)", fx, ["burstAoeFlat"], 75, 80)
    field("Luden's area projectile AP (engine)", fx, ["burstAoeApPct"], 8, 9)
    field("Luden's subsequent projectile (engine)", fx, ["burstPrimaryMissingFlat"], 20, 22.5)
    field("Luden's subsequent projectile AP (engine)", fx, ["burstPrimaryMissingApPct"], 1.2, 1.4)
    text("Luden's _why", fx, "_why",
         "Echo is 75 + 8% AP to the primary and up to five nearby targets, with 20 + 1.2% AP",
         "Echo is 80 + 9% AP to the primary and up to five nearby targets, with 22.5 + 1.4% AP")

    # Rod of Ages
    ra = I["Rod of Ages"]
    field("Rod of Ages price", ra, ["cost"], 2700, 2600)
    passive_text("Rod of Ages Eternity (text)", ra, "Eternity",
                 "equal to 15% of the damage taken", "equal to 20% of the damage taken")
    passive_text("Rod of Ages Veteran per stack (text)", ra, "Veteran",
                 "Each stack provides 15 Health, 30 Mana", "Each stack provides 20 Health, 40 Mana")
    passive_text("Rod of Ages Veteran total (text)", ra, "Veteran",
                 "providing 150 Health, 300 Mana", "providing 200 Health, 400 Mana")
    field("Rod of Ages Veteran health (engine)", item_engine["rod-of-ages"], ["hpFlatPassive"], 150, 200)
    field("Rod of Ages Veteran mana (engine)", item_engine["rod-of-ages"], ["manaFlatPassive"], 300, 400)

    # Lich Bane
    lb = I["Lich Bane"]
    field("Lich Bane movement speed", lb, ["stats", "moveSpeed", "value"], 5, 6)
    passive_text("Lich Bane Spellblade (text)", lb, "Spellblade",
                 "+ 45% AP [ap]", "+ 50% AP [ap]")
    field("Lich Bane Spellblade AP (engine)", item_engine["lich-bane"], ["spellbladeApPct"], 45, 50)

    field("Morellonomicon price", I["Morellonomicon"], ["cost"], 2650, 2550)

    # Hextech Rocketbelt
    hr = I["Hextech Rocketbelt"]
    field("Rocketbelt price", hr, ["cost"], 2700, 2650)
    field("Rocketbelt health", hr, ["stats", "hp", "value"], 250, 300)
    passive_text("Rocketbelt Protobelt (text)", hr, "Protobelt",
                 "dealing 100 plus 10% [ap] magic damage", "dealing 110 plus 15% [ap] magic damage")
    field("Rocketbelt Protobelt (engine)", item_engine["hextech-rocketbelt"], ["burstProcFlat"], 100, 110)
    field("Rocketbelt Protobelt AP (engine)", item_engine["hextech-rocketbelt"], ["burstProcApPct"], 10, 15)

    field("Liandry's Torment AP", I["Liandry's Torment"], ["stats", "ap", "value"], 70, 60)

    for name in ("Bulwark of the Mountain", "Black Mist Scythe"):
        passive_text(f"{name} Soulcast gold (text)", I[name], "Soulcast",
                     "gains 75 gold", "gains 60 gold")

    field("Eclipse AD", I["Eclipse"], ["stats", "ad", "value"], 65, 60)
    gd = I["Goredrinker"]
    field("Goredrinker AD", gd, ["stats", "ad", "value"], 40, 45)
    field("Goredrinker health", gd, ["stats", "hp", "value"], 350, 400)


#: The two engine item files are laid out by hand; edit them as text.
ITEM_ENGINE_EDITS = [
    ('"rod-of-ages": {\n    "hpFlatPassive": 150,\n    "manaFlatPassive": 300,',
     '"rod-of-ages": {\n    "hpFlatPassive": 200,\n    "manaFlatPassive": 400,'),
    ('"lich-bane": {\n    "spellbladeBaseAdPct": 75,\n    "spellbladeApPct": 45',
     '"lich-bane": {\n    "spellbladeBaseAdPct": 75,\n    "spellbladeApPct": 50'),
    ('"hextech-rocketbelt": {\n    "burstProcFlat": 100,\n    "burstProcApPct": 10',
     '"hextech-rocketbelt": {\n    "burstProcFlat": 110,\n    "burstProcApPct": 15'),
]
ITEM_FX_EDITS = [
    ('"burstProcFlat": 75,\n    "burstProcApPct": 8,\n    "burstAoeFlat": 75,\n    "burstAoeApPct": 8,\n'
     '    "burstAoeTargets": 5,\n    "burstPrimaryMissingFlat": 20,\n    "burstPrimaryMissingApPct": 1.2,',
     '"burstProcFlat": 80,\n    "burstProcApPct": 9,\n    "burstAoeFlat": 80,\n    "burstAoeApPct": 9,\n'
     '    "burstAoeTargets": 5,\n    "burstPrimaryMissingFlat": 22.5,\n    "burstPrimaryMissingApPct": 1.4,'),
    ("Echo is 75 + 8% AP to the primary and up to five nearby targets, with 20 + 1.2% AP",
     "Echo is 80 + 9% AP to the primary and up to five nearby targets, with 22.5 + 1.4% AP"),
]


def hand_edit(name: str, raw: str, edits) -> str:
    for old, new in edits:
        n = raw.count(old)
        if n != 1:
            raise SystemExit(f"{name}: {old[:60]!r} occurs {n} times; nothing written")
        raw = raw.replace(old, new)
    return raw


# --------------------------------------------------------------- champions --
def apply_champions(champions, formulas):
    C = by_name(champions)
    F = formulas

    # Kalista
    k = C["Kalista"]
    text("Kalista Pierce (text)", ability(k, "1"), "text",
         "dealing 70 / 135 / 200 / 265 ( +110% AD )", "dealing 30 / 110 / 190 / 270 ( +110% AD )")
    field("Kalista Pierce base", dmg(F["Kalista"]["abilities"]["1"], "Pierce"), ["base"],
          [70, 135, 200, 265], [30, 110, 190, 270])

    # Viktor
    v = C["Viktor"]
    fv = F["Viktor"]["abilities"]
    text("Viktor Siphon Power (text)", ability(v, "1"), "text",
         "dealing 55 / 70 / 85 / 100 ( +35% AP ) magic damage and gaining",
         "dealing 50 / 70 / 90 / 110 ( +40% AP ) magic damage and gaining")
    sp = dmg(fv["1"], "Siphon Power Blast")
    field("Viktor Siphon Power base", sp, ["base"], [45, 60, 75, 90], [50, 70, 90, 110])
    field("Viktor Siphon Power AP", sp, ["ratios", 0, "pct"], 30, 40)
    e = ability(v, "3")
    text("Viktor Hextech Ray (text)", e, "text",
         "dealing 75 / 120 / 165 / 210 ( +30% AP )", "dealing 70 / 115 / 160 / 205 ( +40% AP )")
    text("Viktor Blastquake (text)", e, "text",
         "dealing 30 / 70 / 110 / 150 ( +60% AP )", "dealing 20 / 60 / 100 / 140 ( +75% AP )")
    beam = dmg(fv["3"], "Death Ray Beam")
    field("Viktor Hextech Ray base", beam, ["base"], [75, 120, 165, 210], [70, 115, 160, 205])
    field("Viktor Hextech Ray AP", beam, ["ratios", 0, "pct"], 30, 40)
    bq = dmg(fv["3"], "Death Ray Explosion")
    field("Viktor Blastquake base", bq, ["base"], [30, 70, 110, 150], [20, 60, 100, 140])
    field("Viktor Blastquake AP", bq, ["ratios", 0, "pct"], 60, 75)
    text("Viktor Arcane Storm DoT (text)", ability(v, "4"), "text",
         "50 / 90 / 130 ( +40% AP ) magic damage to enemies within it every second",
         "50 / 90 / 130 ( +35% AP ) magic damage to enemies within it every second")
    field("Viktor Arcane Storm DoT AP", dmg(fv["4"], "Chaos Storm DoT"), ["ratios", 0, "pct"], 40, 35)

    # Shen
    s = C["Shen"]
    fs = F["Shen"]["abilities"]["4"]
    field("Shen Stand United cooldown (text)", ability(s, "4"), ["cooldowns"],
          ["110", "100", "90"], ["120", "110", "100"])
    field("Shen Stand United cooldown", fs, ["cooldowns"], [110, 100, 90], [120, 110, 100])
    text("Shen Stand United shield (text)", ability(s, "4"), "text",
         "for 170 / 340 / 510 ( +135% AP", "for 160 / 260 / 360 ( +135% AP")
    field("Shen Stand United shield", fs, ["defensive", 0, "base"], [170, 340, 510], [160, 260, 360])

    # Irelia
    ir = C["Irelia"]
    fi = F["Irelia"]["abilities"]
    p = ability(ir, "P")
    text("Irelia Ionian Fervor attack speed (text)", p, "text",
         "grant 3% - 17% bonus Attack Speed", "grant 11% - 25% bonus Attack Speed")
    text("Irelia Ionian Fervor damage (text)", p, "text",
         "25 - 150 ( +30% AD ) magic damage", "10 - 80 ( +20% bonus AD ) magic damage")
    on_hit = dmg(fi["P"], "Ionian Fervor On-Hit")
    field("Irelia Ionian Fervor damage base", on_hit, ["base"], [25, 150], [10, 80])
    field("Irelia Ionian Fervor damage ratio (now bonus AD)", on_hit, ["ratios"],
          [{"stat": "bonusAd", "pct": 30}], [{"stat": "bonusAd", "pct": 20}])
    field("Irelia Ionian Fervor attack speed per stack (max)", fi["P"], ["steroids", 0, "pct"], 17, 25)
    reword_note("Irelia Ionian Fervor (note)", fi["P"],
                "scales 3-17% based on level", "scales 11-25% based on level")
    q = ability(ir, "1")
    text("Irelia Bladesurge ratio (text)", q, "text", "( +65% AD )", "( +80% AD )")
    text("Irelia Bladesurge healing (text)", q, "text",
         "11% / 14% / 17% / 20% AD", "9% / 11% / 13% / 15% AD")
    field("Irelia Bladesurge AD ratio", dmg(fi["1"], "Bladesurge"), ["ratios", 0, "pct"], 65, 80)
    field("Irelia Bladesurge healing (rank 1)", fi["1"], ["defensive", 0, "ratios", 0, "pct"], 11, 9)
    reword_note("Irelia Bladesurge healing (note)", fi["1"], "11/14/17/20% AD", "9/11/13/15% AD")

    # Graves, Akshan, Kassadin, Yasuo: base stats
    base_stat("Graves armor", C["Graves"], "armor", "base", 36, 40)
    base_stat("Graves armor per level", C["Graves"], "armor", "perLevel", 4.5, 5)
    base_stat("Akshan magic resist", C["Akshan"], "mr", "base", 30, 34)
    base_stat("Kassadin magic resist", C["Kassadin"], "mr", "base", 38, 34)
    base_stat("Yasuo armor per level", C["Yasuo"], "armor", "perLevel", 4.3, 5.2)

    # Lucian
    lu = C["Lucian"]
    fl = F["Lucian"]["abilities"]
    text("Lucian Lightslinger (text)", ability(lu, "P"), "text",
         "deals 40% / 50% / 60% physical damage", "deals 45% / 55% / 65% physical damage")
    field("Lucian Lightslinger second shot (rank 1)", dmg(fl["P"], "Lightslinger Second Shot"),
          ["ratios", 0, "pct"], 40, 45)
    reword_note("Lucian Lightslinger (note)", fl["P"], "scales to 50% and 65% AD", "scales to 55% and 65% AD")
    text("Lucian Piercing Light (text)", ability(lu, "1"), "text", "( +100% AD )", "( +120% bonus AD )")
    field("Lucian Piercing Light ratio (bonus AD, one value)", dmg(fl["1"], "Piercing Light"), ["ratios"],
          [{"stat": "bonusAd", "pct": 100}], [{"stat": "bonusAd", "pct": 120}])
    field("Lucian Piercing Light stale per-rank note", fl["1"], ["unmodeled"],
          ["AD ratio scales with rank: 65%/85%/105%/125%."], [])

    # Rumble
    ru = C["Rumble"]
    fr = F["Rumble"]["abilities"]
    text("Rumble Overheated attacks (text)", ability(ru, "P"), "text", "5 ( +20% AP )", "5 ( +25% AP )")
    field("Rumble Overheated attacks AP", dmg(fr["P"], "Overheated Empowered Attacks"),
          ["ratios", 0, "pct"], 20, 25)
    text("Rumble The Equalizer (text)", ability(ru, "4"), "text",
         "700 / 1050 / 1400 ( +200% AP )", "800 / 1200 / 1600 ( +220% AP )")
    eq = dmg(fr["4"], "The Equalizer")
    field("Rumble The Equalizer base", eq, ["base"], [700, 1050, 1400], [800, 1200, 1600])
    field("Rumble The Equalizer AP", eq, ["ratios", 0, "pct"], 200, 220)

    # Kassadin Force Pulse: ours already carries Riot's "after"
    field("Kassadin Force Pulse AP", dmg(F["Kassadin"]["abilities"]["3"], "Force Pulse"),
          ["ratios", 0, "pct"], 60, 50)

    # Yasuo
    text("Yasuo Sweeping Blade (text)", ability(C["Yasuo"], "3"), "text",
         "dealing 70 / 80 / 90 / 100 ( +20% bonus AD", "dealing 70 / 90 / 110 / 130 ( +20% bonus AD")
    field("Yasuo Sweeping Blade base", dmg(F["Yasuo"]["abilities"]["3"], "Sweeping Blade"), ["base"],
          [70, 80, 90, 100], [70, 90, 110, 130])


# ----------------------------------------------------------------- writers --
def render(key: str, path: Path, data) -> bytes:
    raw_bytes = path.read_bytes()
    crlf = b"\r\n" in raw_bytes
    raw = raw_bytes.decode("utf-8").replace("\r\n", "\n")
    if key in ("item_fx", "item_engine"):
        new = hand_edit(path.name, raw, ITEM_FX_EDITS if key == "item_fx" else ITEM_ENGINE_EDITS)
        if json.loads(new) != data:
            raise SystemExit(f"{path.name}: the text edit does not match the intended change; "
                             f"nothing written")
    else:
        tail = "\n" if raw.endswith("\n") else ""
        new = json.dumps(data, indent=2, ensure_ascii=False) + tail
    if crlf:
        new = new.replace("\n", "\r\n")
    return new.encode("utf-8")


# ---------------------------------------------------------------- coverage --
COVERAGE = {
    "KALISTA": "applied", "VIKTOR": "applied", "SHEN": "applied", "IRELIA": "applied",
    "GRAVES": "applied", "AKSHAN": "applied", "LUCIAN": "applied", "RUMBLE": "applied",
    "KASSADIN": "applied", "YASUO": "applied",
    "Discordic Echo": "applied", "Rod of Ages": "applied", "Eternity": "applied",
    "Veteran": "applied", "Lich Bane": "applied", "Spell Blade": "applied",
    "Morellonomicon": "applied", "Hextech Rocketbelt": "applied", "Protobelt": "applied",
    "Liandry's Torment": "applied", "Soulcast": "applied (text; gold income is not modelled)",
    "Eclipse": "applied", "Goredrinker": "applied",
    "QOL Improvements": "not modelled: AAA ARAM sound effects",
    "Battle Arsenal": "not modelled: AAA ARAM bug fix",
}
#: Sections whose lines are mode-only or outside the site's model. Smite and
#: Conservation carry their numbers in notes, not lines, so they never reach
#: the coverage check; they are listed in the report instead.
SKIP_SECTIONS = ("GAME MODE CHANGES", "AAA ARAM")
NOT_MODELLED_NOTES = ["Smite burn damage and resist ratios (no jungle model)",
                      "Conservation gold (no jungle model)"]


def check_coverage(notes) -> list[str]:
    gaps = []
    for blade in notes["blades"]:
        if blade["kind"] == "champion":
            if blade["champion"] not in COVERAGE:
                gaps.append(f"champion {blade['champion']}")
            continue
        for b in blade["blocks"]:
            if not b.get("lines"):
                continue
            path = b.get("path") or [b["title"]]
            if b["title"] in COVERAGE or any(s in path for s in SKIP_SECTIONS):
                continue
            gaps.append(f"{' > '.join(path)}: {b['lines']}")
    return gaps


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true", help="apply; default is a dry run")
    args = ap.parse_args(argv)

    notes = json.loads(NOTES.read_text(encoding="utf-8"))
    gaps = check_coverage(notes)
    if gaps:
        print(f"lines in the {PATCH} notes that this script does not account for:")
        for g in gaps:
            print("   ", g)
        return 2

    data = {k: load(k) for k in FILES}
    apply_items(data["items"], data["item_engine"], data["item_fx"])
    apply_champions(data["champions"], data["formulas"])
    field("champion_attack_speed.json patch", data["attack_speed"], ["patch"], PREV, PATCH)
    for k in ("item_rules", "rune_rules", "stat_overrides"):
        field(f"{FILES[k].name} targetPatch", data[k], ["targetPatch"], PREV, PATCH)

    print(f"{len(done)} edits")
    print("not modelled: " + "; ".join(NOT_MODELLED_NOTES))
    if drift:
        print(f"\n{len(drift)} found something other than Riot's 'before' (applied anyway):")
        for d in drift:
            print("   ", d)
    if missing:
        print(f"\n{len(missing)} COULD NOT BE APPLIED:")
        for m in missing:
            print("   ", m)
        print("\nnothing written")
        return 1
    out = {k: render(k, FILES[k], data[k]) for k in FILES}
    if not args.write:
        print("\ndry run: every file rendered, nothing written (use --write)")
        return 0
    for k, blob in out.items():
        FILES[k].write_bytes(blob)
    print(f"\nwrote {len(FILES)} files")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
