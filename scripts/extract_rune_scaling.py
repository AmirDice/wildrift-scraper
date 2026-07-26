"""What every rune is worth once it is fully stacked.

The existing rune models were built for the damage engine, so they only cover
what damage needs: procs, ratios, amps. Fifteen runes had no model at all --
including Legend: Tenacity, Legend: Alacrity, Lethal Tempo and Second Wind --
which meant the "fully scaled" stat view silently ignored them.

This file closes that gap. Every entry below is transcribed from the champion
patch text in data/wrmeta_runes.json (the 7.2 canon), and every entry carries
the phrase it came from. On each run the script checks that phrase still
appears in the current rune text: when Riot changes a rune, the entry is
dropped with a warning instead of quietly shipping last patch's number. That is
the whole point of the evidence field -- these numbers are not allowed to be
remembered, only read.

Two kinds of value:

  stats    something you carry into the fight and can add to a stat sheet
           (tenacity, attack speed, max health, omnivamp ...)
  effects  real, quantified, but not a stat: proc damage, shields, transient
           speed. Shown next to the sheet rather than folded into it, because
           adding Dark Harvest's damage to your Attack Damage would be a lie.

Values that scale with level are written [level 1, level 15]. Values that
differ for melee and ranged champions are written as a melee/ranged pair.

Run:
    python -m scripts.extract_rune_scaling
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNES = ROOT / "data" / "wrmeta_runes.json"
OUT = ROOT / "data" / "rune_scaling.json"
WEB_OUT = ROOT / "web-next" / "src" / "data" / "rune_scaling.json"

# stat keys line up with the frontend stat sheet (ListedBuildStats)
MODEL: dict[str, dict] = {
    # ── Precision: the "Legend" line is exactly what the old model missed ────
    "Legend: Tenacity": {
        "evidence": "additional 15% Tenacity and 20% Slow Resist",
        "stats": [{"stat": "tenacity", "value": 18, "note": "3% base + 15% at full takedown stacks"}],
        "effects": [{"label": "Slow resist", "value": "23%", "note": "3% base + 20% at full stacks"}],
    },
    "Legend: Alacrity": {
        "evidence": "additional 18% Attack Speed",
        "stats": [{"stat": "attackSpeedPct", "value": 21, "note": "3% base + 18% at full takedown stacks"}],
    },
    "Legend: Bloodline": {
        "evidence": "additional 7% Omnivamp",
        "stats": [{"stat": "omnivamp", "value": 8, "note": "1% base + 7% at full takedown stacks"}],
    },
    "Triumph": {
        "evidence": "restore 10% of lost health",
        "effects": [{"label": "Takedown reset", "value": "10% lost Health, 10% max Mana, 35 Move Speed",
                     "note": "on champion takedown, 2s"}],
    },
    "Brutal": {
        "evidence": "bonus adaptive damage to enemy champions",
        "effects": [{"label": "On-hit damage", "value": "5 + 6% bonus AD + 3% AP", "note": "every attack"}],
    },
    "Battle Zeal": {
        "evidence": "1.4% stacking basic ability damage amplification",
        "effects": [{"label": "Ability damage amp", "value": "4.2%", "note": "1.4% per stack, 3 stacks in combat"}],
    },
    "Last Stand": {
        "evidence": "deal 5-11% bonus adaptive damage",
        "effects": [{"label": "Damage amp", "value": "up to 11%", "note": "below 60% Health, max below 30%"}],
    },
    "Cut Down": {
        "evidence": "6.57% bonus adaptive damage",
        "effects": [{"label": "Damage amp", "value": "6.57%", "note": "vs champions above 60% Health"}],
    },
    "Coup de Grace": {
        "evidence": "8% bonus adaptive damage",
        "effects": [{"label": "Damage amp", "value": "8%", "note": "vs champions below 40% Health"}],
    },

    # ── Resolve: durability that only exists once stacked ────────────────────
    "Overgrowth": {
        "evidence": "permanently gain 3 max Health",
        "stats": [
            {"stat": "hp", "value": 90, "note": "3 Health per 3 minions, 90 by the 30-stack milestone"},
            {"stat": "hpPctMax", "value": 3, "note": "+3% max Health at 30 stacks"},
        ],
        "effects": [{"label": "Beyond 30 stacks", "value": "+3 Health per 3 minions",
                     "note": "uncapped, keeps growing all game"}],
    },
    "Second Wind": {
        "evidence": "Gain 5 Health",
        "stats": [{"stat": "hpRegen", "value": 5, "note": "flat 5 Health every 5 seconds"}],
        "effects": [{"label": "After taking damage", "value": "3 + 1.5% missing Health over 5s",
                     "note": "doubled for melee champions"}],
    },
    "Perseverance": {
        "evidence": "Gain 10% Tenacity",
        # Unconditional, so the guaranteed sheet carries it; see Celerity below.
        "stats": [{"stat": "tenacity", "value": 10, "note": "always on",
                   "alreadyGuaranteed": True}],
        "effects": [{"label": "While immobilised", "value": "10-15 Armor and Magic Resist", "note": "1.5s, refreshes"}],
    },
    "Unshakeable": {
        "evidence": "Gain 3% Armor and Magic Resistance",
        "stats": [
            {"stat": "armorPct", "value": 9, "note": "3% base + 2% per nearby enemy, 3 enemies"},
            {"stat": "mrPct", "value": 9, "note": "3% base + 2% per nearby enemy, 3 enemies"},
        ],
        "effects": [{"label": "Slow resist", "value": "20%", "note": "only with 3 enemies nearby"}],
    },
    "Revitalize": {
        "evidence": "5% amplification effect when Healing or granting Shields",
        "stats": [{"stat": "healShieldPower", "value": 15, "note": "5% base, 15% on targets below 40% Health"}],
    },
    "Bone Plating": {
        "evidence": "deal 30-60 (based on level) less damage",
        "effects": [{"label": "Damage blocked", "value": [30, 60], "note": "next 4 hits within 1.5s, 40s cooldown"}],
    },
    "Nullifying Orb": {
        "evidence": "shield that absorbs up to 60-180",
        "effects": [{"label": "Shield", "value": [60, 180], "note": "when dropping below 35% Health"}],
    },
    "Courage of the Colossus": {
        "evidence": "absorbs up to 25-45",
        "effects": [{"label": "Shield", "value": [25, 45], "note": "+1% max Health, on immobilising a champion"}],
    },
    "Font of Life": {
        "evidence": "Heal for 1% of your max",
        "effects": [{"label": "Self heal", "value": "1% max Health + 5% AP", "note": "130% effective if melee"}],
    },
    "Demolish": {
        "evidence": "100 + 22% max Health",
        "effects": [{"label": "Turret damage", "value": "100 + 22% max Health", "note": "at 6 charges"}],
    },

    # ── Domination ───────────────────────────────────────────────────────────
    "Eyeball Collector": {
        "evidence": "stacking up to 8 times",
        "stats": [{"stat": "adaptive", "ad": 12, "ap": 24, "note": "1.5 AD or 3 AP per takedown, 8 stacks"}],
    },
    "Zombie Ward": {
        "evidence": "max 5 stacks",
        "stats": [{"stat": "adaptive", "ad": 15, "ap": 30, "note": "3 AD or 6 AP per ward takedown, 5 stacks"}],
    },
    "Relentless Hunter": {
        "evidence": "Gain 10 out-of-combat Movement Speed",
        "effects": [{"label": "Out-of-combat Move Speed", "value": "20", "note": "10 base + 2 per takedown, 5 stacks"}],
    },
    "Ingenious Hunter": {
        "evidence": "Gains 20 Item Ability Haste",
        "effects": [{"label": "Item Ability Haste", "value": "45", "note": "20 base + 5 per takedown, 5 stacks"}],
    },
    "Hubris": {
        "evidence": "5 + 1 per champion kill",
        "effects": [{"label": "Adaptive Force", "value": "5 + 1 per kill", "note": "30s after a takedown, uncapped"}],
    },
    "Cheap Shot": {
        "evidence": "10-45 bonus true damage",
        "effects": [{"label": "True damage", "value": [10, 45], "note": "vs movement-impaired targets, 7s cooldown"}],
    },
    "Sudden Impact": {
        "evidence": "bonus 15-65 true damage",
        "effects": [{"label": "True damage", "value": [15, 65], "note": "after a dash, blink or stealth exit"}],
    },
    "Empowered Attack": {
        "evidence": "20-60 bonus adaptive damage",
        "effects": [{"label": "Adaptive damage", "value": [20, 60], "note": "every 8s; ranged deal 80%"}],
    },
    "Chain Assault": {
        "evidence": "12-38 (based on level)",
        "effects": [{"label": "Adaptive damage", "value": [12, 38], "note": "+3% bonus AD +1.5% AP, next 2 hits"}],
    },
    "Tyrant": {
        "evidence": "20-70 (based on level)",
        "effects": [{"label": "Adaptive damage", "value": [20, 70], "note": "+6% bonus AD +3% AP, below 50% Health"}],
    },

    # ── Sorcery ──────────────────────────────────────────────────────────────
    "Manaflow Band": {
        "evidence": "up to 300 mana",
        "stats": [{"stat": "mana", "value": 300, "note": "30 per ability hit, capped at 300"}],
    },
    "Absolute Focus": {
        "evidence": "bonus 2–20 Attack Damage",
        "stats": [{"stat": "adaptive", "ad": 20, "ap": 30, "note": "at level 15, while above 65% Health"}],
    },
    "Gathering Storm": {
        "evidence": "2/5/9/14",
        "stats": [{"stat": "adaptive", "ad": 14, "ap": 28, "note": "fourth step, roughly 20 minutes in"}],
    },
    "Celerity": {
        "evidence": "Gain 2% Movement Speed",
        # Both halves are unconditional, so the guaranteed sheet applies them
        # itself (see listedBuildStats); scaled mode must not add them twice.
        "stats": [{"stat": "moveSpeedPct", "value": 2, "note": "always on",
                   "alreadyGuaranteed": True}],
        "effects": [{"label": "Move Speed amp", "value": "+7%", "note": "applies to every other Move Speed bonus"}],
    },
    "Transcendence": {
        "evidence": "gain 5 Ability Haste",
        "stats": [{"stat": "haste", "value": 10, "note": "5 at level 1, 5 more at level 5",
                   "alreadyGuaranteed": True}],
        "effects": [{"label": "Cooldown refund", "value": "8%", "note": "on basic ability hit from level 9"}],
    },
    "Scorch": {
        "evidence": "21-49 bonus magic damage",
        "effects": [{"label": "Magic damage", "value": [21, 49], "note": "on ability hit, 8s cooldown"}],
    },
    "Nimbus Cloak": {
        "evidence": "10% - 40% movement bonus",
        "effects": [{"label": "Move Speed", "value": "10-40%", "note": "3s after a summoner spell"}],
    },
    "Axiom Arcanist": {
        "evidence": "ultimate ability has 10% increased damage",
        "effects": [{"label": "Ultimate amp", "value": "10%", "note": "5% for area damage; 7% cooldown refund on takedown"}],
    },

    # ── Keystones ────────────────────────────────────────────────────────────
    "Lethal Tempo": {
        "evidence": "6-14% (Melee) or 3.5-8% (Ranged)",
        "stats": [{"stat": "attackSpeedPct", "melee": 84, "ranged": 48,
                   "note": "6 stacks at level 15: 14% melee or 8% ranged per stack"}],
        "effects": [{"label": "At max stacks", "value": "25 (melee) / 50 (ranged) Attack Distance",
                     "note": "and the Attack Speed cap is lifted"}],
    },
    "Conqueror": {
        "evidence": "3-5 bonus",
        "stats": [
            {"stat": "adaptive", "ad": 30, "ap": 48, "note": "6 stacks at level 15: 5 AD or 8 AP per stack"},
            {"stat": "omnivamp", "melee": 9, "ranged": 5, "note": "only while fully stacked"},
        ],
    },
    "Dark Harvest": {
        "evidence": "increasing Dark Harvest's damage by 11",
        "effects": [{"label": "Soul damage", "value": "35 + 11 per soul",
                     "note": "+10% bonus AD +5% AP; uncapped, 145 at 10 souls"}],
    },
    "Electrocute": {
        "evidence": "40-210 (based on level)",
        "effects": [{"label": "Burst damage", "value": [40, 210], "note": "+10% bonus AD +5% AP, on a 3-hit combo"}],
    },
    "Empowerment": {
        "evidence": "amplifies your damage dealt by 8%",
        "effects": [
            {"label": "Adaptive damage", "value": [40, 165], "note": "on a 3-attack combo"},
            {"label": "Damage amp", "value": "8%", "note": "until you leave combat"},
        ],
    },
    "Grasp of the Undying": {
        "evidence": "Permanently health increase: 10",
        "effects": [
            {"label": "Permanent Health", "value": "10 per proc", "note": "uncapped; 60% weaker on ranged champions"},
            {"label": "Proc", "value": "3.3% max Health magic damage, 1.3% max Health heal", "note": "every 3s in combat"},
        ],
    },
    "Phase Rush": {
        "evidence": "Ability Haste: 10",
        "stats": [{"stat": "haste", "value": 10, "note": "while Phase Rush is active"}],
        "effects": [{"label": "Move Speed", "value": "40-60% melee, 20-35% ranged", "note": "3s, plus 60% slow resist"}],
    },
    "Fleet Footwork": {
        "evidence": "Bonus Attack Speed: 40%",
        "effects": [
            {"label": "Empowered attack", "value": "40% Attack Speed", "note": "at 100 energy stacks"},
            {"label": "Heal", "value": [15, 110], "note": "+15% bonus AD +10% AP"},
        ],
    },
    "First Strike": {
        "evidence": "7% bonus true damage",
        "effects": [{"label": "True damage amp", "value": "7%", "note": "3s from the opening hit, plus gold"}],
    },
    "Aery": {
        "evidence": "Damage: 15-70 (based on level)",
        "effects": [{"label": "Damage or shield", "value": [15, 70], "note": "shield 25-120; +10% bonus AD +5% AP"}],
    },
    "Arcane Comet": {
        "evidence": "(15 to 100)",
        "effects": [{"label": "Ability damage", "value": [15, 100], "note": "+2 per previous hit, +10% bonus AD +5% AP"}],
    },
    "Guardian": {
        "evidence": "Shield: 40–165",
        "effects": [{"label": "Ally shield", "value": [40, 165], "note": "+6% bonus Health +15% AP"}],
    },
    "Ice Overlord": {
        "evidence": "35 + 75% bonus Armor and Magic Resist",
        "effects": [
            {"label": "Defenses", "value": "35 + 75% bonus Armor and MR", "note": "2.5s after immobilising"},
            {"label": "Magic damage", "value": [15, 100], "note": "+5% max Health"},
        ],
    },
}


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").replace("–", "-").replace("—", "-").lower()


def main() -> None:
    runes = json.loads(RUNES.read_text(encoding="utf-8"))
    text_by_name = {rune["name"]: rune.get("text", "") for rune in runes}

    out: dict[str, dict] = {}
    stale: list[str] = []
    for name, model in MODEL.items():
        source = text_by_name.get(name)
        if source is None:
            stale.append(f"{name}: not in the rune pool any more")
            continue
        evidence = _normalise(model["evidence"])
        if evidence not in _normalise(source):
            stale.append(f"{name}: text no longer contains {model['evidence']!r}")
            continue
        entry = {key: value for key, value in model.items() if key != "evidence"}
        entry["evidence"] = model["evidence"]
        out[name] = entry

    unmodelled = sorted(set(text_by_name) - set(out))

    payload = {
        "targetPatch": "7.2",
        "source": "data/wrmeta_runes.json",
        "note": "Maximum modelled value of each rune: full stacks, full ramp. "
                "'stats' fold into the stat sheet; 'effects' are quantified but are not stats.",
        "runes": out,
        "unmodelled": unmodelled,
    }
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    OUT.write_text(body, encoding="utf-8")
    WEB_OUT.write_text(body, encoding="utf-8")

    print(f"modelled {len(out)} of {len(text_by_name)} runes")
    print(f"wrote {OUT.relative_to(ROOT)} + {WEB_OUT.relative_to(ROOT)}")
    if unmodelled:
        print("\nno scaling value (utility, vision, gold, or nothing quantifiable):")
        print("  " + ", ".join(unmodelled))
    if stale:
        print("\nSTALE ENTRIES DROPPED -- the rune text changed, re-read it:")
        for line in stale:
            print(f"  {line}")


if __name__ == "__main__":
    main()
