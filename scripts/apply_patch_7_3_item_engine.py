"""Teach the fight engine what 7.3's items actually do.

data/items.json holds the stats and the prose; this holds the numbers the two
engines simulate with. Three files:

  data/item_engine_overrides.json  effects, merged OVER the extracted ones, so
                                   a stale extraction is neutralised by writing
                                   the key back as 0 (the file's own idiom).
  data/item_stat_rules.json        stats a passive grants but the stat block
                                   does not print (Infinity Edge's crit damage).
  data/item_rules.json             which items cannot be built together.

The extractor (scripts/extract_item_effects.py) would normally re-read the new
passive text, but it needs DEEPSEEK_API_KEY, which is not set here. These are
written by hand from the patch notes instead, which is what the overrides file
is for, and a later extraction run can still replace the base values under it.

WHAT IS NOT MODELLED (stated, not hidden)

  Hexoptics C44's distance scaling and bonus Attack Range, Rapid Firecannon's
  range, Bloodthirster's overheal shield, Statikk Shiv's chain bounces beyond
  the first target, Sunfire's Health scaling on Immolate, Force of Nature's
  Movement Speed stack timing. Every one is either a positional effect the
  engine has no room for or a key the vocabulary does not carry.

Run:
    python -m scripts.apply_patch_7_3_item_engine
    python -m scripts.apply_patch_7_3_item_engine --write
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

PATCH = "7.3"

#: slug -> effects after 7.3. A 0 means "the extractor found this before and
#: the patch took it away"; the engines read the merged value, so 0 is how a
#: key is deleted without touching the extraction file.
EFFECTS = {
    # -- marksman items ----------------------------------------------------
    "bloodthirster": {
        "physVampPct": 0, "physVampPctOnCrit": 0,
        "_why": "Physical Vamp became the new Lifesteal stat (15%), which the "
                "engines read off the item's stat line. Ichorshield's overheal "
                "shield is not modelled.",
    },
    "blade-of-the-ruined-king": {
        "omnivampPct": 0, "burstProcFlat": 0,
        "_why": "Omnivamp became Lifesteal 12% on the stat line. Drain no longer "
                "deals damage or steals Move Speed. Its 30% slow arms after three "
                "hits, lasts 1.5s and has a 30s cooldown, so the window scheduler "
                "can activate it only once in an ordinary teamfight.",
        "targetSlowPct": 30, "targetSlowDurationSec": 1.5,
        "targetSlowCdSec": 30, "targetSlowArmHits": 3,
    },
    "guinsoos-rageblade": {
        "adaptiveAdFlat": 0, "adaptiveApFlat": 0, "msPct": 0,
        "onHitFlatMagic": 30, "disablesCrit": 0, "asPctPassive": 32,
        "_why": "Chaos (adaptive 25 AD / 50 AP) became printed stats, Surge's "
                "Move Speed is gone, Wrath is a flat 30 magic on hit and no "
                "longer blocks crit, and Seething Strike is unchanged at 8% x 4.",
    },
    "wits-end": {
        "onHitFlatMagic": 40, "healOnHitFlat": 0, "tenacityPct": 0,
        "_why": "On-hit is a flat 40 magic now (was 10-55 by level) and the "
                "below-half-health healing is gone. The new 20% Tenacity is a "
                "printed stat, and both the stat and this key feed the same "
                "multiplicative channel, so carrying it here too would charge "
                "the item 36% tenacity.",
    },
    "terminus": {
        "onHitFlatMagic": 30, "pctPen": 30, "mrShredPct": 30,
        "_why": "Shadow 35 -> 30 magic on hit. Juxtaposition's dark side is 10% "
                "of each penetration per stack, three stacks, and the old 40% "
                "cap is gone from the text.",
    },
    "phantom-dancer": {
        "asPctPassive": 30, "msPct": 7,
        "_why": "Spectral Waltz is 6% Attack Speed x 5 stacks (was a flat 25%), "
                "and Swift-Footed is 7% Move Speed (was 5%).",
    },
    "runaans-hurricane": {
        "onHitFlatPhys": 0,
        "_why": "Wind Blade (15 physical on hit) was removed; the bolts remain.",
    },
    "mortal-reminder": {
        "pctPen": 0, "pctPenOnCrit": 0,
        "_why": "Last Whisper is integrated into the stat block as 30% Armor "
                "Penetration, so the effect keys would double it.",
    },
    "seryldas-grudge": {
        "pctPen": 0, "burstProcFlat": 0, "grievousWoundsPct": 0,
        "targetSlowPct": 30, "targetSlowUptime": 40,
        "_why": "Penetration is read from the 35% stat line. Icy slows targets "
                "below 60% Health by 30%; represented at 40% fight uptime.",
    },
    "goredrinker": {
        "omnivampPct": 0, "burstProcTotalAdRatio": 175,
        "burstProcType": "physical", "burstProcCdSec": 12,
        "_why": "Thirsting Slash damage is modeled against one champion as 175% "
                "total AD every 12 seconds. Its 20% AD + 10% missing-Health heal "
                "per champion hit is not modeled.",
    },
    "infinity-edge": {
        "critMult": 2.3, "critDamagePerExcessCrit": 0,
        "_why": "Infinity raises critical strike damage to 230% (base is 200% "
                "from 7.3). Limit Break, the excess-crit conversion, is gone.",
    },
    "kraken-slayer": {
        "everyNthFlat": {"lvlRange": [150, 210]},
        "everyNthRangedFlat": {"lvlRange": [120, 168]},
        "msPct": 4,
        "_why": "Bring It Down's third-attack damage is up, and the missing "
                "health scaling is 0.75% per 1% up to 75% (was 1% up to 70%), "
                "which the engine averages the same way it did before.",
    },
    "the-collector": {
        "executePct": 5,
        "_why": "The execute threshold is a flat 5% now, not 4% + 2% of crit.",
    },
    "essence-reaver": {
        "spellbladeBaseAdPct": 135, "burstProcFlat": 0, "msFlat": 0,
        "_why": "Spellblade is one hit of 135% base AD (was a 70-damage charge "
                "system with Move Speed). The 0-80 that scales with Critical "
                "Rate is not modelled: the engine has no crit-scaled spellblade "
                "key, so this is the floor of the effect.",
    },
    "manamune": {
        "adFromManaPct": 2,
        "_why": "AWE converts 2% of max Mana (was 1.5%).",
    },
    "nashors-tooth": {
        "adaptiveAdFlat": 0, "adaptiveApFlat": 0,
        "adaptiveOnHitFlat": 0, "adaptiveOnHitBonusAdPct": 0, "adaptiveOnHitApPct": 0,
        "onHitFlatMagic": 15, "onHitApRatio": 20,
        "_why": "Magic Fang (adaptive) was removed and the item is pure Ability "
                "Power again, so Gnaw is a plain magic on-hit of 15 + 20% bonus "
                "AP rather than an adaptive one.",
    },
    "ludens-echo": {
        "burstProcFlat": 75, "burstProcApPct": 8,
        "_why": "Echo is 75 + 8% AP (was 140 + 15%). The single-target top-up "
                "for each target it misses is not modelled: the engine prices "
                "the primary target only.",
    },
    "youmuus-ghostblade": {
        "msFlat": 30, "asPctPassive": 0,
        "_why": "Momentum is a flat out-of-combat 30 Move Speed now, and "
                "Spectral Haste (25% Attack Speed) was removed.",
    },
    "trinity-force": {
        "msPct": 0,
        "_why": "Fervor's 5% Move Speed was removed.",
    },
    # -- defence and support ----------------------------------------------
    "force-of-nature": {
        "msPct": 6, "drMagicPct": 0, "mrFlat": 70,
        "_why": "The percentage magic damage reduction is gone; at four stacks "
                "the item grants 70 Magic Resist and 6% Move Speed instead. "
                "Stack uptime is not modelled, so this is the full value.",
    },
    "sunfire-aegis": {
        "dotDps": 20, "damageAmpPct": 0,
        "_why": "Immolate is a flat 20 per second plus 1.5% bonus Health; the "
                "Health half has no key, and Flametouch's stacking amp is gone.",
    },
    "frozen-heart": {
        "targetAsSlowPct": 25,
        "_why": "Winter's Caress is a flat 25% Attack Speed aura on every nearby "
                "enemy, not a four-stack chill.",
    },
    "abyssal-mask": {
        "mrShredFlat": 0, "damageAmpPct": 12,
        "_why": "Unmake no longer shreds Magic Resist; nearby enemies take 12% "
                "more magic damage. Charged as the carrier's own amp, which is "
                "the half of it the engine can see.",
    },
    "amaranths-twinguard": {
        "armorPctPassive": 30, "mrPctPassive": 30,
        "_why": "Endurance now grants 30% BONUS Armor and Magic Resist at max "
                "stacks. It was modelled at 20.6% of total resistances; the new "
                "text is explicit about both the number and the base.",
    },
    "winters-approach": {
        "hpFromManaPct": 15,
        "_why": "AWE converts 15% of max Mana into Health (was 8%).",
    },
    "fimbulwinter": {
        "hpFromManaPct": 15, "shieldFlat": 120,
        "_why": "AWE is 15% of max Mana; Frozen Colossus shields a flat 120 plus "
                "4.5% max Mana (the Mana half has no key).",
    },
    "mantle-of-the-twelfth-hour": {
        "msFlat": 0, "healFlat": {"lvlRange": [200, 400]}, "hpFlatPassive": 0,
        "_why": "Lifeline is a heal now (200-400 plus resistance scaling that "
                "has no key) with 200-300 temporary Health, at 30% rather than "
                "35% Health.",
    },
    "deaths-dance": {
        "drPct": 12,
        "_why": "Unchanged for ranged (12%); melee storage went 27% -> 30%, and "
                "the engine's single figure is the ranged one.",
    },
    "ardent-censer": {
        "allyAsPct": 30, "allyOnHitFlatMagic": 25,
        "_why": "Censer is a flat 30% Attack Speed and 25 magic on hit for both "
                "of you, no longer scaling with the ally's level.",
    },
    "staff-of-flowing-water": {
        "allyApFlat": 40, "hasteFlatPassive": 15,
        "_why": "Rapids grants a flat 40 Ability Power and 15 Ability Haste to "
                "both of you (was 30-50 by level).",
    },
    "imperial-mandate": {
        "burstProcFlat": 0, "allyProcFlat": 0, "allyMsPct": 0, "msPct": 0,
        "damageAmpPct": 7,
        "_why": "Coordinated Fire is gone. Command marks a crowd-controlled "
                "enemy so they take 7% more damage; the mark helps the whole "
                "team, and the engine can only price your own share of it.",
    },
    "zekes-convergence": {
        "burstProcFlat": 150, "burstProcCdSec": 60,
        "_why": "Frostfire Tempest is 150 magic damage on your ultimate (was a "
                "320-600 blizzard), so it recurs on the ultimate's cooldown.",
    },
    "yordle-trap": {
        "mrShredFlat": 0, "msPct": 0, "allyAsPct": 20, "asPctPassive": 20,
        "_why": "Catcher no longer shreds resistances or grants gold on a kill "
                "it marked; it now hands you and nearby allies Attack Speed "
                "(30% melee, 20% ranged) after a slow or immobilise.",
    },
    "harmonic-echo": {
        "allyHealFlat": 0,
        "_why": "The item no longer heals by itself: it forwards 30% of a heal "
                "or 35% of a shield you cast to a second ally. That is a share "
                "of the caster's own healing, which the engine has no key for.",
    },
    # -- the ten new items -------------------------------------------------
    "hexoptics-c44": {
        "_why": "Magnification (0-10% by distance) and Arcane Aim (bonus Attack "
                "Range on a takedown) are positional; the engine has neither "
                "distance nor range, so the item is priced on its stats.",
    },
    "yun-tal-wildarrows": {
        "asPctPassive": 25, "critPctPassive": 25,
        "_why": "Flurry's 25% Attack Speed, which is up for most of a fight "
                "given the cooldown drops by 1s per attack, and Practice Makes "
                "Perfect's 25% Critical Rate. The shop prints that crit as 0% "
                "because it is earned by attacking (125 attacks for a ranged "
                "champion), so it cannot sit in the stat line without "
                "misstating the purchase -- but the engines score a completed "
                "level 15 build, where it is long since full. critPctPassive "
                "is the crit twin of asPctPassive, which exists for exactly "
                "this reason.",
    },
    "stormrazor": {
        "burstProcFlat": 120, "burstProcCdSec": 6, "msPct": 11,
        "_why": "Bolt is 120 magic on the Energized attack with 45% Move Speed "
                "for 1.5s. Energized recharges while moving and attacking, so "
                "it is charged every 6 seconds rather than once a fight. msPct "
                "is a PERMANENT bonus in the engine, so the burst is discounted "
                "to its uptime: 45% for 1.5s of every 6 is about 11%.",
    },
    "rapid-firecannon": {
        "burstProcFlat": 80, "burstProcCdSec": 6,
        "_why": "Sharpshooter is 80 magic on the Energized attack; its 35% bonus "
                "Attack Range has no key.",
    },
    "fiendhunter-bolts": {
        "_why": "Opening Barrage's three guaranteed crits after an ultimate are "
                "a window the engine cannot open: it has no ultimate timeline. "
                "Priced on its stats and the 20 ultimate Ability Haste.",
    },
    "immortal-shieldbow": {
        "shieldFlat": {"lvlRange": [300, 550]},
        "_why": "Lifeline's ranged shield, which is who buys it. Melee is "
                "350-650.",
    },
    "statikk-shiv": {
        "burstProcFlat": 60, "burstProcCdSec": 6,
        "aoeProcFlat": 60, "aoeProcCdSec": 6, "aoeProcTargets": 5,
        "_why": "Electrospark's first 60-damage hit is single-target; its five "
                "additional level-15 bounces are reported on the AoE axis. On-hit "
                "effects carried by those bounces are not modeled.",
    },
    "whispering-circlet": {
        "_why": "Harmony is Heal and Shield Power from max Mana, which the stat "
                "rules carry; there is no separate combat effect.",
    },
    "diadem-of-songs": {
        "allyHealFlat": 10,
        "_why": "Diadem heals the lowest-Health nearby ally for 0.8% of max Mana "
                "each second. At its ~1,200 Mana that is about 10 a second, so "
                "it is charged as a flat ally heal.",
    },
    "echoes-of-helia": {
        "allyHealFlat": {"lvlRange": [80, 250]},
        "_why": "Soul Siphon's fragments cap at 80-250 by level and are spent on "
                "the next heal or shield, so the cap is the per-use value.",
    },
}

#: Stats a passive grants that the shop does not print, for the site's stat
#: sheet. `always` is added to the sheet; `conditional` is shown as prose.
STAT_RULES = {
    "trinity-force": {
        "conditional": [
            {"label": "Valor",
             "detail": "Attacks grant 20 Move Speed for 2 seconds (halved for ranged champions)."},
        ],
    },
    "infinity-edge": {
        "always": [{"stat": "critDamage", "set": 230, "label": "Infinity"}],
    },
    "blade-of-the-ruined-king": {
        "conditional": [
            {"label": "Drain",
             "detail": "Three attacks or abilities on the same champion slow them by 30% for 1.5 seconds."},
        ],
    },
    "yun-tal-wildarrows": {
        "conditional": [
            {"label": "Practice Makes Perfect",
             "detail": "Attacks permanently grant Critical Rate, 0.2% per attack for ranged and "
                       "0.4% for melee, up to 25%."},
            {"label": "Flurry",
             "detail": "Attacking a champion grants 25% Attack Speed for 6 seconds."},
        ],
    },
    "rapid-firecannon": {
        "conditional": [
            {"label": "Sharpshooter",
             "detail": "The Energized attack deals 80 bonus magic damage and grants 35% bonus "
                       "Attack Range, up to 150."},
        ],
    },
    "hexoptics-c44": {
        "conditional": [
            {"label": "Magnification",
             "detail": "Attacks deal up to 10% bonus damage, reaching the maximum at 550 units away."},
            {"label": "Arcane Aim",
             "detail": "A takedown within 3 seconds of your damage grants 100 Attack Range for 8 seconds."},
        ],
    },
    "fiendhunter-bolts": {
        "conditional": [
            {"label": "Opening Barrage",
             "detail": "After your ultimate, your next 3 attacks crit for 80% of normal critical "
                       "damage, or deal 15% bonus true damage if they would already crit."},
        ],
    },
    "immortal-shieldbow": {
        "conditional": [
            {"label": "Lifeline",
             "detail": "Dropping below 35% Health shields you for 300-550 (350-650 melee) for 3 "
                       "seconds. (70s cooldown)"},
        ],
    },
    "stormrazor": {
        "conditional": [
            {"label": "Bolt",
             "detail": "The Energized attack deals 120 bonus magic damage and grants 45% Move "
                       "Speed for 1.5 seconds."},
        ],
    },
    "statikk-shiv": {
        "conditional": [
            {"label": "Electrospark",
             "detail": "The Energized attack chains to 3-6 targets for 60 magic damage each, 90 "
                       "against minions and monsters, and applies on-hit effects to them."},
        ],
    },
}

#: Items that cannot be built together, added to data/item_rules.json.
MUTEX_ADD = {
    "lifeline": ["immortal-shieldbow"],
}

#: Who may build an item at all, written into data/items.json.
#:
#: This used to be read out of the passive prose, and the only line carrying it
#: was wr-meta's mangled "This item cannot only be used by melee champions" on
#: Runaan's. 7.3 rewrote that passive from Riot's own text, which does not
#: mention the restriction at all, and with the sentence went the one thing
#: keeping Runaan's out of melee builds. A field says it once and cannot be
#: rewritten away.
RESTRICTIONS = {
    "runaans-hurricane": "ranged-only",
}


def load(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def save(name: str, payload: dict) -> None:
    # indent=2 is how these three are stored; anything else reformats every
    # line and hides the patch inside a whitespace diff.
    (DATA / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    items = {i["slug"]: i for i in load("items.json")}
    overrides = load("item_engine_overrides.json")
    stat_rules = load("item_stat_rules.json")
    rules = load("item_rules.json")

    missing = [slug for slug in EFFECTS if slug not in items]
    missing += [slug for slug in STAT_RULES if slug not in items]
    if missing:
        print("NOT IN THE CATALOGUE:", ", ".join(sorted(set(missing))))
        return 1

    for slug, fx in EFFECTS.items():
        before = {k: v for k, v in (overrides.get(slug) or {}).items() if not k.startswith("_")}
        entry = dict(overrides.get(slug) or {})
        entry.update(fx)
        entry.pop("_why_channel", None)      # superseded by this patch's note
        if slug == "nashors-tooth":
            entry.pop("_why_gnaw", None)     # superseded by pure-AP 7.3 Gnaw
        if slug == "force-of-nature":
            entry.pop("_why_dr", None)       # old 20% magic-DR version was removed
        overrides[slug] = entry
        after = {k: v for k, v in entry.items() if not k.startswith("_")}
        changed = {k: (before.get(k), v) for k, v in after.items() if before.get(k) != v}
        if changed:
            print(f"{items[slug]['name']}:")
            for key, (was, now) in changed.items():
                print(f"    {key}: {was} -> {now}")

    for slug, spec in STAT_RULES.items():
        stat_rules["items"][slug] = spec
    stat_rules["targetPatch"] = PATCH

    catalogue = load("items.json")
    for item in catalogue:
        want = RESTRICTIONS.get(item["slug"])
        if want and item.get("restriction") != want:
            item["restriction"] = want
            print(f'{item["name"]}: restriction = {want}')

    groups = rules.get("hardExclusive", {})
    for group, slugs in MUTEX_ADD.items():
        current = groups.get(group, {}).get("slugs", [])
        for slug in slugs:
            if slug not in current:
                current.append(slug)
                print(f"mutex {group}: + {slug}")
        groups.setdefault(group, {})["slugs"] = current

    if args.write:
        save("item_engine_overrides.json", overrides)
        save("item_stat_rules.json", stat_rules)
        save("item_rules.json", rules)
        (DATA / "items.json").write_text(
            json.dumps(catalogue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("\nwrote item_engine_overrides.json, item_stat_rules.json, "
              "item_rules.json, items.json")
    else:
        print("\ndry run: pass --write to save")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
