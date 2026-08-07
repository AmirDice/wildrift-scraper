"""Apply the patch 7.2 changes that the Jul 6 scrape predates.

data/champions_wr.json and data/runes.json were scraped on Jul 6, 2026 -- two
days BEFORE patch 7.2 dropped on Jul 8. Everyone downstream assumed the base
was 7.2 and applied 7.2a / 7.2b as deltas on top, so the 7.2 changes themselves
were never landed in these two files:

  - 14 champions (the audit found Lee Sin Q/E/R, Zed R cooldown, Yasuo W
    cooldown + E cap + R pen, Zyra plants, Norra banish, Varus blight timing
    expressible in our text; the rest are ranges and [New] mechanics the
    tooltips never carried)
  - the 7.2 "broad nerfs across most runes" (~30 runes; Transcendence and
    Eyeball Collector already carry 7.2 values from the Jul 26 partial
    refresh, and Botanist was taken to its 7.2b value of 10 gold directly)

data/items.json is NOT touched: it was re-scraped Jul 19 from wr-meta at 7.2,
and the four items 7.2 reworked (Stridebreaker, Goredrinker, Quicksilver Sash,
Mercurial Scimitar) verify against the official notes exactly.

Transcribed from the official notes:

    https://wildrift.leagueoflegends.com/en-us/news/game-updates/wild-rift-patch-notes-7-2/

Ranked only, same exclusion as the 7.2a / 7.2b scripts.

Every edit asserts the CURRENT value first and tolerates finding the NEW value
(so a re-run is a no-op, not an error). A value matching neither fails loudly.

Run:
    python -m scripts.apply_patch_7_2_gaps            # dry run
    python -m scripts.apply_patch_7_2_gaps --write

After --write, the downstream regeneration this script does NOT do:
    python -m scripts.extract_formulas --only "<changed champions>"
    python -m scripts.export_engine_data
    python -m scripts.export_champion_details
and the advisor must be redeployed (champions_wr.json is an advisor source).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# (rune_name, old_substring, new_substring)
RUNE_TEXT = [
    ("Electrocute",
     "40 - 194 (based on level) (+35% bonus AD) (+20% AP)",
     "40 - 210 (based on level) (+10% bonus AD) (+5% AP)"),
    ("Dark Harvest",
     "permanently increasing Dark Harvest's damage by 10.",
     "permanently increasing Dark Harvest's damage by 11."),
    ("Dark Harvest",
     "Damage: 40 + 10 per soul (+25% bonus AD +15% bonus AP)",
     "Damage: 35 + 11 per soul (+10% bonus AD +5% bonus AP)"),
    ("Empowerment",
     "deals 60 - 200 bonus adaptive damage (based on level)",
     "deals 40 - 165 bonus adaptive damage (based on level)"),
    ("Empowerment",
     "increases your damage dealt by 9%",
     "increases your damage dealt by 8%"),
    # NB: the source text uses en-dashes with spaces here; matched verbatim.
    ("Lethal Tempo",
     "Each stack increases Attack Speed by 8 – 16% (melee) or 3 – 10% (ranged)",
     "Each stack increases Attack Speed by 6 – 14% (melee) or 3.5 – 8% (ranged)"),
    ("Lethal Tempo",
     "gain 50 (melee) or 75 (ranged) Attack Distance",
     "gain 25 (melee) or 50 (ranged) Attack Distance"),
    ("Fleet Footwork",
     "your next attack gains 100% Attack Speed",
     "your next attack gains 40% Attack Speed"),
    ("Fleet Footwork",
     "Heal: 15 - 85 + 30% bonus Attack Damage + 30% Ability Power",
     "Heal: 15 - 110 + 15% bonus Attack Damage + 10% Ability Power"),
    ("Conqueror",
     "grants 3 - 7 (based on level)",
     "grants 3 - 5 (based on level)"),
    ("Conqueror",
     "or Ability Power 4 - 11 (based on level)",
     "or Ability Power 4 - 8 (based on level)"),
    ("Grasp of the Undying",
     "restore 2.5% of your maximum health",
     "restore 1.3% of your maximum health"),
    ("Guardian",
     "(45 - 180 + 5% bonus Health + 15% Ability Power)",
     "(40 - 165 + 6% bonus Health + 15% Ability Power)"),
    ("Guardian",
     "cooldown: 40s - 20s",
     "cooldown: 55s - 25s"),
    ("Aery",
     "(+20% bonus AD) (+10% AP) Adaptive damage",
     "(+10% bonus AD) (+5% AP) Adaptive damage"),
    ("Aery",
     "shielding them for 30 - 140 (based on level) (+40% bonus AD) (+20% AP)",
     "shielding them for 25 - 120 (based on level) (+10% bonus AD) (+5% AP)"),
    ("Arcane Comet",
     "Damage: 18 - 95 + (3 x total hits on enemy champions) + 35% bonus Attack Damage + 20% Ability Power",
     "Damage: 15 - 100 + (2 x total hits on enemy champions) + 10% bonus Attack Damage + 5% Ability Power"),
    ("Phase Rush",
     "Ranged 30% / 50%)",
     "Ranged 20% / 35%)"),
    ("Phase Rush",
     "25 Ability Haste",
     "10 Ability Haste"),
    ("Phase Rush",
     "Cooldown: 12s",
     "Cooldown: 21s - 7s (based on level)"),
    ("First Strike",
     "(melee: 100%/ranged: 85%)",
     "(melee: 60%/ranged: 45%)"),
    ("Ice Overlord",
     "slowing enemies inside by (20% + 1.5% Bonus Health)",
     "slowing enemies inside by (15% + 1% Bonus Health)"),
    ("Ice Overlord",
     "by 35+80% Bonus Armor and Magic Resistance",
     "by 35+75% Bonus Armor and Magic Resistance"),
    ("Ice Overlord",
     "dealing 25-125 + 5% Bonus Health magic damage",
     "dealing 15-100 + 5% Bonus Health magic damage"),
    # NB: en-dash, no spaces ("10–80").
    ("Sudden Impact",
     "bonus 10–80 true damage",
     "bonus 15–65 true damage"),
    ("Sudden Impact",
     "Level 5: Deal an additional 10 true damage",
     "Level 5: Deal an additional 5 true damage"),
    ("Sudden Impact",
     "Level 9: Deal an additional 20 true damage",
     "Level 9: Deal an additional 5 true damage"),
    ("Zombie Ward",
     "Additionally gain 4 Attack Damage or 8 Ability Power",
     "Additionally gain 3 Attack Damage or 6 Ability Power"),
    ("Empowered Attack",
     "dealing 35 - 50 bonus adaptive damage",
     "dealing 20 - 60 bonus adaptive damage"),
    ("Chain Assault",
     "deal 20 - 35 (+5% bonus AD +2.5% bonus AP)",
     "deal 12 - 38 (+3% bonus AD +1.5% bonus AP)"),
    ("Tyrant",
     "deal 30 - 50 (+7.5% bonus AD +3.5% AP)",
     "deal 20 - 70 (+6% bonus AD +3% AP)"),
    ("Hextech Flashtraption",
     "(25 seconds of cooldown)",
     "(18 seconds of cooldown)"),
    ("Unshakeable",
     "Gain 4% Armor and Magic Resist.",
     "Gain 3% Armor and Magic Resist."),
    ("Unshakeable",
     "gain an additional 3% Armor and Magic Resist",
     "gain an additional 2% Armor and Magic Resist"),
    ("Second Wind",
     "regenerate 6 (+2% of your missing health)",
     "regenerate 3 (+1.5% of your missing health)"),
    ("Overgrowth",
     "When 1 monster or 2 minions are killed nearby",
     "When 3 monsters or 3 minions are killed nearby"),
    ("Courage of the Colossus",
     "(10 seconds cooldown)",
     "(18 seconds cooldown)"),
    ("Font of Life",
     "Heals for 3% of your max Health + 15% of your Ability Power",
     "Heals for 1.5% of your max Health + 5% of your Ability Power"),
    ("Font of Life",
     "Cooldown: 20s",
     "Cooldown: 15s"),
    ("Perseverance",
     "gain 15 - 25 armor and magic resistance",
     "gain 10 - 15 armor and magic resistance"),
    ("Legend: Alacrity",
     "up to 20% at maximum stacks",
     "up to 18% at maximum stacks"),
    ("Brutal",
     "deal 6 (+ 8% Bonus Attack Damage) bonus adaptive damage",
     "deal 5 (+ 6% Bonus Attack Damage + 3% Ability Power) bonus adaptive damage"),
    # The notes give the per-second tick (2% -> 1.4%); the 4.2% cap is that
    # tick times the existing 3-tick structure the text already describes.
    ("Battle Zeal",
     "gain 2% basic ability damage amplification against them every 1s, up to a maximum of 6%",
     "gain 1.4% basic ability damage amplification against them every 1s, up to a maximum of 4.2%"),
    ("Cut Down",
     "deal 8% bonus adaptive damage",
     "deal 6.57% bonus adaptive damage"),
]

# (champion, ability_name_fragment, old_substring, new_substring)
CHAMP_TEXT = [
    ("Lee Sin", "Sonic Wave",
     "deals 55 / 90 / 125 / 160 ( +100% AD ) physical damage to enemies and reveals them",
     "deals 60 / 100 / 140 / 180 ( +90% AD ) physical damage to enemies and reveals them"),
    ("Lee Sin", "Sonic Wave",
     "dealing 55 / 90 / 125 / 160 to 110 / 180 / 250 / 360 ( +100% to +200% AD )",
     "dealing 60 / 100 / 140 / 180 to 120 / 200 / 280 / 360 ( +90% to +180% AD )"),
    ("Lee Sin", "Tempest",
     "Deals 90 / 140 / 190 / 240 ( +125% AD ) magic damage",
     "Deals 35 / 70 / 105 / 140 ( +90% AD ) magic damage"),
    ("Lee Sin", "Dragon's Rage",
     "dealing 100 / 250 / 400 ( +180% bonus AD + 10% / 13% / 16% of the target's maximum health )",
     "dealing 125 / 350 / 575 ( +190% bonus AD + 12% / 15% / 18% of the target's bonus health )"),
    ("Yasuo", "Sweeping Blade",
     "up to + 50%",
     "up to + 75%"),
    ("Yasuo", "Last Breath",
     "Critical Strikes gain 40% Armor Penetration",
     "Critical Strikes gain 55% bonus Armor Penetration"),
    ("Zyra", "Garden of Thorns",
     "dealing 10 - 108 ( +15% AP ) magic damage",
     "dealing 10 - 108 ( +10% AP ) magic damage"),
    ("Varus", "Chain of Corruption",
     "gain 3 Blight stacks over the next 3 seconds",
     "gain 3 Blight stacks over the next 1.5 seconds"),
    ("Norra", "Journey to Nowhere",
     "sending them to another dimension for 2.25 seconds",
     "sending them to another dimension for 1.5 seconds"),
    ("Norra", "Journey to Nowhere",
     "returned to their original location after 2.25 seconds",
     "returned to their original location after 1.5 seconds"),
]

# (champion, ability_name_fragment, old_cooldowns, new_cooldowns)
CHAMP_CDS = [
    ("Yasuo", "Wind Wall", ["18", "18", "18", "18"], ["22", "20", "18", "16"]),
    ("Zed", "Death Mark", ["85", "65", "45"], ["85", "70", "55"]),
]

# Changes the data model or our source text cannot express, recorded rather
# than dropped -- same discipline as the 7.2a / 7.2b scripts.
UNAPPLIED = [
    "Yasuo / Way of the Wanderer shield 115~600 -> 125-680 based on level: our "
    "text reads '115 - 500 (+100% Critical Strike Rate)', matching neither the "
    "notes' old nor new value, so there is nothing safe to assert against",
    "Grasp of the Undying damage 1.5% -> 3.3% max Health: our text reads 2%, "
    "matching neither side (the heal 2.5% -> 1.3% DID match and was applied)",
    "Conqueror max-stack totals: the source text's own maxima (12-36 / 18-54) "
    "never equalled 6x the per-stack values, so only the per-stack numbers the "
    "notes give are changed",
    "Phase Rush slow resist 75% -> 60% (our text carries no slow-resist term)",
    "Bone Plating cooldown 30s -> 40s (our text carries no cooldown)",
    "Hexflash [New] 6s combat lockout (text addition, not a value edit)",
    "Kai'Sa / Killer Instinct landing range 4 -> 5.5 (no range term in text)",
    "Kayn / Umbral Trespass exit distance 4 -> 4.5 / 6 -> 6.5 (no range term)",
    "Syndra / Scatter the Weak knockback range 7.2 -> 7.5 (no range term)",
    "Orianna / Command: Shockwave range 3 -> 3.25 (no range term)",
    "Annie / Tibbers and Zyra / plants [New] magic pen inheritance (mechanic "
    "additions our tooltips never carried)",
    "Darius / Crippling Strike [New] kill refund 50% CD + 100% mana",
    "Norra / Journey to Nowhere [New] post-banish 80% slow for 0.75s",
    "Zed / Death Mark [New] 0.5s recast lockout",
    "Yasuo / Sweeping Blade stack count 2 -> 3 (the 75% cap edit carries the "
    "player-visible number; the text never states the stack count)",
    "Fiddlesticks / Terrify fear-window bugfixes (qualitative)",
    "K'Sante / All Out: our text already reads 'bonus Armor Pen', the 7.2 "
    "wording, so there was nothing to change",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    applied, skipped, failed = [], [], []

    def ok(msg):
        applied.append(msg)
        print(f"  OK    {msg}")

    def already(msg):
        skipped.append(msg)
        print(f"  SKIP  {msg} (already 7.2)")

    def bad(msg):
        failed.append(msg)
        print(f"  MISS  {msg}")

    # ---- runes ------------------------------------------------------------
    runes = json.loads((DATA / "runes.json").read_text(encoding="utf-8"))
    by_name = {r["name"]: r for r in runes}

    print("RUNES")
    for name, old, new in RUNE_TEXT:
        r = by_name.get(name)
        if r is None:
            bad(f"{name}: rune not found")
            continue
        desc = r["description"]
        if old in desc:
            r["description"] = desc.replace(old, new)
            ok(f"{name}: {old[:60]} -> {new[:60]}")
        elif new in desc:
            already(f"{name}: {new[:60]}")
        else:
            bad(f"{name}: expected {old[:80]!r}")

    # ---- champions ---------------------------------------------------------
    champs = json.loads((DATA / "champions_wr.json").read_text(encoding="utf-8"))
    by_champ = {c["name"]: c for c in champs}

    def find_ability(champ_name, fragment):
        c = by_champ.get(champ_name)
        for a in (c or {}).get("abilities") or []:
            if fragment.lower() in a.get("name", "").lower():
                return a
        return None

    print("CHAMPIONS")
    for champ, frag, old, new in CHAMP_TEXT:
        a = find_ability(champ, frag)
        if a is None:
            bad(f"{champ} / {frag}: ability not found")
            continue
        if old in a["text"]:
            a["text"] = a["text"].replace(old, new)
            ok(f"{champ} / {a['name']}: {old[:55]} -> {new[:55]}")
        elif new in a["text"]:
            already(f"{champ} / {a['name']}: {new[:55]}")
        else:
            bad(f"{champ} / {a['name']}: expected {old[:70]!r}")

    for champ, frag, old_cds, new_cds in CHAMP_CDS:
        a = find_ability(champ, frag)
        if a is None:
            bad(f"{champ} / {frag}: ability not found")
            continue
        if a.get("cooldowns") == old_cds:
            a["cooldowns"] = new_cds
            ok(f"{champ} / {a['name']}: cooldowns {old_cds} -> {new_cds}")
        elif a.get("cooldowns") == new_cds:
            already(f"{champ} / {a['name']}: cooldowns {new_cds}")
        else:
            bad(f"{champ} / {a['name']}: cooldowns expected {old_cds}, "
                f"found {a.get('cooldowns')}")

    print(f"\napplied {len(applied)}, already-current {len(skipped)}, "
          f"failed {len(failed)}, unappliable (recorded) {len(UNAPPLIED)}")
    if failed:
        raise SystemExit("asserts failed -- nothing written")
    if not args.write:
        print("dry run -- nothing written (pass --write)")
        return
    (DATA / "runes.json").write_text(
        json.dumps(runes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (DATA / "champions_wr.json").write_text(
        json.dumps(champs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("written: data/runes.json, data/champions_wr.json")


if __name__ == "__main__":
    main()
