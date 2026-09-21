"""Apply patch 7.3's champion BASE STATS, including the new attack speed model.

Three sources inside the notes, all read from data/patch_notes_7_3.json:

  1. The champion change blades ("EZREAL / Base Stats / Base Attack Damage:
     58 -> 60"), which are the patch's own list.
  2. The durability appendix: 51 champions' Health, Armour and Magic Resist.
  3. The attack speed appendix: all 141 of ours, as four numbers each.

ATTACK SPEED IS A NEW MODEL

    7.3 restates attack speed for every champion and publishes the formula:

        total       = base + ratio x bonus
        bonus       = baseBonus + perLevel x sum(0.7 + 0.04 x l) + items/runes
        at level 15 = baseBonus + 14 x perLevel

    Base and ratio are the same number for every champion in the appendix, so
    the engines' existing shape -- a ratio multiplied by (1 + bonus) -- still
    holds; what changes is that the innate bonus and the growth are now known
    for the whole roster instead of the eight champions the owner measured by
    hand. Those measurements are kept in the file under `measuredBefore7_3`:
    they were right for 7.2 and they are the only check we have on the new
    table.

    Our champions_wr.json keeps storing attack speed the way the site shows it
    (the level 1 total, the level 15 total, and a per-level step between them),
    because that is what a champion page prints. The four official numbers live
    in data/champion_attack_speed.json, which is what the engines read.

WHERE THE NOTES DISAGREE WITH THEMSELVES

    Caitlyn's base bonus attack speed is 0.28 in her own change block and in
    the worked example in the appendix, and 0.2 in the appendix table. The
    champion block wins: it is the patch's own change list, and it agrees with
    the example. Every conflict of this kind is printed.

Run:
    python -m scripts.apply_patch_7_3_champion_stats
    python -m scripts.apply_patch_7_3_champion_stats --write
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PATCH = "7.3"

CHAMPIONS = DATA / "champions_wr.json"
AS_FILE = DATA / "champion_attack_speed.json"
OVERRIDES = DATA / "champion_stat_overrides.json"
NOTES = DATA / "patch_notes_7_3.json"

#: Notes label -> (our stat, which half of it)
BASE_STATS = {
    "base health": ("hp", "base"),
    "health per level": ("hp", "perLevel"),
    "base armor": ("armor", "base"),
    "armor per level": ("armor", "perLevel"),
    "base magic resist": ("mr", "base"),
    "magic resist per level": ("mr", "perLevel"),
    "base attack damage": ("ad", "base"),
    "attack damage per level": ("ad", "perLevel"),
    "base mana": ("mana", "base"),
    "mana per level": ("mana", "perLevel"),
}

#: The four numbers that define attack speed from 7.3 on.
AS_STATS = {
    "attack speed ratio": "attackSpeedRatio",
    "base attack speed": "baseAttackSpeed",
    "base bonus attack speed": "baseBonusAttackSpeed",
    "attack speed per level": "attackSpeedPerLevel",
}

MAX_LEVEL = 15


def key_of(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").lower().replace("’", "'")
    return re.sub(r"[^a-z0-9]", "", text)


def number(text: str) -> float | None:
    m = re.match(r"^([0-9]+(?:\.[0-9]+)?)", (text or "").strip())
    return float(m.group(1)) if m else None


def level_bonus(per_level: float, level: int) -> float:
    """Bonus attack speed a champion has gained by `level` from levelling.

    Riot's own wording: each level up grants perLevel x (0.7 + 0.04 x current
    level), which sums to exactly 14 x perLevel at level 15.
    """
    return per_level * sum(0.7 + 0.04 * l for l in range(1, level))


def blocks(notes: dict):
    """(champion name as published, block title, lines) over the whole page."""
    for blade in notes["blades"]:
        if blade["kind"] == "champion":
            for block in blade["blocks"]:
                yield blade["champion"], block["title"], block["lines"], "champion block"
        else:
            for block in blade["blocks"]:
                yield block["title"], block["title"], block["lines"], "appendix"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    notes = json.loads(NOTES.read_text(encoding="utf-8"))
    champions = json.loads(CHAMPIONS.read_text(encoding="utf-8"))
    as_file = json.loads(AS_FILE.read_text(encoding="utf-8"))
    overrides = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    by_key = {key_of(c["name"]): c for c in champions}

    applied: list[str] = []
    problems: list[str] = []
    conflicts: list[str] = []
    as_table: dict[str, dict] = {}
    as_source: dict[str, str] = {}
    #: (champion, stat, half) the patch actually moved, so the stat overrides
    #: below can follow exactly those and nothing else.
    touched: set[tuple[str, str, str]] = set()

    for published, title, lines, where in blocks(notes):
        champ = by_key.get(key_of(published))
        if champ is None:
            continue
        stats = champ.setdefault("baseStats", {})
        for line in lines:
            m = re.match(r"^([A-Za-z' ]+?)\s*:\s*(.+)$", line)
            if not m:
                continue
            label, rest = m.group(1).strip().lower(), m.group(2).strip()
            if label in AS_STATS:
                value = number(rest)
                if value is None:
                    continue
                name = champ["name"]
                key = AS_STATS[label]
                have = as_table.setdefault(name, {})
                # The champion's own block is the patch's change list; the
                # appendix is a table reprinted beside it. When they disagree,
                # the block wins and the disagreement is printed.
                if key in have and abs(have[key] - value) > 1e-9:
                    if as_source.get(name) == "champion block":
                        conflicts.append(f"{name} {key}: block {have[key]:g}, appendix {value:g} "
                                         f"-- kept the block")
                        continue
                    conflicts.append(f"{name} {key}: appendix {have[key]:g}, block {value:g} "
                                     f"-- kept the block")
                have[key] = value
                if where == "champion block":
                    as_source[name] = where
                elif name not in as_source:
                    as_source[name] = where
                continue

            if label not in BASE_STATS:
                continue
            stat, half = BASE_STATS[label]
            old, new = None, None
            if "→" in rest:
                old_text, new_text = [t.strip() for t in rest.split("→")[:2]]
                old, new = number(old_text), number(new_text)
            else:
                new = number(rest)
            if new is None:
                continue
            entry = stats.setdefault(stat, {"base": 0.0, "perLevel": 0.0, "lvl15": 0.0})
            have = entry.get(half)
            if old is not None and (have is None or abs(float(have) - old) > 0.001):
                held = "nothing" if have is None else f"{float(have):g}"
                problems.append(f'{champ["name"]} {stat}.{half}: notes say {old:g}, we hold {held}')
            entry[half] = new
            touched.add((champ["name"], stat, half))
            entry["lvl15"] = round(entry.get("base", 0.0)
                                   + entry.get("perLevel", 0.0) * (MAX_LEVEL - 1), 4)
            applied.append(f'{champ["name"]} {stat}.{half} = {new:g}')

    # -- attack speed: write the official four numbers, then restate the
    #    champion sheet (level 1 and level 15 totals) from them.
    missing_as = [c["name"] for c in champions if c["name"] not in as_table]
    for name, row in as_table.items():
        champ = by_key[key_of(name)]
        ratio = row.get("attackSpeedRatio")
        base = row.get("baseAttackSpeed", ratio)
        bonus = row.get("baseBonusAttackSpeed", 0.0)
        per_level = row.get("attackSpeedPerLevel", 0.0)
        if ratio is None:
            problems.append(f"{name}: attack speed rows without a ratio")
            continue
        level1 = base + ratio * bonus
        level15 = base + ratio * (bonus + level_bonus(per_level, MAX_LEVEL))
        champ["baseStats"]["attackSpeed"] = {
            "base": round(level1, 4),
            # A display step, not the game's curve: levelling is front-loaded
            # (0.74 of a step from 1 to 2, 1.26 from 14 to 15). The engines read
            # the real four numbers from champion_attack_speed.json.
            "perLevel": round((level15 - level1) / (MAX_LEVEL - 1), 5),
            "lvl15": round(level15, 4),
        }
        applied.append(f"{name} attackSpeed {level1:.3f} at 1, {level15:.3f} at 15")

    old_curve = (as_file.get("champions") or {})
    as_file["patch"] = PATCH
    as_file["_note"] = (
        "Attack speed as patch 7.3 defines it, from the appendix of the official "
        "notes: total = baseAttackSpeed + attackSpeedRatio x bonus, where bonus is "
        "baseBonusAttackSpeed + attackSpeedPerLevel x sum(0.7 + 0.04 x level) over "
        "the levels gained, plus items and runes. At level 15 the level term is "
        "exactly 14 x attackSpeedPerLevel."
    )
    as_file["_why_not_derived"] = (
        "Riot publishes these per champion and nothing predicts them: among mages "
        "alone the per-level figure runs from 0.005 to 0.04. Before 7.3 the file "
        "held eight champions the owner measured in game, kept below as "
        "measuredBefore7_3 -- they are the only independent check on this table."
    )
    as_file.pop("_how_to_add", None)
    if old_curve and "measuredBefore7_3" not in as_file:
        as_file["measuredBefore7_3"] = old_curve
    as_file["champions"] = {
        name: {**row, "source": as_source.get(name, "appendix")}
        for name, row in sorted(as_table.items())
    }

    # -- the champions whose stats are overridden at export time, because the
    #    owner read them in game and the scrape had them wrong. An override
    #    written for an older patch silently wins over anything changed here,
    #    which is how a fix can look applied and not be.
    #
    #    ONLY what this patch actually changed is copied across. Syncing the
    #    whole block would overwrite the owner's readings with the scrape they
    #    were written to correct -- it put Kayn's level-15 attack damage back to
    #    112 when the game says 126.
    for name, entry in (overrides.get("champions") or {}).items():
        champ = by_key.get(key_of(name))
        if not champ:
            continue
        for stat, values in (entry.get("baseStats") or {}).items():
            ours = champ["baseStats"].get(stat) or {}
            for half in ("base", "perLevel"):
                if (name, stat, half) not in touched or half not in values:
                    continue
                if abs(float(values[half]) - float(ours.get(half, 0))) > 0.001:
                    values[half] = ours.get(half, values[half])
                    values["lvl15"] = round(values.get("base", 0.0)
                                            + values.get("perLevel", 0.0) * (MAX_LEVEL - 1), 4)
                    applied.append(f"{name}: override {stat}.{half} follows 7.3")
        # Attack speed is restated for the whole roster in 7.3, so an override
        # holding a 7.2 reading of it is out of date by definition.
        if "attackSpeed" in (entry.get("baseStats") or {}) and champ["name"] in as_table:
            entry["baseStats"]["attackSpeed"] = dict(champ["baseStats"]["attackSpeed"])
            applied.append(f"{name}: override attackSpeed follows the 7.3 table")

    # A transform form is the same body with different abilities, and only the
    # base name appears in the notes. Kayn (Rhaast) would otherwise keep 7.2's
    # attack speed while Kayn moved to the new table.
    for name, entry in (overrides.get("champions") or {}).items():
        base_name = name.split(" (")[0]
        if base_name == name or base_name not in as_table:
            continue
        base_champ = by_key.get(key_of(base_name))
        if not base_champ:
            continue
        entry.setdefault("baseStats", {})["attackSpeed"] = dict(
            base_champ["baseStats"]["attackSpeed"])
        applied.append(f"{name}: attack speed follows {base_name}")
    overrides["targetPatch"] = PATCH

    print(f"APPLIED ({len(applied)})")
    for line in applied[:40]:
        print(f"  {line}")
    if len(applied) > 40:
        print(f"  ... and {len(applied) - 40} more")
    if conflicts:
        print(f"\nTHE NOTES DISAGREE WITH THEMSELVES ({len(conflicts)}):")
        for line in conflicts:
            print(f"  {line}")
    if missing_as:
        print(f"\nNO ATTACK SPEED ROW ({len(missing_as)}): {', '.join(missing_as)}")
    if problems:
        print(f"\nDISAGREEMENTS WITH OUR DATA ({len(problems)}):")
        for line in problems:
            print(f"  {line}")

    if args.write:
        CHAMPIONS.write_text(json.dumps(champions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        AS_FILE.write_text(json.dumps(as_file, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        OVERRIDES.write_text(json.dumps(overrides, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("\nwrote champions_wr.json, champion_attack_speed.json, champion_stat_overrides.json")
    else:
        print("\ndry run: pass --write to save")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
