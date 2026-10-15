"""Apply Wild Rift patch 7.3b to the site's data.

Reads nothing it retypes: every change below quotes the line of
data/patch_notes_7_3b.json it implements (made by scripts/parse_patch_notes.py
from Riot's page), and the COVERAGE table at the bottom accounts for every
line in that parse. A line the table does not mention fails the run, so a
change cannot be dropped by forgetting it.

Each edit names the value we expect to find, writes the patch's new value,
and REPORTS -- not aborts -- when what it found was not the patch's "before".
Three of those are expected and are corrections in their own right: our text
had drifted from the game before this patch arrived.

    Tryndamere Battle Fury   we said 0.32% per Fury; Riot's before is 0.3-0.5%
    Yasuo Way of the Wanderer we said a 115-500 shield; Riot's before is 77-529
    Hwei's passive text       still on 7.3 numbers (33-333, 33% AP): the 7.3a
                              script's replacement looked for a hyphen and the
                              text has an en dash, so it never matched
    Grasp of the Undying      runes page and engine said 2%; Riot's before is
                              3.3%, and wr-meta agreed with Riot
    Warmog's Heart            we said 950 bonus Health; Riot's before is 900

What this does NOT do, deliberately:

* It does not re-run extract_formulas. Re-extraction re-guesses judgment
  fields (asEfficiency, abilitiesCanCrit) as well as numbers -- the 7.2d
  drift trap -- and every 7.3b number has an exact field to write instead.
* It does not touch the win-rate patch labels. The boards were collected on
  7.3a and still are; only what the DATA describes moves to 7.3b.

    python -m scripts.apply_patch_7_3b            # report only
    python -m scripts.apply_patch_7_3b --write    # apply

Then, per the patch checklist: export_engine_data, export_champion_details,
export_items, fetch_riot_patch_history.mjs, bump the build cache, redeploy
the advisor.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
WEB_DATA = ROOT / "web-next" / "src" / "data"
NOTES = DATA / "patch_notes_7_3b.json"
PATCH = "7.3b"

FILES = {
    "items": DATA / "items.json",
    "runes": DATA / "runes.json",
    "wrmeta_runes": DATA / "wrmeta_runes.json",
    "rune_engine": DATA / "rune_engine.json",
    "rune_effects": DATA / "rune_effects.json",
    "item_fx": DATA / "item_engine_overrides.json",
    "champions": DATA / "champions_wr.json",
    "formulas": DATA / "ability_formulas.json",
    "hwei_kit": DATA / "hwei_kit.json",
    "item_rules": DATA / "item_stat_rules.json",
    "rune_rules": DATA / "rune_stat_rules.json",
    # NOT web-next/src/data/stat_rules.json: export_engine_data regenerates
    # that file and takes its targetPatch from THIS one, so an edit made
    # there is reverted by the next export -- which is what happened the
    # first time this script ran.
    "stat_overrides": DATA / "champion_stat_overrides.json",
}

drift: list[str] = []      # found something other than Riot's "before"
missing: list[str] = []    # could not find what to change at all
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
    """Replace `old` with `new` in a text field, exactly once.

    `old` is what OUR text says. `patch_before` is what Riot says it was,
    given only where the two differ, so the drift is reported rather than
    hidden by the replacement succeeding.
    """
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
    """Record a change no field can express, on the ability itself."""
    notes = ability.setdefault("unmodeled", [])
    entry = f"{PATCH}: {line}"
    if entry not in notes:
        notes.append(entry)
    done.append(label)


def ability(champ, slot):
    for a in champ["abilities"]:
        if str(a.get("slot")) == slot:
            return a
    raise KeyError(f"{champ['name']} has no slot {slot}")


# ------------------------------------------------------------------- items --
def apply_items(items, item_fx):
    I = by_name(items)
    field("Youmuu's price", I["Youmuu's Ghostblade"], ["cost"], 3000, 2900)
    field("Locket price", I["Locket of the Iron Solari"], ["cost"], 2600, 2500)
    field("Locket health", I["Locket of the Iron Solari"], ["stats", "hp", "value"], 200, 300)
    field("Thornmail price", I["Thornmail"], ["cost"], 2700, 2850)
    field("Statikk price", I["Statikk Shiv"], ["cost"], 3000, 2900)
    field("Yun Tal price", I["Yun Tal Wildarrows"], ["cost"], 3100, 3000)

    w = I["Warmog's Armor"]
    w["passives"] = list(w["passives"])
    idx = next(i for i, p in enumerate(w["passives"]) if p.startswith("Warmog's Heart"))
    holder = {"t": w["passives"][idx]}
    text("Warmog's Heart threshold", holder, "t",
         "at least 950 bonus Health", "at least 1250 bonus Health", patch_before="900")
    w["passives"][idx] = holder["t"]

    s = I["Statikk Shiv"]
    idx = next(i for i, p in enumerate(s["passives"]) if p.startswith("ElectroShock"))
    holder = {"t": s["passives"][idx]}
    text("Statikk ElectroShock stacks", holder, "t",
         "Attacks grant 5 bonus Energized stacks", "Attacks grant 7 bonus Energized stacks")
    s["passives"][idx] = holder["t"]

    # The engine charges Electrospark on a fixed cadence that was chosen, not
    # derived from the stack count, so there is no honest number to scale it
    # by. Say so where the next person tuning it will look.
    fx = item_fx["statikk-shiv"]
    line = ("7.3b raised ElectroShock from 5 to 7 bonus Energized stacks per "
            "attack, which makes Electrospark fire more often. The 6s cadence "
            "here was chosen rather than derived from the stack count, so it "
            "has NOT been rescaled: Statikk's 7.3b buff is in the text and "
            "the price, not yet in the simulation.")
    fx.setdefault("_patch", [])
    if line not in fx["_patch"]:
        fx["_patch"].append(line)


# ------------------------------------------------------------------- runes --
def apply_runes(runes, wrmeta, rune_engine, rune_effects):
    R, W = by_name(runes), by_name(wrmeta)

    text("Electrocute damage (runes page)", R["Electrocute"], "description",
         "dealing them 40 - 210 (based on level)", "dealing them 60 - 210 (based on level)")
    text("Electrocute damage (wr-meta)", W["Electrocute"], "text",
         "Damage value: 40-210", "Damage value: 60-210")
    field("Electrocute damage (engine)", rune_engine["Electrocute"],
          ["burstProcFlat", "lvlRange"], [40, 210], [60, 210])

    text("Cheap Shot cooldown (runes page)", R["Cheap Shot"], "description",
         "(7 seconds cooldown)", "(5 seconds cooldown)")
    text("Cheap Shot cooldown (wr-meta)", W["Cheap Shot"], "text",
         "Cooldown: 7s", "Cooldown: 5s")
    field("Cheap Shot cooldown (engine)", rune_engine["Cheap Shot"],
          ["burstProcCdSec"], 7, 5)
    rune_engine["Cheap Shot"]["_why_cd"] = "'(5 seconds cooldown).' (7.3b: 7s -> 5s)"

    text("Grasp damage (runes page)", R["Grasp of the Undying"], "description",
         "deal 2% of your maximum health", "deal 3% of your maximum health",
         patch_before="3.3%")
    text("Grasp health growth (runes page)", R["Grasp of the Undying"], "description",
         "permanently grant 10 bonus health", "permanently grant 8 bonus health")
    text("Grasp damage (wr-meta)", W["Grasp of the Undying"], "text",
         "Bonus magic damage: 3.3% [hp]", "Bonus magic damage: 3% [hp]")
    text("Grasp health growth (wr-meta)", W["Grasp of the Undying"], "text",
         "Permanently health increase: 10", "Permanently health increase: 8")
    g = rune_effects["keystones"]["Grasp of the Undying"]
    field("Grasp damage (engine)", g, ["procOwnMaxHpPct"], 3.3, 3)
    g["_why"] = g["_why"].replace("deals 2% of the user's max Health",
                                  "deals 3% of the user's max Health")
    g.setdefault("_patch", [])
    for line in ("7.3b procOwnMaxHpPct: 2 -> 3. Riot lists the pre-patch value "
                 "as 3.3%, so this was underrated before 7.3b as well.",
                 "7.3b permanent Health per proc: 10 -> 8 (not modelled; see _why)."):
        if line not in g["_patch"]:
            g["_patch"].append(line)

    text("Aery shield (runes page)", R["Aery"], "description",
         "shielding them for 25 - 120 (based on level)",
         "shielding them for 20 - 100 (based on level)")
    text("Aery shield (wr-meta)", W["Aery"], "text", "Shield: 25-120", "Shield: 20-100")
    field("Aery shield (engine)", rune_engine["Aery"], ["shieldFlat", "lvlRange"],
          [25, 120], [20, 100])


# --------------------------------------------------------------- champions --
def apply_champions(champions, formulas):
    C = by_name(champions)
    F = formulas

    # Volibear -- Frenzied Maul
    v = ability(C["Volibear"], "2")
    text("Volibear Maul AD (text)", v, "text", "( +100% AD + 6.5% bonus HP )",
         "( +110% AD + 6.5% bonus HP )")
    text("Volibear empowered Maul AD (text)", v, "text", "( +160% AD + 10.4% bonus HP )",
         "( +176% AD + 10.4% bonus HP )")
    text("Volibear empowered heal (text)", v, "text", "+5% / 6% / 7% / 8% lost Health",
         "+5% / 8% / 11% / 14% lost Health")
    fv = F["Volibear"]["abilities"]["2"]
    field("Volibear Maul AD", fv, ["damage", 0, "ratios", 0, "pct"], 100, 110)
    field("Volibear empowered Maul AD", fv, ["damage", 1, "ratios", 0, "pct"], 160, 176)
    field("Volibear empowered heal", fv, ["defensive", 0, "ratios", 0, "pct"], 5, [5, 8, 11, 14])
    fv["defensive"][0]["note"] = "frenzy cast only; missing-health share 5/8/11/14% by rank (7.3b)"

    # Jhin -- Whisper
    j = ability(C["Jhin"], "P")
    text("Jhin missing-health damage (text)", j, "text",
         "deal additional 11% missing Health physical damage",
         "deal additional 11.5% - 25% (based on level, capped at level 10) missing Health physical damage")
    text("Jhin crit damage (text)", j, "text",
         "deal 80% of normal critical strike damage", "deal 85% of normal critical strike damage")
    fj = F["Jhin"]["abilities"]["P"]
    field("Jhin missing-health damage", fj, ["damage", 0, "ratios", 0, "pct"], 11, 11.5)
    note("Jhin missing-health ramp", fj,
         "4th-shot missing-Health damage 11% - 25% capped at level 15 -> 11.5% - 25% "
         "capped at level 10; the model carries the level-1 floor only.")
    note("Jhin crit damage", fj, "Standard Critical Strike Damage 80% -> 85% (not modelled).")

    # Tryndamere -- Battle Fury, Spinning Slash
    t = ability(C["Tryndamere"], "P")
    text("Tryndamere Fury crit (text)", t, "text",
         "Gains 0.32% Critical Rate for each point of Fury",
         "Gains 0.5% Critical Rate for each point of Fury", patch_before="0.3%-0.5% (based on level)")
    ft = F["Tryndamere"]["abilities"]
    ft["P"]["unmodeled"] = [s.replace("Each fury gives 0.32% crit chance",
                                      "Each fury gives 0.5% crit chance (7.3b)")
                            for s in ft["P"]["unmodeled"]]
    done.append("Tryndamere Fury crit (formula note)")
    e = ability(C["Tryndamere"], "3")
    text("Tryndamere Spinning Slash (text)", e, "text",
         "80 / 120 / 160 / 200 ( +100% bonus AD", "80 / 130 / 180 / 230 ( +110% bonus AD")
    fe = ft["3"]["damage"][0]
    field("Tryndamere Spinning Slash base", fe, ["base"], [80, 120, 160, 200], [80, 130, 180, 230])
    # Two corrections in one: the ratio rises, and it is BONUS AD. Riot's
    # line and our own tooltip both say bonus; the formula scaled off total
    # AD and so has been overrating Spinning Slash all along.
    if fe["ratios"][0] != {"stat": "ad", "pct": 100}:
        drift.append(f"Tryndamere Spinning Slash ratio: found {fe['ratios'][0]!r}")
    else:
        drift.append("Tryndamere Spinning Slash ratio: scaled off TOTAL AD; patch and "
                     "tooltip both say bonus AD. Corrected to bonusAd.")
    fe["ratios"][0] = {"stat": "bonusAd", "pct": 110}
    done.append("Tryndamere Spinning Slash ratio")

    # Hwei -- the live kit is F["Hwei"]["hwei"] (both engines read it); the
    # abilities block carries the same numbers for everything else.
    fh, kit = F["Hwei"]["abilities"], F["Hwei"]["hwei"]
    field("Hwei passive base", kit, ["passive", "base"], [40, 285], [30, 280])
    field("Hwei passive AP", kit, ["passive", "ap"], 0.3, 0.25)
    field("Hwei passive base (abilities)", fh, ["P", "damage", 0, "base", "lvlRange"], [40, 285], [30, 280])
    field("Hwei passive AP (abilities)", fh, ["P", "damage", 0, "ratios", 0, "pct"], 30, 25)
    ww = kit["spells"]["WW"]
    field("Hwei WW initial shield", ww, ["shieldBase"], [60, 80, 100, 120], [50, 70, 90, 110])
    field("Hwei WW initial shield AP", ww, ["shieldAp"], 0.35, 0.30)
    field("Hwei WW max shield", ww, ["maxShieldBase"], [108, 128, 148, 168], [98, 118, 138, 158])
    field("Hwei WW max shield AP", ww, ["maxShieldAp"], 0.71, 0.60)
    field("Hwei WW max shield (abilities)", fh, ["2", "defensive", 0, "base"],
          [108, 128, 148, 168], [98, 118, 138, 158])
    field("Hwei WW max shield AP (abilities)", fh, ["2", "defensive", 0, "ratios", 0, "pct"], 71, 60)
    field("Hwei WE bonus damage", kit, ["spells", "WE", "base"], [30, 40, 50, 60], [20, 30, 40, 50])
    field("Hwei WE bonus damage (abilities)", fh, ["2", "damage", 0, "base"], [30, 40, 50, 60], [20, 30, 40, 50])
    field("Hwei EE damage", kit, ["spells", "EE", "base"], [70, 120, 170, 220], [60, 110, 160, 210])
    field("Hwei EE AP", kit, ["spells", "EE", "ap"], 0.7, 0.6)
    maw = next(d for d in fh["3"]["damage"] if d["name"] == "Crushing Maw")
    field("Hwei EE damage (abilities)", maw, ["base"], [70, 120, 170, 220], [60, 110, 160, 210])
    field("Hwei EE AP (abilities)", maw, ["ratios", 0, "pct"], 70, 60)
    note("Hwei EE range and hitbox", fh["3"], "Crushing Maw cast range 7.5 -> 7 and jaw "
         "hitbox optimised (not modelled: single-target, all spells hit).")
    kit["patch"] = PATCH
    hp = ability(C["Hwei"], "P") if any(str(a.get("slot")) == "P" for a in C["Hwei"]["abilities"]) else None
    if hp is not None and hp.get("text"):
        text("Hwei passive (text)", hp, "text", "33–333 by level +33% AP",
             "30–280 by level +25% AP", patch_before="40 - 285 + 30% AP")

    # Nocturne
    n = C["Nocturne"]
    field("Nocturne health per level", n, ["baseStats", "hp", "perLevel"], 134, 128)
    field("Nocturne health at 15", n, ["baseStats", "hp", "lvl15"], 2536,
          n["baseStats"]["hp"]["base"] + 14 * 128)
    q = ability(n, "1")
    text("Nocturne Duskbringer damage (text)", q, "text", "70 / 125 / 180 / 235", "60 / 115 / 170 / 225")
    text("Nocturne Duskbringer AD (text)", q, "text",
         "Gains 20 / 30 / 40 / 50 Attack Damage", "Gains 10 / 25 / 40 / 55 Attack Damage")
    fn = F["Nocturne"]["abilities"]
    field("Nocturne Duskbringer damage", fn["1"], ["damage", 0, "base"], [70, 125, 180, 235], [60, 115, 170, 225])
    field("Nocturne Duskbringer AD", fn["1"], ["steroids", 0, "flat"], [20, 30, 40, 50], [10, 25, 40, 55])
    field("Nocturne Paranoia cooldown (text)", ability(n, "4"), ["cooldowns"],
          ["110", "90", "70"], ["120", "100", "80"])
    field("Nocturne Paranoia cooldown", fn["4"], ["cooldowns"], [110, 90, 70], [120, 100, 80])

    # Yunara
    y = C["Yunara"]
    yq = ability(y, "1")
    s = yq.get("text") or ""
    old = "10 / 15 / 20 / 25 ( +20% AP ) magic damage"
    if s.count(old) != 2:
        missing.append(f"Yunara Cultivation of Spirit: expected the passive and active "
                       f"damage lines, found {s.count(old)}")
    else:
        yq["text"] = s.replace(old, "5 / 10 / 15 / 20 ( +20% AP ) magic damage")
        done.append("Yunara Cultivation of Spirit (text)")
    fy = F["Yunara"]["abilities"]
    field("Yunara Spirit Charge damage", fy["1"], ["damage", 0, "base"], [10, 15, 20, 25], [5, 10, 15, 20])
    note("Yunara active damage", fy["1"], "Spirit Unbound's on-hit damage 10/15/20/25 -> "
         "5/10/15/20, the same values as the passive line the model carries.")
    field("Yunara ultimate cooldown (text)", ability(y, "4"), ["cooldowns"],
          ["70", "60", "50"], ["70", "65", "60"])
    field("Yunara ultimate cooldown", fy["4"], ["cooldowns"], [70, 60, 50], [70, 65, 60])

    # Senna
    sp = ability(C["Senna"], "P")
    text("Senna AD per Mist (text)", sp, "text",
         "Each stack of Mist grants 1.25 Attack Damage", "Each stack of Mist grants 0.9 Attack Damage")
    text("Senna crit damage (text)", sp, "text", "deal 90% of no", "deal 80% of no")
    fs = F["Senna"]["abilities"]
    fs["P"]["unmodeled"] = [x.replace("Each stack of Mist grants 1.25 Attack Damage",
                                      "Each stack of Mist grants 0.9 Attack Damage (7.3b)")
                            for x in fs["P"]["unmodeled"]]
    note("Senna crit damage", fs["P"], "Standard Critical Strike Damage 90% -> 80% (not modelled).")
    sq = ability(C["Senna"], "1")
    text("Senna Piercing Darkness (text)", sq, "text", "dealing 50 / 80 / 110 / 140", "dealing 30 / 60 / 90 / 120")
    field("Senna Piercing Darkness damage", fs["1"], ["damage", 0, "base"], [50, 80, 110, 140], [30, 60, 90, 120])

    # Yasuo
    ya = ability(C["Yasuo"], "P")
    text("Yasuo shield (text)", ya, "text", "absorbs 115 - 500", "absorbs 77 - 630",
         patch_before="77 - 529")
    text("Yasuo crit damage (text)", ya, "text",
         "deal 90% of normal critical strike damage", "deal 95% of normal critical strike damage")
    fya = F["Yasuo"]["abilities"]["P"]
    field("Yasuo shield", fya, ["defensive", 0, "base", "lvlRange"], [77, 529], [77, 630])
    note("Yasuo crit damage", fya, "Standard Critical Strike Damage 90% -> 95% (not modelled).")


def sync_hwei_kit(kit_file, formulas):
    """Bring data/hwei_kit.json level with the live kit.

    Both engines read Hwei from ability_formulas.json. hwei_kit.json is what
    scripts/add_hwei.py builds the champion FROM, and the 7.3a script never
    updated it -- it still held 7.3 numbers, so re-running that generator
    would have silently undone 7.3a and now 7.3b too. Copy the numbers, keep
    the kit's provenance fields.
    """
    live = formulas["Hwei"]["hwei"]
    before = copy.deepcopy(kit_file)
    kit_file["passive"] = copy.deepcopy(live["passive"])
    kit_file["spells"] = copy.deepcopy(live["spells"])
    kit_file["patch"] = PATCH
    kit_file["note"] = (kit_file.get("note", "").rstrip()
                        + " Numbers synced from ability_formulas.json (Hwei.hwei) at 7.3b;"
                          " that block is what both engines read, and this file had been"
                          " left on 7.3 when 7.3a landed.")
    changed = [k for k in ("passive", "spells") if before.get(k) != kit_file.get(k)]
    done.append(f"hwei_kit.json synced ({', '.join(changed) or 'already level'})")
    # Anything ELSE the kits disagree on is reported, not copied: a
    # difference outside the numbers a patch moves is a decision for a
    # person, not for a sync.
    for k in ("cooldowns", "manaCosts", "skillOrder", "baseStats"):
        if k in live and live[k] != kit_file.get(k):
            drift.append(f"hwei_kit.json {k} differs from the live kit (left as is)")


# ----------------------------------------------------------------- writers --
#: Files laid out by hand, which a re-dump would reformat from top to bottom.
#: They are edited as text instead, and the result is parsed back and
#: compared with what the edits above computed, so a text edit that does
#: not mean exactly the intended change is never written.
HAND_FORMATTED = {"rune_effects", "item_fx", "hwei_kit"}


def _compact(v) -> str:
    """hwei_kit.json's own style: arrays tight, objects spaced."""
    if isinstance(v, dict):
        return "{" + ", ".join(f"{json.dumps(k)}: {_compact(x)}" for k, x in v.items()) + "}"
    if isinstance(v, list):
        return "[" + ",".join(_compact(x) for x in v) + "]"
    return json.dumps(v, ensure_ascii=False)


