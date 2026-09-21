"""Apply patch 7.3's item changes to data/items.json.

    https://wildrift.leagueoflegends.com/en-gb/news/game-updates/wild-rift-patch-notes-7-3/

7.3 is the marksman-ecosystem patch: ten new completed items, three of ours
removed, and stat edits on forty-two more. That is an order of magnitude past
the hand-typed apply scripts of 7.2x, so this one works differently.

HOW IT WORKS

    Every "Stat: old → new" line in the notes is read from the PARSE
    (data/patch_notes_7_3.json, written by scripts/parse_patch_notes.py), not
    retyped here. For each one the script asserts our stored value equals the
    notes' pre-value, then writes the post-value. A line it cannot map, or a
    pre-value that disagrees, is REPORTED rather than skipped, so the patch
    cannot half-land the way 7.2b did.

    What stays hand-written is what the notes cannot give mechanically: the ten
    new item records (category, tags, icon), the passive rewrites, and the
    named drift below.

DRIFT ACCEPTED (the notes' pre-value disagrees with ours; the post-value wins)

    Essence Reaver AD 35, we hold 40. Blade of the Ruined King 3200, we hold
    3000. Navori Quickblades 2800, we hold 2700. Knight's Vow 2600, we hold
    2500. Mantle of the Twelfth Hour 2700, we hold 2900. Zeke's Convergence
    Health 400, we hold 350. Each is a single unambiguous post-value, so it is
    written and the disagreement clears with it.

NAMES

    From 7.3 the site uses Riot's own names, which is what the shop shows:
    Redemption becomes Salvation, Wit's End becomes At Wit's End, Staff of
    Flowing Water becomes Staff of Flowing Waters, Lord Dominik's Regard
    becomes Regards. Slugs do not move: they are keys in ladder records,
    champion builds and icon filenames, and renaming them would orphan all of
    it for a label change.

Run:
    python -m scripts.apply_patch_7_3_items            # dry run + report
    python -m scripts.apply_patch_7_3_items --write

Then: python -m scripts.export_items   (web-next/src/data/items.json is a
separate generated copy -- see the patch checklist).
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ITEMS = DATA / "items.json"
NOTES = DATA / "patch_notes_7_3.json"

PATCH = "7.3"

#: Riot's name for an item we file under another one. wr-meta, where our
#: catalogue comes from, uses PC League's names for these four.
ALIAS = {
    "at wit's end": "wits-end",
    "lord dominik's regards": "lord-dominiks-regard",
    "staff of flowing waters": "staff-of-flowing-water",
    "salvation": "redemption",
}

#: slug -> the name the shop shows from 7.3 on.
RENAME = {
    "redemption": "Salvation",
    "wits-end": "At Wit's End",
    "staff-of-flowing-water": "Staff of Flowing Waters",
    "lord-dominiks-regard": "Lord Dominik's Regards",
}

#: Off the Rift in 7.3. The records stay, marked, because ladder builds
#: collected in August still reference them and a card that silently drops an
#: item misstates what those fifty players built.
REMOVED = {
    "magnetic-blaster": "Removed in 7.3: too much of an all-purpose item, its effects "
                        "split across Stormrazor, Rapid Firecannon and Statikk Shiv.",
    "soul-transfer": "Removed in 7.3: never found its intended audience.",
    "searing-crown": "Removed in 7.3: the new jungle system has no need for a "
                     "jungle-specific Sunfire Aegis.",
}

#: Notes label -> our stat key. Percent-ness comes from the value itself.
STAT_LABELS = {
    "attack damage": "ad",
    "ability power": "ap",
    "attack speed": "attackSpeed",
    "critical rate": "crit",
    "critical strike chance": "crit",
    "armor penetration": "physicalPen",
    "magic penetration": "magicPen",
    "ability haste": "abilityHaste",
    "health": "hp",
    "max health": "hp",
    "maximum health": "hp",
    "base health": "hp",
    "armor": "armor",
    "magic resist": "mr",
    "magic resistance": "mr",
    "movement speed": "moveSpeed",
    "mana": "mana",
    "max mana": "mana",
    "maximum mana": "mana",
    "base mana regen": "manaRegen",
    "heal and shield power": "healShieldPower",
    "physical vamp": "physicalVamp",
    "omnivamp": "omnivamp",
    "lifesteal": "lifesteal",
    "tenacity": "tenacity",
    "price": "cost",
    "total price": "cost",
}

#: Lines that are real changes but not ours to hold. We carry completed items
#: only, so a recipe is a fact about components we do not model.
SKIP_LABELS = {"build path"}

#: Items whose Movement Speed lives in a named passive rather than the stat
#: block ("Cloud Stride: +5% Move Speed"), so the notes' stat line must be
#: applied to the text instead. Checked, not assumed: the script fails if the
#: old value is not in the passive.
MS_IN_PASSIVE = {"kraken-slayer", "phantom-dancer", "dead-mans-plate", "trinity-force",
                 "guinsoos-rageblade"}

#: Ability haste that only applies to one kind of ability. The site models
#: these separately from flat haste, because 20 ultimate haste is not 20 haste.
SCOPED = {
    "zekes-convergence": {"ultimateAbilityHaste": 10},
}


#: The full passive list after 7.3, for every item whose text changed. Whole
#: lists rather than substring edits: most of these are rewrites, and a list
#: says plainly which passives an item still has. Text follows the house style
#: (name, colon, the effect, with [stat] markers where a stat is named).
#:
#: Where a passive is folded into another and the notes do not say so in words,
#: the judgement is in a comment beside it.
PASSIVES = {
    "bloodthirster": [
        "Ichorshield: Overhealing from your Lifesteal [lifesteal] becomes a shield, up to 165-345 "
        "(based on level).",
    ],
    # Mana Siphon is gone: the new Spellblade restores the mana itself, and the
    # notes describe the item as streamlined to one effect.
    "essence-reaver": [
        "Spellblade: After casting an ability, your next attack within 10 seconds deals bonus "
        "physical damage equal to 135% base [ad] + 0-80 (based on [crit] Critical Rate) and "
        "restores Mana [mana] equal to 50% of the damage dealt. (1.5s Cooldown)",
    ],
    "the-collector": [
        "Killer: [physicalPen] +10 Armor Penetration.",
        "Death and Taxes: Damaging an enemy champion and leaving them below 5% of their max Health "
        "[hp] executes them, permanently raising the execute threshold by 0.1% of max Health and "
        "granting 25 bonus gold.",
    ],
    "kraken-slayer": [
        "Cloud Stride: [moveSpeed] +4% Move Speed.",
        "Bring It Down: Every third attack deals 150-210 bonus physical damage (120-168 for ranged "
        "champions), increased by 0.75% per 1% Health [hp] the target is missing, up to 75%.",
    ],
    "blade-of-the-ruined-king": [
        "Ruined Strike: Attacks deal bonus physical damage on hit equal to 7% of the target's "
        "current Health [hp] (8.5% for melee), minimum 15 and at most 100 against monsters.",
        "Drain: Hitting the same enemy champion 3 times with attacks or abilities slows them by 30% "
        "for 1.5 seconds. (30s Cooldown)",
    ],
    # Chaos goes with the adaptive stat: the item now carries flat AD and AP.
    "guinsoos-rageblade": [
        "Wrath: Attacks deal 30 bonus magic damage on hit.",
        "Seething Strike: Attacks grant 8% Attack Speed, stacking up to 4 times. At max stacks, "
        "every 3rd attack triggers an additional on-hit effect.",
    ],
    "wits-end": [
        "At Wit's End: Basic attacks deal 40 bonus magic damage on hit.",
    ],
    "terminus": [
        "Shadow: Attacks deal 30 bonus magic damage on hit.",
        "Juxtaposition: Alternate between Light and Dark on hit. Light grants 5-8 Armor [armor] and "
        "Magic Resist [mr]; Dark grants [physicalPen] 10% Armor Penetration and [magicPen] 10% "
        "Magic Penetration. Each stacks up to 3 times.",
    ],
    "phantom-dancer": [
        "Swift-Footed: [moveSpeed] +7% Movement Speed.",
        "Spectral Waltz: Landing an attack on a champion grants 6% Attack Speed and 1% Movement "
        "Speed [moveSpeed] for 6 seconds, stacking up to 5 times.",
    ],
    "runaans-hurricane": [
        "Wind's Fury: Attacks fire mini bolts at 2 nearby targets on hit, each dealing 55% physical "
        "damage [ad]. The bolts can Critically Strike and apply on-hit effects.",
    ],
    "mortal-reminder": [
        "Sepsis: Physical damage dealt to enemy champions applies 50% Grievous Wounds for 3 seconds. "
        "Grievous Wounds reduces the effectiveness of Healing and Regeneration effects.",
    ],
    "infinity-edge": [
        "Infinity: Critical Strikes deal 230% damage instead of 200%.",
    ],
    "manamune": [
        "Awe: Grants Attack Damage [ad] equal to 2% of max Mana [mana] and refunds 15% of all Mana "
        "spent.",
        "Mana Charge: Attacks and Mana expenditure grant 14 max Mana [mana], up to 700, at which "
        "point Manamune transforms into Muramana. Triggers up to 3 times every 10 seconds. You may "
        "only carry one Tear of the Goddess item at a time.",
    ],
    "muramana": [
        "Awe: Grants Attack Damage [ad] equal to 2% of max Mana [mana] and refunds 15% of all Mana "
        "spent.",
        "Shock: Attacks deal bonus physical damage equal to 1.5% of max Mana [mana]; abilities deal "
        "bonus physical damage equal to 3.5% of max Mana for melee and 3% for ranged.",
    ],
    "seryldas-grudge": [
        "Icy: Damaging active abilities and empowered attacks slow enemies below 60% current Health "
        "[hp] by 30% Movement Speed [moveSpeed] for 1 second.",
    ],
    "ardent-censer": [
        "Censer: Healing or shielding an allied champion other than yourself empowers you both for "
        "6 seconds, granting 30% bonus Attack Speed and 25 bonus magic damage on attacks.",
    ],
    "staff-of-flowing-water": [
        "Rapids: Healing or shielding an allied champion other than yourself empowers you both for "
        "6 seconds, granting 40 Ability Power [ap] and 15 Ability Haste [abilityHaste].",
    ],
    "imperial-mandate": [
        "Control: Crowd control abilities gain 20 Ability Haste [abilityHaste].",
        "Command: Crowd controlling an enemy champion marks them for 4 seconds, and they take 7% "
        "increased damage while marked.",
    ],
    "zekes-convergence": [
        "Converge: Gain 10 ultimate Ability Haste [abilityHaste].",
        "Frostfire Tempest: Casting your ultimate deals 150 magic damage and slows nearby enemies "
        "by 30% over 5 seconds. With no enemy champion in range, the effect waits up to 5 seconds "
        "for one.",
    ],
    "yordle-trap": [
        "Catcher: Slowing or immobilizing an enemy champion empowers you for 8 seconds (4 for "
        "ranged), granting 20 Movement Speed [moveSpeed]. While empowered, you and nearby allies "
        "gain 30% bonus Attack Speed (20% for ranged). A kill by you or an empowered ally grants "
        "you 20 gold.",
    ],
    "mantle-of-the-twelfth-hour": [
        "Lifeline: Dropping below 30% max Health [hp] grants 200-300 bonus Health for 5 seconds and "
        "heals you over those 5 seconds for 200-400 + 120% bonus Armor [armor] + 120% bonus Magic "
        "Resist [mr] + 15% bonus Health. During it, gain 10% size, 10% Movement Speed [moveSpeed] "
        "and 20% Tenacity.",
    ],
    "frozen-heart": [
        "Winter's Caress: All enemy champions within 650 units lose 25% Attack Speed.",
    ],
    "abyssal-mask": [
        "Unmake: All enemy champions within 6.5 meters take 12% increased magic damage.",
    ],
    "deaths-dance": [
        "Defy: If a champion you damaged within the last 3 seconds dies, the stored Cauterize damage "
        "is cleansed and you heal over 2 seconds for 90% bonus Attack Damage [ad].",
        "Cauterize: Store 30% of physical and magic damage taken (12% for ranged champions) and take "
        "it as true damage over 3 seconds instead.",
    ],
    "winters-approach": [
        "Awe: Grants bonus Health [hp] equal to 15% of max Mana [mana] and refunds 15% of all Mana "
        "spent.",
        "Mana Charge: Attacks, Mana expenditure and damage taken from champions, structures and epic "
        "monsters grant 14 max Mana [mana], up to 700, at which point Winter's Approach transforms "
        "into Fimbulwinter. Triggers up to 3 times every 10 seconds. You may only carry one Tear of "
        "the Goddess item at a time.",
    ],
    "fimbulwinter": [
        "Awe: Grants bonus Health [hp] equal to 15% of max Mana [mana] and refunds 15% of all Mana "
        "spent.",
        "Frozen Colossus: Impairing an enemy champion's movement grants a shield for 3 seconds that "
        "absorbs 120 + 4.5% max Mana [mana], increased by 80% with more than one enemy champion "
        "nearby. (8s Cooldown) Ranged champions get 50% of the shield.",
    ],
    "amaranths-twinguard": [
        "Endurance: Gain 1 Endurance stack each second while in combat with enemy champions, up to "
        "5. At max stacks, gain 20% size, 20% Tenacity, 30% bonus Armor [armor] and 30% bonus Magic "
        "Resist [mr] until you leave combat.",
    ],
    "force-of-nature": [
        "Absorb: Taking magic damage from enemy champions grants 1 Steadfast stack for 7 seconds, up "
        "to 4; dealing damage to enemy champions refreshes it. At max stacks, gain 6% Movement Speed "
        "[moveSpeed] and 70 bonus Magic Resist [mr].",
    ],
    "youmuus-ghostblade": [
        "Slice: [physicalPen] +15 Armor Penetration.",
        "Momentum: 3 seconds after combat with enemy champions ends, gain 30 bonus Movement Speed "
        "[moveSpeed] (20 for ranged champions).",
    ],
    "trinity-force": [
        "Spellblade: Using an ability causes the next attack used within 10 seconds to deal bonus "
        "physical damage equal to 200% base AD [ad] (1.5s Cooldown). Damage is reduced vs structures.",
        "Valor: Attacks grant 20 Move Speed for 2 seconds. Bonuses do not stack. Ranged champions "
        "gain halved values.",
    ],
    "dusk-and-dawn": [
        "Spellblade: After using an ability, your next attack deals (75% base [ad] + 10% [ap]) bonus "
        "magic damage and heals you for 10% [ap] + 3% bonus Health [hp]. After a brief delay, apply "
        "on-hits to the target 1 additional time. (1.5s Cooldown) Deals reduced damage to structures.",
    ],
    "nashors-tooth": [
        "Gnaw: Attacks deal 15 + 20% bonus [ap] magic damage on hit.",
    ],
    "ludens-echo": [
        "Echo: Your next damaging ability or empowered attack deals 75 + 8% [ap] magic damage to the "
        "target and up to 5 nearby enemies. For each target fewer than that, the primary target takes "
        "an additional 20 + 1.2% [ap] magic damage. (9s Cooldown)",
    ],
    "sunfire-aegis": [
        "Immolate: On entering combat, deal 20 + 1.5% bonus Health [hp] magic damage to nearby "
        "enemies every second. Immolate deals 175-250% damage to minions and 130% to monsters.",
    ],
    "infinity-orb": [
        "Inevitable Demise: Abilities and empowered attacks Critically Strike for 20% bonus damage "
        "against enemies below 40% Health [hp].",
    ],
    "steraks-gage": [
        "Heavy Handed: +50% base Attack Damage as bonus Attack Damage [ad].",
        "Lifeline: Damage that puts you under 35% [hp] Health grants a shield equal to 75% of your "
        "bonus Health [hp] that decays over 3 seconds. (75s Cooldown)",
        "Sterak's Fury: Triggering Lifeline increases size, empowers you and removes all crowd "
        "control effects on you (except Airborne) for 4 seconds.",
    ],
    "harmonic-echo": [
        "Harmonic Echo: Healing or shielding an allied champion links the effect to the nearest "
        "allied champion with the lowest percentage Health, excluding yourself, granting them 30% of "
        "that heal or 35% of that shield. With no other ally in range, the original target receives "
        "it instead.",
    ],
}


#: The ten items 7.3 adds. Stats are cross-checked against the parsed notes
#: below, so a mistyped number here fails the run rather than shipping.
#:
#: Icons come from PC League's art (Riot has not published Wild Rift icons for
#: these yet), downloaded by scripts/fetch_pc_item_icons.py.
NEW_ITEMS = [
    {
        "slug": "hexoptics-c44", "name": "Hexoptics C44", "category": "Physical",
        "categories": ["Physical"], "cost": 2900,
        "stats": {"ad": 55, "crit": "25%"},
        "passives": [
            "Magnification: Attacks deal 0-10% bonus damage based on how far the enemy is, reaching "
            "the maximum at 550 units.",
            "Arcane Aim: When a champion you damaged within the last 3 seconds dies, gain 100 bonus "
            "Attack Range for 8 seconds.",
        ],
        "tags": [],
    },
    {
        # Critical Rate starts at 0 and is earned by attacking, so it is a
        # passive here rather than a "+0%" stat line nobody can read.
        "slug": "yun-tal-wildarrows", "name": "Yun Tal Wildarrows", "category": "Physical",
        "categories": ["Physical"], "cost": 3100,
        "stats": {"ad": 50, "attackSpeed": "25%"},
        "passives": [
            "Practice Makes Perfect: Attacks permanently grant Critical Rate [crit], 0.4% per attack "
            "for melee and 0.2% for ranged, up to 25%.",
            "Flurry: Attacking an enemy champion grants 25% Attack Speed for 6 seconds. (20s "
            "Cooldown, reduced by 1s per attack and 2s on a Critical Strike)",
        ],
        "tags": [],
    },
    {
        "slug": "stormrazor", "name": "Stormrazor", "category": "Physical",
        "categories": ["Physical"], "cost": 3000,
        "stats": {"ad": 50, "crit": "25%", "attackSpeed": "20%"},
        "passives": [
            "Energized: Moving and attacking generate an Energized attack.",
            "Bolt: Your Energized attack deals 120 bonus magic damage and grants 45% Movement Speed "
            "[moveSpeed] for 1.5 seconds.",
        ],
        "tags": ["mobility"],
    },
    {
        "slug": "rapid-firecannon", "name": "Rapid Firecannon", "category": "Physical",
        "categories": ["Physical"], "cost": 2650,
        "stats": {"crit": "25%", "attackSpeed": "40%", "moveSpeed": "4%"},
        "passives": [
            "Energized: Moving and attacking generate an Energized attack.",
            "Sharpshooter: Your Energized attack deals 80 bonus magic damage and grants 35% bonus "
            "Attack Range, up to 150.",
        ],
        "tags": ["mobility"],
    },
    {
        "slug": "fiendhunter-bolts", "name": "Fiendhunter Bolts", "category": "Physical",
        "categories": ["Physical"], "cost": 2650,
        "stats": {"crit": "25%", "attackSpeed": "45%", "moveSpeed": "4%"},
        "scopedStats": {"ultimateAbilityHaste": 20},
        "passives": [
            "Night Vigil: Gain 20 ultimate Ability Haste [abilityHaste].",
            "Opening Barrage: After casting your ultimate, your next 3 attacks within 8 seconds gain "
            "50% Attack Speed and are guaranteed to Critically Strike for 80% of your normal "
            "Critical Strike damage. An attack that would already Critically Strike deals 15% bonus "
            "true damage instead. (45s Cooldown)",
        ],
        "tags": ["mobility"],
    },
    {
        "slug": "immortal-shieldbow", "name": "Immortal Shieldbow", "category": "Physical",
        "categories": ["Physical", "Defense"], "cost": 3000,
        "stats": {"ad": 55, "crit": "25%"},
        "passives": [
            "Lifeline: Taking damage that would put you below 35% Health [hp] grants a shield for 3 "
            "seconds (350-650 for melee, 300-550 for ranged, based on level). (70s Cooldown)",
        ],
        "tags": ["shield"],
    },
    {
        "slug": "statikk-shiv", "name": "Statikk Shiv", "category": "Physical",
        "categories": ["Physical", "Magic"], "cost": 3000,
        "stats": {"ad": 40, "ap": 40, "attackSpeed": "30%", "moveSpeed": "4%"},
        "passives": [
            "Energized: Moving and attacking generate an Energized attack.",
            "Electrospark: Your Energized attack fires chain lightning that bounces to 3/4/5/6 "
            "targets (at levels 1/5/9/13), dealing 60 magic damage, or 90 against minions and "
            "monsters. On-hit effects apply to the bounce targets.",
            "ElectroShock: Attacks grant 5 bonus Energized stacks.",
        ],
        "tags": ["onHit"],
    },
    {
        "slug": "whispering-circlet", "name": "Whispering Circlet", "category": "Support",
        "categories": ["Support"], "cost": 2400,
        "stats": {"hp": 200, "mana": 500, "manaRegen": "50%", "healShieldPower": "8%"},
        "passives": [
            "Harmony: Gain bonus Heal and Shield Power [healShieldPower] equal to 0.5% of max Mana "
            "[mana] and refund 25% of Mana spent.",
            "Mana Charge: Mana expenditure grants 14 max Mana [mana], up to 700, at which point "
            "Whispering Circlet transforms into Diadem of Songs. Triggers up to 2 times every 10 "
            "seconds.",
        ],
        "tags": ["mana"],
        "upgradesTo": "diadem-of-songs",
    },
    {
        "slug": "diadem-of-songs", "name": "Diadem of Songs", "category": "Support",
        "categories": ["Support"], "cost": 2400,
        "stats": {"hp": 200, "mana": 1200, "manaRegen": "50%", "healShieldPower": "8%"},
        "passives": [
            "Harmony: Gain bonus Heal and Shield Power [healShieldPower] equal to 0.5% of max Mana "
            "[mana] and refund 25% of Mana spent.",
            "Diadem: While you, or an ally you healed or shielded in the last 3 seconds, are in "
            "combat, heal the nearby allied champion with the lowest Health within 800 units each "
            "second for 0.8% of your max Mana [mana].",
        ],
        "tags": ["mana", "sustain"],
    },
    {
        "slug": "echoes-of-helia", "name": "Echoes of Helia", "category": "Support",
        "categories": ["Support"], "cost": 2400,
        "stats": {"hp": 200, "ap": 40, "abilityHaste": 20, "manaRegen": "50%"},
        "passives": [
            "Soul Siphon: 30% of pre-mitigation damage dealt to enemy champions is stored as Soul "
            "Fragments, up to 80-250 based on level. Healing or shielding an allied champion other "
            "than yourself consumes every fragment to heal them for the same amount.",
        ],
        "tags": ["sustain"],
    },
]


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").lower().replace("’", "'")
    return re.sub(r"\s+", " ", text).strip()


def key_of(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", norm(text))


def number(text: str) -> float | None:
    m = re.match(r"^([0-9]+(?:\.[0-9]+)?)", text.replace(",", "").strip())
    return float(m.group(1)) if m else None


def item_blocks(notes: dict) -> list[tuple[dict, list[dict]]]:
    """Each item's own block plus its passive blocks, in page order."""
    blade = next(b for b in notes["blades"] if b.get("id") == "ITEM ADJUSTMENTS")
    blocks = blade["blocks"]
    out = []
    for i, block in enumerate(blocks):
        if block["level"] != 4:
            continue
        kids = []
        for child in blocks[i + 1:]:
            if child["level"] <= 4:
                break
            kids.append(child)
        out.append((block, kids))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    notes = json.loads(NOTES.read_text(encoding="utf-8"))
    items = json.loads(ITEMS.read_text(encoding="utf-8"))
    by_slug = {i["slug"]: i for i in items}
    by_name = {key_of(i["name"]): i for i in items}

    applied: list[str] = []
    problems: list[str] = []
    unmapped: list[str] = []

    def resolve(title: str) -> dict | None:
        slug = ALIAS.get(norm(title))
        if slug:
            return by_slug[slug]
        return by_name.get(key_of(title))

    for block, _kids in item_blocks(notes):
        item = resolve(block["title"])
        if item is None:
            continue
        for line in block["lines"]:
            m = re.match(r"^(?:\[(New|Removed|Adjusted)\]\s*)?([A-Za-z'’ ]+?)\s*:\s*(.+)$", line)
            if not m:
                unmapped.append(f'{block["title"]}: {line}')
                continue
            tag, label, rest = m.group(1), norm(m.group(2)), m.group(3).strip()
            if label in SKIP_LABELS:
                continue
            stat = STAT_LABELS.get(label)
            if not stat:
                unmapped.append(f'{block["title"]}: {line}')
                continue
            percent = "%" in rest
            if "→" in rest:
                old_text, new_text = [t.strip() for t in rest.split("→")[:2]]
            elif tag == "New":
                old_text, new_text = None, rest
            elif tag == "Removed":
                old_text, new_text = rest, None
            else:
                # A restated value on an item we already carry (the notes print
                # the whole block for a reworked item).
                old_text, new_text = None, rest
            old = number(old_text) if old_text else None
            new = number(new_text) if new_text else None

            if stat == "cost":
                if old is not None and item["cost"] != old:
                    problems.append(f'{item["name"]} cost: notes say {old:g}, we hold {item["cost"]}')
                if new is not None:
                    applied.append(f'{item["name"]} cost {item["cost"]} -> {new:g}')
                    item["cost"] = int(new)
                continue

            held_in_stats = stat in item["stats"]
            if stat == "moveSpeed" and not held_in_stats and item["slug"] in PASSIVES:
                # The rewrite below carries the new value; here we only check
                # that we were holding the old one.
                if old is not None and not any(f"{old:g}%" in p for p in item["passives"]):
                    problems.append(f'{item["name"]}: no passive holds {old:g}% move speed ({line})')
                continue

            if stat == "moveSpeed" and not held_in_stats and item["slug"] in MS_IN_PASSIVE:
                # Held in a named passive on these items ("Cloud Stride: +5%
                # Move Speed"), so the stat block is empty and the edit belongs
                # in the text. A move speed that goes to nothing takes its
                # passive with it rather than leaving "+0% Move Speed".
                hit = False
                for n, text in enumerate(item["passives"]):
                    if old is None or f"{old:g}%" not in text or "Move" not in text:
                        continue
                    if not new:
                        item["passives"].pop(n)
                        applied.append(f'{item["name"]} passive "{text.split(":")[0]}" removed with its move speed')
                    else:
                        item["passives"][n] = text.replace(f"{old:g}%", f"{new:g}%", 1)
                        applied.append(f'{item["name"]} passive move speed {old:g}% -> {new:g}%')
                    hit = True
                    break
                if not hit:
                    problems.append(f'{item["name"]}: no passive holds {old:g}% move speed ({line})')
                continue

            have = item["stats"].get(stat)
            if old is not None and (have is None or abs(have["value"] - old) > 0.001):
                held = "nothing" if have is None else f'{have["value"]:g}'
                problems.append(f'{item["name"]} {stat}: notes say {old:g}, we hold {held}')
            if new is None or new == 0:
                # "Health: 150 → 0" means the item no longer grants it, not
                # that it grants zero of it.
                if item["stats"].pop(stat, None) is not None:
                    applied.append(f'{item["name"]} {stat} removed')
                continue
            item["stats"][stat] = {"value": new, "percent": percent}
            applied.append(f'{item["name"]} {stat} = {new:g}{"%" if percent else ""}')

    parsed_stats = {}
    for block, _kids in item_blocks(notes):
        rows = {}
        for line in block["lines"]:
            m = re.match(r"^(?:\[(?:New|Removed|Adjusted)\]\s*)?([A-Za-z'’ ]+?)\s*:\s*([^→]+)$", line)
            if not m:
                continue
            stat = STAT_LABELS.get(norm(m.group(1)))
            if stat and stat != "cost":
                rows[stat] = (number(m.group(2)), "%" in m.group(2))
        parsed_stats[key_of(block["title"])] = rows

    next_id = max(i["id"] for i in items) + 1
    for spec in NEW_ITEMS:
        if spec["slug"] in by_slug:
            problems.append(f'{spec["slug"]}: already in the catalogue')
            continue
        stats = {}
        for stat, raw in spec["stats"].items():
            percent = isinstance(raw, str) and raw.endswith("%")
            stats[stat] = {"value": float(str(raw).rstrip("%")), "percent": percent}
        # The notes are the check on this table: every stat they print for the
        # item must be the value written here.
        for stat, (value, percent) in parsed_stats.get(key_of(spec["name"]), {}).items():
            mine = stats.get(stat)
            if value == 0 and mine is None:
                continue          # a stat that starts at zero and is earned
            if mine is None or abs(mine["value"] - value) > 0.001 or mine["percent"] != percent:
                held = "nothing" if mine is None else f'{mine["value"]:g}'
                problems.append(f'{spec["name"]} {stat}: notes say {value:g}, this table says {held}')
        record = {
            "id": next_id, "slug": spec["slug"], "name": spec["name"],
            "category": spec["category"], "categories": spec["categories"],
            "cost": spec["cost"], "stats": stats, "passives": list(spec["passives"]),
            "tags": list(spec["tags"]), "icon": f'/items/{spec["slug"]}.png',
            "addedIn": PATCH,
        }
        if "scopedStats" in spec:
            record["scopedStats"] = {k: {"value": float(v), "percent": False}
                                     for k, v in spec["scopedStats"].items()}
        if "upgradesTo" in spec:
            record["upgradesTo"] = spec["upgradesTo"]
        items.append(record)
        by_slug[spec["slug"]] = record
        next_id += 1
        applied.append(f'{spec["name"]}: added ({spec["cost"]} gold)')

    for slug, passives in PASSIVES.items():
        item = by_slug.get(slug)
        if item is None:
            problems.append(f"{slug}: no such item to rewrite")
            continue
        if item["passives"] != passives:
            applied.append(f'{item["name"]}: passives rewritten '
                           f'({len(item["passives"])} -> {len(passives)})')
            item["passives"] = list(passives)

    for slug, scoped in SCOPED.items():
        item = by_slug[slug]
        item.setdefault("scopedStats", {}).update(
            {k: {"value": float(v), "percent": False} for k, v in scoped.items()})
        applied.append(f'{item["name"]}: {", ".join(f"{k} {v}" for k, v in scoped.items())}')

    for slug, why in REMOVED.items():
        by_slug[slug]["removedIn"] = PATCH
        by_slug[slug]["removedWhy"] = why
        applied.append(f'{by_slug[slug]["name"]}: marked removed in {PATCH}')

    for slug, name in RENAME.items():
        was = by_slug[slug]["name"]
        by_slug[slug]["name"] = name
        applied.append(f"{was} renamed to {name}")

    print(f"APPLIED ({len(applied)})")
    for line in applied:
        print(f"  {line}")
    if unmapped:
        print(f"\nNOT MAPPED ({len(unmapped)}) -- handled elsewhere or needs a hand:")
        for line in unmapped:
            print(f"  {line[:150]}")
    if problems:
        print(f"\nDISAGREEMENTS ({len(problems)}):")
        for line in problems:
            print(f"  {line}")

    if args.write:
        # indent=2 is how the catalogue is stored; anything else rewrites all
        # 3,700 lines and buries the patch in a whitespace diff.
        ITEMS.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\nwrote {ITEMS.relative_to(ROOT)}")
    else:
        print("\ndry run: pass --write to save")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
