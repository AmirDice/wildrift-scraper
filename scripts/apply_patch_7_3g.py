"""Apply Wild Rift patch 7.3g to the site's data.

Same discipline as scripts/apply_patch_7_3f.py, which this copies: every
change quotes a line of data/patch_notes_7_3g.json (scripts/parse_patch_notes.py
from Riot's page), the COVERAGE table accounts for every line in that parse,
each edit names RIOT'S "before" and REPORTS -- not aborts -- when ours was
something else, and every file is rendered before any is written.

Judgment calls, reported again at run time:

    Sylas Kingslayer   Riot gives only the base heal ratio, 5% -> 6.5% bonus
        Health. The capped heal is that heal doubled ("up to 60 / 120 / 180 /
        240 (+60% AP +10% bonus HP)"), so its ratio moves 10% -> 13% with it.
    Absolute Focus   Riot's AP "before" was 4 - 40; ours said 2 - 30. Set to
        Riot's "after", 3.3 - 30, which keeps our maximum.
    Immortal Shieldbow   the engine prices the ranged shield (300 - 550),
        now 320 - 550; the melee range is text.
    Irelia Bladesurge healing   kept as the rank-1 ratio with the per-rank
        values in the note, as the formula already did.

Not modelled, recorded in COVERAGE: Aurora's Twofold Hex projectile width,
the 70% health threshold of Absolute Focus (the engine models a fresh-fight
ceiling), Sylas's explosion damage to minions (text), and the AAA ARAM
section.

    python -m scripts.apply_patch_7_3g            # report only
    python -m scripts.apply_patch_7_3g --write    # apply

Then, per the patch checklist: export_engine_data, export_champion_details,
export_items, extract_formulas is NOT needed (formulas are edited here),
fetch_riot_patch_history.mjs, bump the build cache, redeploy the advisor.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
NOTES = DATA / "patch_notes_7_3g.json"
PATCH = "7.3g"
PREV = "7.3f"

FILES = {
    "items": DATA / "items.json",
    "item_engine": DATA / "item_engine.json",
    "item_fx": DATA / "item_engine_overrides.json",
    "item_rules": DATA / "item_stat_rules.json",
    "champions": DATA / "champions_wr.json",
    "formulas": DATA / "ability_formulas.json",
    "attack_speed": DATA / "champion_attack_speed.json",
    "rune_rules": DATA / "rune_stat_rules.json",
    "stat_overrides": DATA / "champion_stat_overrides.json",
    "runes": DATA / "runes.json",
    "wrmeta_runes": DATA / "wrmeta_runes.json",
    "rune_effects": DATA / "rune_effects.json",
    "rune_engine": DATA / "rune_engine.json",
    "rune_scaling": DATA / "rune_scaling.json",
    "rune_coverage": DATA / "rune_engine_coverage.json",
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


def passive_text(label, item, prefix, old, new):
    for i, p in enumerate(item["passives"]):
        if p.startswith(prefix):
            holder = {"t": p}
            text(label, holder, "t", old, new)
            item["passives"][i] = holder["t"]
            return
    missing.append(f"{label}: {item['name']} has no passive {prefix!r}")


def base_stat(label, champ, stat, key, before, after):
    st = champ["baseStats"][stat]
    field(label, st, [key], before, after)
    st["lvl15"] = round(st["base"] + 14 * st["perLevel"], 4)


# ------------------------------------------------------------------- items --
def apply_items(items, item_engine, item_fx, item_rules):
    I = by_name(items)

    sb = I["Immortal Shieldbow"]
    passive_text("Shieldbow Lifeline (text)", sb, "Lifeline",
                 "(350-650 for melee, 300-550 for ranged, based on level)",
                 "(380-700 for melee, 320-550 for ranged, based on level)")
    field("Shieldbow Lifeline ranged shield (engine)", item_fx["immortal-shieldbow"],
          ["shieldFlat", "lvlRange"], [300, 550], [320, 550])
    lifeline = item_rules["items"]["immortal-shieldbow"]["conditional"][0]
    text("Shieldbow Lifeline (rules)", lifeline, "detail",
         "shields you for 300-550 (350-650 melee)", "shields you for 320-550 (380-700 melee)")

    bg = I["Berserker's Greaves"]
    field("Berserker's Greaves attack speed", bg, ["stats", "attackSpeed", "value"], 35, 30)
    passive_text("Berserker's Blessed Blade (text)", bg, "Blessed Blade",
                 "restore 10 Health", "restore 5 Health")
    field("Berserker's Blessed Blade (engine)", item_engine["berserkers-greaves"], ["healOnHitFlat"], 10, 5)

    gg = I["Gunmetal Greaves"]
    field("Gunmetal Greaves attack speed", gg, ["stats", "attackSpeed", "value"], 50, 45)
    passive_text("Gunmetal Blessed Blade (text)", gg, "Blessed Blade",
                 "restore 12 Health", "restore 5 Health")
    field("Gunmetal Blessed Blade (engine)", item_engine["gunmetal-greaves"], ["healOnHitFlat"], 12, 5)

    ac = I["Ardent Censer"]
    passive_text("Ardent Censer attack speed (text)", ac, "Censer",
                 "granting 30% bonus Attack Speed", "granting 25% bonus Attack Speed")
    fx = item_fx["ardent-censer"]
    field("Ardent Censer ally attack speed (engine)", fx, ["allyAsPct"], 30, 25)
    field("Ardent Censer own attack speed (engine)", fx, ["selfTriggeredAsPct"], 30, 25)

    field("Harmonic Echo AP", I["Harmonic Echo"], ["stats", "ap", "value"], 40, 25)
    field("Guinsoo's Rageblade attack speed", I["Guinsoo's Rageblade"],
          ["stats", "attackSpeed", "value"], 30, 25)


#: The two engine item files and rune_effects are laid out by hand.
ITEM_ENGINE_EDITS = [
    ('"berserkers-greaves": {\n    "healOnHitFlat": 10',
     '"berserkers-greaves": {\n    "healOnHitFlat": 5'),
    ('"gunmetal-greaves": {\n    "msPct": 15,\n    "healOnHitFlat": 12',
     '"gunmetal-greaves": {\n    "msPct": 15,\n    "healOnHitFlat": 5'),
]
ITEM_FX_EDITS = [
    ('"immortal-shieldbow": {\n    "shieldFlat": {\n      "lvlRange": [\n        300,\n        550',
     '"immortal-shieldbow": {\n    "shieldFlat": {\n      "lvlRange": [\n        320,\n        550'),
    ('"allyAsPct": 30,', '"allyAsPct": 25,'),
    ('"selfTriggeredAsPct": 30,', '"selfTriggeredAsPct": 25,'),
]
RUNE_EFFECT_EDITS = [
    ('"Absolute Focus": {\n      "bonusAdRange": [\n        2,\n        20\n      ],',
     '"Absolute Focus": {\n      "bonusAdRange": [\n        2,\n        18\n      ],'),
]
HAND = {"item_engine": ITEM_ENGINE_EDITS, "item_fx": ITEM_FX_EDITS, "rune_effects": RUNE_EFFECT_EDITS}


# ------------------------------------------------------------------- runes --
def apply_runes(runes, wrmeta, effects, engine, scaling, coverage):
    af = by_name(runes)["Absolute Focus"]
    text("Absolute Focus (runes.json)", af, "description",
         "While above 65% Health, gain a bonus 2 - 20 Attack Damage or 2 - 30 Ability Power",
         "While above 70% Health, gain a bonus 2 - 18 Attack Damage or 3.3 - 30 Ability Power")
    wm = by_name(wrmeta)["Absolute Focus"]
    text("Absolute Focus (wrmeta text)", wm, "text",
         "While above 65% Health, gain a bonus 2–20 Attack Damage (based on level) or 2–30 Ability Power",
         "While above 70% Health, gain a bonus 2–18 Attack Damage (based on level) or 3.3–30 Ability Power")
    eff = effects
    for k in ("minors", "keystones"):
        if isinstance(eff, dict) and k in eff and "Absolute Focus" in eff[k]:
            eff = eff[k]
            break
    field("Absolute Focus AD (rune_effects)", eff["Absolute Focus"], ["bonusAdRange"], [2, 20], [2, 18])
    e = engine["Absolute Focus"]
    field("Absolute Focus AD (engine)", e, ["adaptiveAd", "lvlRange"], [2, 20], [2, 18])
    field("Absolute Focus AP (engine)", e, ["adaptiveAp", "lvlRange"], [4, 40], [3.3, 30])
    sc = scaling
    for k in ("runes",):
        if k in sc and "Absolute Focus" in sc[k]:
            sc = sc[k]
    st = sc["Absolute Focus"]["stats"][0]
    field("Absolute Focus AD at 15 (scaling)", st, ["ad"], 20, 18)
    text("Absolute Focus threshold (scaling note)", st, "note",
         "while above 65% Health", "while above 70% Health")
    text("Absolute Focus evidence (scaling)", sc["Absolute Focus"], "evidence",
         "bonus 2–20 Attack Damage", "bonus 2–18 Attack Damage")
    cov = coverage
    for k in ("partial", "excluded"):
        if isinstance(cov, dict) and k in cov and "Absolute Focus" in cov[k]:
            cov = cov[k]
            break
    text("Absolute Focus threshold (coverage)", cov, "Absolute Focus",
         "after falling below 65% Health", "after falling below 70% Health")


# --------------------------------------------------------------- champions --
def apply_champions(champions, formulas):
    C = by_name(champions)
    F = formulas

    # Vayne
    va = C["Vayne"]
    fv = F["Vayne"]["abilities"]
    text("Vayne Silver Bolts (text)", ability(va, "2"), "text",
         "6% / 7% / 8% / 9% true damage", "5.5% / 7% / 8.5% / 10% true damage")
    field("Vayne Silver Bolts max Health", dmg(fv["2"], "Silver Bolts passive"),
          ["ratios", 0, "pct"], [6, 7, 8, 9], [5.5, 7, 8.5, 10])
    text("Vayne Final Hour (text)", ability(va, "4"), "text",
         "Gains 30 / 40 / 50 Attack Damage", "Gains 40 / 50 / 60 Attack Damage")
    field("Vayne Final Hour AD", fv["4"], ["steroids", 0, "flat"], [30, 40, 50], [40, 50, 60])

    # Irelia
    ir = C["Irelia"]
    fi = F["Irelia"]["abilities"]
    base_stat("Irelia base AD", ir, "ad", "base", 58, 62)
    q = ability(ir, "1")
    field("Irelia Bladesurge cooldown (text)", q, ["cooldowns"], ["9", "8", "7", "6"], ["8", "7", "6", "5"])
    field("Irelia Bladesurge cooldown", fi["1"], ["cooldowns"], [9, 8, 7, 6], [8, 7, 6, 5])
    text("Irelia Bladesurge healing (text)", q, "text",
         "healing herself for 9% / 11% / 13% / 15% AD", "healing herself for 11% / 13% / 15% / 17% AD")
    field("Irelia Bladesurge healing (rank 1)", fi["1"], ["defensive", 0, "ratios", 0, "pct"], 9, 11)
    reword_note("Irelia Bladesurge healing (note)", fi["1"], "9/11/13/15% AD", "11/13/15/17% AD")

    # Garen
    ga = C["Garen"]
    fg = F["Garen"]["abilities"]["3"]
    e = ability(ga, "3")
    text("Garen Judgment damage (text)", e, "text",
         "dealing 13 / 17 / 21 / 25 ( +25% / 30% / 35% / 40% AD )",
         "dealing 10 / 13 / 16 / 19 ( +30% / 36% / 42% / 48% AD )")
    spin = dmg(fg, "Judgment Spin")
    field("Garen Judgment base", spin, ["base"], [13, 17, 21, 25], [10, 13, 16, 19])
    field("Garen Judgment AD ratio", spin, ["ratios", 0, "pct"], [25, 30, 35, 40], [30, 36, 42, 48])
    text("Garen Judgment armor shred (text)", e, "text",
         "their Armor is shredded by 10%", "their Armor is shredded by 15%")
    reword_note("Garen Judgment armor shred (note)", fg,
                "shreds target armor by 10%", "shreds target armor by 15%")

    # Smolder
    sm = C["Smolder"]
    fs = F["Smolder"]["abilities"]
    field("Smolder Achooo! cooldown (text)", ability(sm, "2"), ["cooldowns"],
          ["12", "11", "10", "9"], ["13", "12", "11", "10"])
    field("Smolder Achooo! cooldown", fs["2"], ["cooldowns"], [12, 11, 10, 9], [13, 12, 11, 10])
    field("Smolder Flap cooldown (text)", ability(sm, "3"), ["cooldowns"],
          ["18", "16", "14", "12"], ["22", "19", "16", "13"])
    field("Smolder Flap cooldown", fs["3"], ["cooldowns"], [18, 16, 14, 12], [22, 19, 16, 13])

    # Sylas
    sy = C["Sylas"]
    fy = F["Sylas"]["abilities"]
    text("Sylas Chain Lash minions (text)", ability(sy, "1"), "text",
         "The explosion deals 30% damage to minions", "The explosion deals 35% damage to minions")
    reword_note("Sylas Chain Lash minions (note)", fy["1"],
                "Explosion deals 30% damage to minions", "Explosion deals 35% damage to minions")
    w = ability(sy, "2")
    text("Sylas Kingslayer heal (text)", w, "text", "+30% AP +5% bonus HP", "+30% AP +6.5% bonus HP")
    text("Sylas Kingslayer capped heal (text)", w, "text", "+60% AP +10% bonus HP", "+60% AP +13% bonus HP")
    field("Sylas Kingslayer heal bonus Health", fy["2"], ["defensive", 0, "ratios", 1, "pct"], 5, 6.5)
    field("Sylas Kingslayer capped heal bonus Health (derived: doubled)", fy["2"],
          ["defensive", 1, "ratios", 1, "pct"], 10, 13)

    # Aurora: projectile width only
    fa = F["Aurora"]["abilities"]["1"]
    fa.setdefault("unmodeled", []).append(
        "7.3g: projectile narrower on the first cast and wider on the recast's return")
    done.append("Aurora Twofold Hex width (note)")


# ----------------------------------------------------------------- writers --
CANON_INDENT = {"wrmeta_runes": 2}


def render(key: str, path: Path, data) -> bytes:
    raw_bytes = path.read_bytes()
    crlf = b"\r\n" in raw_bytes
    raw = raw_bytes.decode("utf-8").replace("\r\n", "\n")
    if key in HAND:
        new = raw
        for old, rep in HAND[key]:
            n = new.count(old)
            if n != 1:
                raise SystemExit(f"{path.name}: {old[:60]!r} occurs {n} times; nothing written")
            new = new.replace(old, rep)
        if json.loads(new) != data:
            raise SystemExit(f"{path.name}: the text edit does not match the intended change; nothing written")
    else:
        orig = json.loads(raw)
        fmt = None
        for indent in (2, 1):
            for ascii_ in (False, True):
                for tail in ("", "\n"):
                    if json.dumps(orig, indent=indent, ensure_ascii=ascii_) + tail == raw:
                        fmt = (indent, ascii_, tail)
        if fmt is None:
            raise SystemExit(f"{path.name}: not canonically formatted; add hand edits")
        new = json.dumps(data, indent=fmt[0], ensure_ascii=fmt[1]) + fmt[2]
    if crlf:
        new = new.replace("\n", "\r\n")
    return new.encode("utf-8")


# ---------------------------------------------------------------- coverage --
COVERAGE = {
    "VAYNE": "applied", "IRELIA": "applied", "GAREN": "applied", "SMOLDER": "applied",
    "SYLAS": "applied", "AURORA": "not modelled: projectile width (noted on the formula)",
    "Life Line": "applied", "Berserker's Greaves": "applied", "Blessed Blade": "applied",
    "Gunmetal Greaves": "applied", "Censer": "applied", "Harmonic Echo": "applied",
    "Guinsoo's Rageblade": "applied",
    "Absolute Focus": "applied (the 70% threshold is text; the engine models a fresh-fight ceiling)",
}
SKIP_SECTIONS = ("GAME MODE CHANGES", "AAA ARAM")


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
    apply_items(data["items"], data["item_engine"], data["item_fx"], data["item_rules"])
    apply_runes(data["runes"], data["wrmeta_runes"], data["rune_effects"], data["rune_engine"],
                data["rune_scaling"], data["rune_coverage"])
    apply_champions(data["champions"], data["formulas"])
    field("champion_attack_speed.json patch", data["attack_speed"], ["patch"], PREV, PATCH)
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