def _insert_key(raw: str, block_open: str, indent: str, key: str, value) -> str:
    """Add `key` as the last field of the block opened by `block_open`."""
    start = raw.index(block_open)
    close = raw.index("\n" + indent[:-2] + "}", start)
    body = json.dumps(value, indent=2, ensure_ascii=False).replace("\n", "\n" + indent)
    return raw[:close] + f",\n{indent}{json.dumps(key)}: {body}" + raw[close:]


def hand_edit(key: str, raw: str, data) -> str:
    if key == "rune_effects":
        g = data["keystones"]["Grasp of the Undying"]
        assert raw.count('"procOwnMaxHpPct": 2,') == 1
        raw = raw.replace('"procOwnMaxHpPct": 2,', '"procOwnMaxHpPct": 3,')
        old_why = "the attack deals 2% of the user's max Health"
        assert raw.count(old_why) == 1
        raw = raw.replace(old_why, "the attack deals 3% of the user's max Health")
        return _insert_key(raw, '"Grasp of the Undying": {', "      ", "_patch", g["_patch"])
    if key == "item_fx":
        return _insert_key(raw, '"statikk-shiv": {', "    ", "_patch",
                           data["statikk-shiv"]["_patch"])
    if key == "hwei_kit":
        lines = raw.split("\n")
        for i, line in enumerate(lines):
            s = line.strip()
            if s.startswith('"passive":'):
                lines[i] = f'  "passive": {_compact(data["passive"])},'
            for code, spell in data["spells"].items():
                if s.startswith(f'"{code}": {{'):
                    comma = "," if s.endswith(",") else ""
                    lines[i] = f'    "{code}": {_compact(spell)}{comma}'
            if s.startswith('"patch":'):
                lines[i] = f'  "patch": {json.dumps(data["patch"])},'
            if s.startswith('"note":'):
                lines[i] = f'  "note": {json.dumps(data["note"], ensure_ascii=False)},'
        return "\n".join(lines)
    raise KeyError(key)


