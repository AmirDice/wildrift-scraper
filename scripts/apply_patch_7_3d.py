"""Apply Wild Rift patch 7.3d to the site's data.

Same discipline as scripts/apply_patch_7_3b.py, which this copies: every
change quotes a line of data/patch_notes_7_3d.json (scripts/parse_patch_notes.py
from Riot's page), the COVERAGE table accounts for every line in that parse,
each edit names the value we expect to find and REPORTS -- not aborts -- when
what it found was not Riot's "before", and every file is rendered before any
is written.

7.3c is not applied by anything: its notes are AAA ARAM augments only.

Judgment calls, reported again at run time:

    Shyvana "Health Regen per level: 9 -> 12"   our per-level regen is a
        placeholder (1 for 126 champions) and our BASE regen is exactly 9, so
        the 12 goes on base.
    Attack speed per level (Shyvana, Camille, Lee Sin, Akali)   the official
        number lives in champion_attack_speed.json; champions_wr.json carries
        its derived form (ratio x perLevel, and a level-15 total), so both
        are rewritten from the one number.

Not modelled, recorded in COVERAGE: Hand of Baron, minion push advantage and
turret stacking (the site has no structure or minion model), the AAA ARAM
augments, and the K/DA Ahri art update.

    python -m scripts.apply_patch_7_3d            # report only
    python -m scripts.apply_patch_7_3d --write    # apply

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
NOTES = DATA / "patch_notes_7_3d.json"
PATCH = "7.3d"
PREV = "7.3b"

FILES = {
    "items": DATA / "items.json",
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
    """Set obj[...keys] to `after`, reporting if it was not `before`."""
    cur = obj
    for k in keys[:-1]:
        cur = cur[k]
    found = cur.get(keys[-1]) if isinstance(cur, dict) else cur[keys[-1]]
    if found != before:
        drift.append(f"{label}: expected {before!r}, found {found!r}")
    cur[keys[-1]] = after
    done.append(label)


def text(label, obj, key, old, new, patch_before=None):
    """Replace `old` with `new` in a text field, exactly once."""
    s = obj.get(key) or ""
    n = s.count(old)
    if n != 1:
        missing.append(f"{label}: {old!r} occurs {n} times")
        return
    obj[key] = s.replace(old, new)
    if patch_before is not None:
        drift.append(f"{label}: our text said {old!r}; Riot's before was {patch_before!r}")
    done.append(label)


def note(label, ability, line):
    notes = ability.setdefault("unmodeled", [])
    entry = f"{PATCH}: {line}"
    if entry not in notes:
        notes.append(entry)
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


# ------------------------------------------------------------------- items --
def apply_items(items, item_fx):
    I = by_name(items)

    fb = I["Fiendhunter Bolts"]
    passive_text("Fiendhunter crit damage (text)", fb, "Opening Barrage",
                 "for 80% of your normal Critical Strike damage",
                 "for 85% of your normal Critical Strike damage")
    passive_text("Fiendhunter true damage (text)", fb, "Opening Barrage",
                 "deals 15% bonus true damage", "deals 17.5% bonus true damage")
    field("Fiendhunter crit damage (engine)", item_fx["fiendhunter-bolts"],
          ["ultAttackCritMultiplierPct"], 80, 85)
    field("Fiendhunter true damage (engine)", item_fx["fiendhunter-bolts"],
          ["ultAttackTruePctIfCrit"], 15, 17.5)

    field("Divine Sunderer price", I["Divine Sunderer"], ["cost"], 3400, 3300)
    field("Essence Reaver AD", I["Essence Reaver"], ["stats", "ad", "value"], 50, 55)
    field("Whispering Circlet heal and shield power", I["Whispering Circlet"],
          ["stats", "healShieldPower", "value"], 8, 6)
    field("Diadem heal and shield power", I["Diadem of Songs"],
          ["stats", "healShieldPower", "value"], 8, 6)

    sr = I["Stormrazor"]
    passive_text("Stormrazor Bolt (text)", sr, "Bolt",
                 "deals 120 bonus magic damage and grants 45% Movement Speed",
                 "deals 100 bonus magic damage and grants 35% Movement Speed")
    fx = item_fx["stormrazor"]
    field("Stormrazor Bolt damage (engine)", fx, ["burstProcFlat"], 120, 100)
    # msPct is the burst's uptime share, per its own _why: 35% for 1.5s of
    # every 6s is 8.75%, rounded the way the 11 was.
    field("Stormrazor Bolt haste uptime (engine)", fx, ["msPct"], 11, 9)

    # The _why notes quote the numbers too; hand_edit_item_fx makes the same
    # edits to the raw text, and render() checks the two agree.
    text("Stormrazor _why", fx, "_why",
         "Bolt is 120 magic on the Energized attack with 45% Move Speed for 1.5s",
         "Bolt is 100 magic on the Energized attack with 35% Move Speed for 1.5s")
    text("Stormrazor _why uptime", fx, "_why",
         "45% for 1.5s of every 6 is about 11%", "35% for 1.5s of every 6 is about 9%")
    text("Fiendhunter _why", item_fx["fiendhunter-bolts"], "_why",
         "forced crits at 80% normal crit damage, while attacks that would already crit add 15% true damage",
         "forced crits at 85% normal crit damage, while attacks that would already crit add 17.5% true damage")


def hand_edit_item_fx(raw: str) -> str:
    """item_engine_overrides.json is laid out by hand; edit it as text."""
    edits = [
        ('"ultAttackCritMultiplierPct": 80', '"ultAttackCritMultiplierPct": 85'),
        ('"ultAttackTruePctIfCrit": 15', '"ultAttackTruePctIfCrit": 17.5'),
        ("forced crits at 80% normal crit damage, while attacks that would already crit add 15% true damage",
         "forced crits at 85% normal crit damage, while attacks that would already crit add 17.5% true damage"),
        ('"burstProcFlat": 120,\n    "burstProcCdSec": 6,\n    "msPct": 11,',
         '"burstProcFlat": 100,\n    "burstProcCdSec": 6,\n    "msPct": 9,'),
        ("Bolt is 120 magic on the Energized attack with 45% Move Speed for 1.5s",
         "Bolt is 100 magic on the Energized attack with 35% Move Speed for 1.5s"),
        ("45% for 1.5s of every 6 is about 11%", "35% for 1.5s of every 6 is about 9%"),
    ]
    for old, new in edits:
        n = raw.count(old)
        if n != 1:
            raise SystemExit(f"item_engine_overrides.json: {old[:60]!r} occurs {n} times; "
                             f"nothing written")
        raw = raw.replace(old, new)
    return raw


# --------------------------------------------------------------- champions --
def attack_speed_per_level(label, champ, as_table, before, after):
    row = as_table["champions"][champ["name"]]
    field(f"{label} attack speed per level", row, ["attackSpeedPerLevel"], before, after)
    st = champ["baseStats"]["attackSpeed"]
    derived = round(row["attackSpeedRatio"] * before, 5)
    if abs(st["perLevel"] - derived) > 1e-4:
        drift.append(f"{label} baseStats attackSpeed.perLevel: expected {derived}, "
                     f"found {st['perLevel']}")
    st["perLevel"] = round(row["attackSpeedRatio"] * after, 5)
    st["lvl15"] = lvl15(st)
    done.append(f"{label} baseStats attack speed (derived)")


def apply_champions(champions, formulas, as_table):
    C = by_name(champions)
    F = formulas

    # Shyvana
    sh = C["Shyvana"]
    hp = sh["baseStats"]["hp"]
    field("Shyvana health per level", hp, ["perLevel"], 120, 130)
    hp["lvl15"] = lvl15(hp)
    rg = sh["baseStats"]["hpRegen"]
    field("Shyvana health regen (base; notes say 'per level')", rg, ["base"], 9, 12)
    rg["lvl15"] = lvl15(rg)
    drift.append("Shyvana health regen: Riot labels 9 -> 12 'per level'; our per-level "
                 "regen is a placeholder and our base is 9, so it was applied to base")
    attack_speed_per_level("Shyvana", sh, as_table, 0.012, 0.024)
    fs = F["Shyvana"]["abilities"]
    field("Shyvana Twin Bite cooldown (text)", ability(sh, "1"), ["cooldowns"],
          ["8.5", "7.5", "6.5", "5.5"], ["7", "6.5", "6", "5.5"])
    field("Shyvana Twin Bite cooldown", fs["1"], ["cooldowns"], [8.5, 7.5, 6.5, 5.5], [7, 6.5, 6, 5.5])
    field("Shyvana Burnout cooldown (text)", ability(sh, "2"), ["cooldowns"],
          ["13", "12", "11", "10"], ["12", "11", "10", "9"])
    field("Shyvana Burnout cooldown", fs["2"], ["cooldowns"], [13, 12, 11, 10], [12, 11, 10, 9])
    text("Shyvana Wings of the Cloud (text)", ability(sh, "2"), "text",
         "haste Shyvana by an additional 25%", "haste Shyvana by an additional 15%")
    reword_note("Shyvana Wings of the Cloud (note)", fs["2"],
                "additional 25% haste", "additional 15% haste")
    e = ability(sh, "3")
    field("Shyvana Flame Breath cooldown (text)", e, ["cooldowns"],
          ["11", "10", "9", "8"], ["10", "9", "8", "7"])
    field("Shyvana Flame Breath cooldown", fs["3"], ["cooldowns"], [11, 10, 9, 8], [10, 9, 8, 7])
    text("Shyvana Flame Breath ratio (text)", e, "text",
         "60 / 110 / 160 / 210 ( +30% AD +40% AP )", "60 / 110 / 160 / 210 ( +50% AD +80% AP )")
    text("Shyvana Dragon detonation ratio (text)", e, "text",
         "110 ( +50% AD +70% AP )", "110 ( +100% AD +100% AP )")
    text("Shyvana scorched earth AD (text)", e, "text",
         "28 ( +10% AD +20% AP )", "28 ( +15% AD +20% AP )")
    dmg = {d["name"]: d for d in fs["3"]["damage"]}
    fb = dmg["Flame Breath Fireball"]
    field("Shyvana Flame Breath AD", fb, ["ratios", 0, "pct"], 30, 50)
    field("Shyvana Flame Breath AP", fb, ["ratios", 1, "pct"], 40, 80)
    dd = dmg["Flame Breath Dragon Fireball"]
    field("Shyvana Dragon detonation AD", dd, ["ratios", 0, "pct"], 50, 100)
    field("Shyvana Dragon detonation AP", dd, ["ratios", 1, "pct"], 70, 100)
    field("Shyvana scorched earth AD", dmg["Flame Breath Dragon Fire"],
          ["ratios", 0, "pct"], 10, 15)
    text("Shyvana Life of the Ocean (text)", ability(sh, "4"), "text",
         "gaining 20% Omnivamp", "gaining 10% Omnivamp")
    reword_note("Shyvana Life of the Ocean (note)", fs["4"],
                "20% Omnivamp", "10% Omnivamp")

    # Camille, Lee Sin, Akali: attack speed growth
    attack_speed_per_level("Camille", C["Camille"], as_table, 0.016, 0.028)
    attack_speed_per_level("Lee Sin", C["Lee Sin"], as_table, 0.02, 0.04)
    attack_speed_per_level("Akali", C["Akali"], as_table, 0.02, 0.04)
    ar = C["Akali"]["baseStats"]["armor"]
    field("Akali base armor", ar, ["base"], 34, 37)
    ar["lvl15"] = lvl15(ar)

    # Malphite
    m = C["Malphite"]
    fm = F["Malphite"]["abilities"]
    text("Malphite Granite Shield (text)", ability(m, "P"), "text",
         "( 11% maximum HP )", "( 10% maximum HP )")
    field("Malphite Granite Shield", fm["P"], ["defensive", 0, "ratios", 0, "pct"], 11, 10)
    text("Malphite Thunderclap first attack (text)", ability(m, "2"), "text",
         "40 / 60 / 80 / 100 ( +40% AP +40% Armor ) bonus physical damage",
         "30 / 45 / 60 / 75 ( +40% AP +20% Armor ) bonus physical damage")
    drift.append("Malphite Thunderclap first-attack Armor ratio: we said 40%; Riot's "
                 "before was 30%. Set to Riot's 20%.")
    tc = next(d for d in fm["2"]["damage"] if d["name"] == "Thunderclap empowered first attack")
    field("Malphite Thunderclap first attack base", tc, ["base"], [40, 60, 80, 100], [30, 45, 60, 75])
    field("Malphite Thunderclap first attack Armor ratio", tc, ["ratios", 1, "pct"], 30, 20)

    # Ekko
    ek = C["Ekko"]
    fe = F["Ekko"]["abilities"]
    text("Ekko Z-Drive vs monsters (text)", ability(ek, "P"), "text",
         "Deals 120% damage to monsters", "Deals 110% damage to monsters")
    reword_note("Ekko Z-Drive vs monsters (note)", fe["P"],
                "120% damage to monsters", "110% damage to monsters")
    text("Ekko Timewinder vs monsters (text)", ability(ek, "1"), "text",
         "Deals 115% damage to monsters", "Deals 100% damage to monsters")
    reword_note("Ekko Timewinder vs monsters (note)", fe["1"],
                "deals 115% damage to monsters", "deals 100% damage to monsters")

    # Lee Sin
    text("Lee Sin Dragon's Rage (text)", ability(C["Lee Sin"], "4"), "text",
         "dealing 125 / 350 / 575", "dealing 150 / 375 / 600")
    field("Lee Sin Dragon's Rage base", F["Lee Sin"]["abilities"]["4"],
          ["damage", 0, "base"], [125, 350, 575], [150, 375, 600])

    # Nasus
    n = C["Nasus"]
    fn = F["Nasus"]["abilities"]
    ad = n["baseStats"]["ad"]
    field("Nasus base AD", ad, ["base"], 58, 62)
    ad["lvl15"] = lvl15(ad)
    text("Nasus Spirit Fire (text)", ability(n, "3"), "text",
         "dealing 55 / 110 / 165 / 220", "dealing 50 / 90 / 130 / 170")
    field("Nasus Spirit Fire base", fn["3"], ["damage", 0, "base"],
          [55, 110, 165, 220], [50, 90, 130, 170])
    text("Nasus Fury resists (text)", ability(n, "4"), "text",
         "40 / 50 / 60 Armor and Magic Resist", "40 / 55 / 70 Armor and Magic Resist")
    field("Nasus Fury armor", fn["4"], ["steroids", 1, "flat"], [40, 50, 60], [40, 55, 70])
    field("Nasus Fury magic resist", fn["4"], ["steroids", 2, "flat"], [40, 50, 60], [40, 55, 70])

    # Samira
    sa = C["Samira"]
    fsa = F["Samira"]["abilities"]
    text("Samira Flair ratio (text)", ability(sa, "1"), "text",
         "( +110% AD )", "( +115% AD )", patch_before="125%")
    fl = {d["name"]: d for d in fsa["1"]["damage"]}
    field("Samira Flair ratio (ranged)", fl["Flair (ranged)"], ["ratios", 0, "pct"], 125, 115)
    field("Samira Flair ratio (melee)", fl["Flair (melee)"], ["ratios", 0, "pct"], 125, 115)
    text("Samira Inferno Trigger ratio (text)", ability(sa, "4"), "text",
         "(+ 50% AD )", "(+ 45% AD )")
    field("Samira Inferno Trigger ratio", fsa["4"], ["damage", 0, "ratios", 0, "pct"], 50, 45)

    # Ashe: the crit-scaled bonus cannot be expressed by ratios (7.3 note)
    note("Ashe Frost Shot crit bonus", F["Ashe"]["abilities"]["P"],
         "bonus attack damage from crit stats 0 ~ 130% -> 0 ~ 123.5% (not modelled).")

    # Miss Fortune
    mf = C["Miss Fortune"]
    fmf = F["Miss Fortune"]["abilities"]
    text("Miss Fortune Love Tap (text)", ability(mf, "P"), "text",
         "( 15 +40% bonus AD )", "( 15 +50% bonus AD )")
    field("Miss Fortune Love Tap bonus AD", fmf["P"], ["damage", 0, "ratios", 0, "pct"], 40, 50)
    text("Miss Fortune Bullet Time crit (text)", ability(mf, "4"), "text",
         "Each wave can Crit for 130% damage, increased by 30% of Critical Damage above 200%",
         "Each wave can Crit for 135% - 145.5% damage (based on Critical Damage)")
    bt = fmf["4"]["damage"][0]
    field("Miss Fortune Bullet Time crit (note)", bt, ["note"],
          "Each wave can critically strike for 130% damage",
          "Each wave can critically strike for 135% - 145.5% damage (based on Critical Damage)")
    note("Miss Fortune Bullet Time crit", fmf["4"],
         "wave critical damage 130% ~ 139% -> 135% ~ 145.5% (based on crit stats).")

    # Singed
    sg = C["Singed"]
    fsg = F["Singed"]["abilities"]
    hp = sg["baseStats"]["hp"]
    field("Singed base health", hp, ["base"], 690, 660)
    hp["lvl15"] = lvl15(hp)
    ms = sg["baseStats"]["moveSpeed"]
    field("Singed move speed", ms, ["base"], 355, 350)
    ms["lvl15"] = lvl15(ms)
    field("Singed Mega Adhesive cooldown (text)", ability(sg, "2"), ["cooldowns"],
          ["11", "11", "11", "11"], ["14", "13", "12", "11"])
    field("Singed Mega Adhesive cooldown", fsg["2"], ["cooldowns"], [11, 11, 11, 11], [14, 13, 12, 11])
    field("Singed Fling cooldown (text)", ability(sg, "3"), ["cooldowns"],
          ["12", "12", "12", "12"], ["13", "13", "13", "13"])
    field("Singed Fling cooldown", fsg["3"], ["cooldowns"], [12, 12, 12, 12], [13, 13, 13, 13])


# ----------------------------------------------------------------- writers --
def render(key: str, path: Path, data) -> bytes:
    raw_bytes = path.read_bytes()
    crlf = b"\r\n" in raw_bytes
    raw = raw_bytes.decode("utf-8").replace("\r\n", "\n")
    if key == "item_fx":
        new = hand_edit_item_fx(raw)
        if json.loads(new) != data:
            raise SystemExit("item_engine_overrides.json: the text edit does not match "
                             "the intended change; nothing written")
    else:
        tail = "\n" if raw.endswith("\n") else ""
        new = json.dumps(data, indent=2, ensure_ascii=False) + tail
    if crlf:
        new = new.replace("\n", "\r\n")
    return new.encode("utf-8")


# ---------------------------------------------------------------- coverage --
COVERAGE = {
    "SHYVANA": "applied", "CAMILLE": "applied", "MALPHITE": "applied", "EKKO": "applied",
    "LEE SIN": "applied", "AKALI": "applied", "NASUS": "applied", "SAMIRA": "applied",
    "ASHE": "noted: crit-scaled bonus is text-only since 7.3", "MISS FORTUNE": "applied",
    "SINGED": "applied",
    "Opening Barrage": "applied", "Divine Sunderer": "applied", "Essence Reaver": "applied",
    "Whispering Circlet": "applied", "Diadem of Songs": "applied", "Bolt": "applied",
    "Hand of Baron": "not modelled: no minion or structure model on the site",
    "Minions": "not modelled: no minion or structure model on the site",
    "Turrets": "not modelled: no minion or structure model on the site",
}
MODE_ONLY = "GAME MODE CHANGES"


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
            if b["title"] in COVERAGE or MODE_ONLY in path:
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
    apply_items(data["items"], data["item_fx"])
    apply_champions(data["champions"], data["formulas"], data["attack_speed"])
    field("champion_attack_speed.json patch", data["attack_speed"], ["patch"],
          data["attack_speed"]["patch"], PATCH)
    for k in ("item_rules", "rune_rules", "stat_overrides"):
        field(f"{FILES[k].name} targetPatch", data[k], ["targetPatch"], PREV, PATCH)

    print(f"{len(done)} edits")
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
    if not args.write:
        print("\ndry run: nothing written (use --write)")
        return 0
    out = {k: render(k, FILES[k], data[k]) for k in FILES}
    for k, blob in out.items():
        FILES[k].write_bytes(blob)
    print(f"\nwrote {len(FILES)} files")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