def render(key: str, path: Path, data) -> bytes:
    """The bytes this file should hold. Nothing is written here."""
    raw_bytes = path.read_bytes()
    crlf = b"\r\n" in raw_bytes
    raw = raw_bytes.decode("utf-8").replace("\r\n", "\n")
    if key in HAND_FORMATTED:
        new = hand_edit(key, raw, data)
        if json.loads(new) != data:
            raise SystemExit(f"{path.name}: the text edit does not match the intended "
                             f"change; nothing written")
    else:
        tail = "\n" if raw.endswith("\n") else ""
        new = json.dumps(data, indent=2, ensure_ascii=False) + tail
    if crlf:
        new = new.replace("\n", "\r\n")
    return new.encode("utf-8")


# ---------------------------------------------------------------- coverage --
#: Every line of the parse, and what became of it. Keyed by (heading, line).
COVERAGE = {
    "VOLIBEAR": "applied", "JHIN": "applied", "TRYNDAMERE": "applied", "HWEI": "applied",
    "NOCTURNE": "applied", "YUNARA": "applied", "SENNA": "applied", "YASUO": "applied",
    "Youmuu's Ghostblade": "applied", "Locket of the Iron Solari": "applied",
    "Thornmail": "applied", "Warmog’s Heart": "applied", "Statikk Shiv": "applied",
    "Yun Tal Wildarrows": "applied", "Electrocute": "applied", "Cheap Shot": "applied",
    "Grasp of the Undying": "applied", "Aery": "applied",
    "Crimson Raptor": "not modelled: no jungle camp data on the site",
    "Raptor": "not modelled: no jungle camp data on the site",
    "AAA ARAM": "mode-only: the site models ranked Summoner's Rift",
    "BUG FIXES": "no data: client fixes, nothing on the site states the bugged values",
}
ARAM = {"Soothing Slipstream", "Rock Solid", "Poro Head", "Origin: Lethal Tempo",
        "Eureka", "Upgrade Sword of Blossoming Dawn", "Bigger and Bigger",
        "Goliath", "Fast and Furious"}


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
            title = b["title"]
            if title in COVERAGE or title in ARAM or (b.get("path") or [""])[0] == "BUG FIXES":
                continue
            gaps.append(f"{' > '.join(b.get('path') or [title])}: {b['lines']}")
    return gaps


# -------------------------------------------------------------------- main --
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true", help="apply; default is a dry run")
    args = ap.parse_args(argv)

    notes = json.loads(NOTES.read_text(encoding="utf-8"))
    gaps = check_coverage(notes)
    if gaps:
        print("lines in the 7.3b notes that this script does not account for:")
        for g in gaps:
            print("   ", g)
        return 2

    data = {k: load(k) for k in FILES}
    apply_items(data["items"], data["item_fx"])
    apply_runes(data["runes"], data["wrmeta_runes"], data["rune_engine"], data["rune_effects"])
    apply_champions(data["champions"], data["formulas"])
    sync_hwei_kit(data["hwei_kit"], data["formulas"])
    for k in ("item_rules", "rune_rules", "stat_overrides"):
        field(f"{FILES[k].name} targetPatch", data[k], ["targetPatch"], "7.3a", PATCH)

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
    # Render EVERY file before writing ANY. A hand-edited file can refuse,
    # and refusing after others were already written would leave the data
    # half on 7.3b.
    out = {k: render(k, FILES[k], data[k]) for k in FILES}
    for k, blob in out.items():
        FILES[k].write_bytes(blob)
    print(f"\nwrote {len(FILES)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
