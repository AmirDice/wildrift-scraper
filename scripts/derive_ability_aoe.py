"""Derive per-component area targeting for the explicit multi-target fight.

The 1v3 axis is worth 30% of the tournament objective, so a champion whose
damage is all single-target in the engine loses to one holding Runaan's even
when its own kit clears three people.  Before this script only Graves was
curated, which meant every other champion's Q/W/E contributed nothing and the
axis quietly measured "does this build buy item AoE".

Three sources, in descending authority:

1. ``data/ability_aoe_overrides.json`` -- hand-verified component rules.  These
   always win.  An ability whose components disagree (Graves' ultimate: the
   shell hits one target, the cone behind it hits the others) can ONLY be
   expressed here, because the derivation works a whole ability at a time.
2. ``data/ult_shape.json`` -- the hand-verified list of AoE ultimates, already
   checked against tooltips once.  It settles slot 4 outright.
3. The ability text in ``web-next/src/data/champion_details.json``, read one
   damage sentence at a time.

Reading damage sentences rather than whole tooltips is what makes the text
usable.  "Enemies" appears in 312 of 715 abilities, but very often in a clause
about vision or a slow that has nothing to do with who takes the hit; a
tooltip-wide match tags Graves' Smoke Screen from "enemies cannot see outside
of it".  Restricting the match to the sentence that states the damage drops
almost all of that.

Run: python -m scripts.derive_ability_aoe [--check]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DETAILS = ROOT / "web-next" / "src" / "data" / "champion_details.json"
FORMULAS = ROOT / "data" / "ability_formulas.json"
ULT_SHAPE = ROOT / "data" / "ult_shape.json"
OVERRIDES = ROOT / "data" / "ability_aoe_overrides.json"
OUT = ROOT / "data" / "ability_aoe.json"

# Only two secondaries exist in the scenario, so this is also the ceiling.
SECONDARIES = 2

# Language that means the damage sentence reaches more than the primary target.
#
# A BARE plural is not on this list, and that is the whole trick.  "Attacks
# cause enemies to bleed" (Darius), "Zed's attacks against enemies below 50%
# Health" and "Units hit take 72% AD" (Graves' four shotgun pellets landing on
# one body) are all ordinary English plurals describing a single-target effect.
# Matching them tagged three passives as area damage and tripled those
# champions' auto-attack output in the 1v3.  Every marker below names an area,
# a path, or a count of victims.
_MULTI = re.compile(
    r"\ball enemies\b|\bnearby\b|\bsurrounding\b|\baround (?:it|him|her|them|the)\b"
    r"|\bin the area\b|\bin an area\b|\barea of effect\b|\bon an area\b"
    r"|\bcone\b|\bradius\b|\bexplod|\berupt|\bdetonat\w* (?:in|around)\b"
    r"|\bpasses through\b|\bpassing through\b|\bpierc\w*\b|\bin a line\b"
    r"|\bin its path\b|\bin their path\b|\bsplash\b"
    r"|\benemies hit\b|\benemies caught\b|\bcaught in\b|\beach enemy\b"
    r"|\bevery enemy\b|\beach champion\b|\bmultiple enemies\b|\bother enemies\b"
    r"|\bsecondary targets?\b|\bboth targets\b|\benemies in\b|\benemies within\b"
    r"|\benemies struck\b",
    re.I,
)

# A clause that spreads only to minions and monsters is not champion AoE.  Jhin's
# Deadly Flourish "stops on the first champion hit ... and 75% of that damage to
# minions and monsters hit along the way" is a single-target champion ability.
_PVE_SPREAD = re.compile(
    r"\bto minions\b|\bminions and monsters\b|\bagainst minions\b"
    r"|\bto non-champions\b|\bnon-champions\b",
    re.I,
)

# Abilities that reach exactly one extra body, not the whole scenario.
_ONE_EXTRA = re.compile(r"\bboth targets\b|\ba second (?:target|enemy)\b"
                        r"|\bone additional\b|\bricochets?\b|\bbounc\w*\b", re.I)

# Components that are basic-attack riders rather than the ability's own area
# hit.  An ability can be area damage while one of its components is not:
# Blitzcrank's Static Field zaps the whole area on cast but its passive arcs to
# one enemy, and Jax's ultimate passive is simply every third attack.  These
# land on the body being attacked, so they stay primary-only unless an override
# says otherwise.  Gragas is the exception that proves the rule and is curated.
_ATTACK_RIDER = re.compile(
    r"\bauto\b|\bautos\b|on.?hit|\bbasic attack|\bpassive\b|empowered attack",
    re.I,
)

# Phrases that pull a sentence BACK to single-target even when a plural noun is
# in it.  "Enemies hit by the first cast" is AoE; "the first enemy hit" is not.
_SINGLE = re.compile(
    r"\bthe first enemy\b|\bfirst enemy hit\b|\bsingle target\b|\bone enemy\b"
    r"|\bthe target\b(?!s)|\btarget enemy\b|\bnearest enemy\b|\bthe enemy hit\b",
    re.I,
)

# "deals 50% damage to other enemies" / "secondary targets take 60%".
_REDUCED = re.compile(
    r"(\d{1,3})\s*%\s*(?:of the\s*)?damage\s+to\s+(?:other|secondary|subsequent|additional|nearby)",
    re.I,
)
# Caitlyn's "Hitting an enemy expands the bullet, but reduces subsequent damage
# by 40%" states the falloff the other way round.
_FALLOFF = re.compile(r"reduces? (?:subsequent|further|additional) damage by\s*(\d{1,3})\s*%",
                      re.I)

# Sentences that never describe who takes the hit.  Dropping them first is what
# keeps a vision or movement clause from tagging the whole ability.
_NOT_DAMAGE = re.compile(
    r"\bcannot see\b|\bgrants? vision\b|\breveal|\bheals?\b|\bshields?\b"
    r"|\brestores?\b|\bmana\b|\bcooldown\b|\bgains? \d|\bmove(?:ment)? speed\b",
    re.I,
)

# Riot's tooltips often state an amount without the noun: Darius' Decimate
# reads "Hitting enemies with the blade of the axe deals 50 / 90 / 130 / 170",
# which a bare /damage/ test throws away along with the only AoE marker in the
# ability.  Any sentence that deals or takes a number is a damage sentence.
_DAMAGE = re.compile(r"\bdamage\b|\bdeals?\s|\bdealing\s|\btakes?\s|\binflicts?\s", re.I)


def _load(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _sentences(text: str) -> list[str]:
    """Split a tooltip into sentences without losing decimal numbers."""
    guarded = re.sub(r"(\d)\.(\d)", r"\1<DOT>\2", text or "")
    parts = re.split(r"(?<=[.:;])\s+", guarded)
    return [p.replace("<DOT>", ".").strip() for p in parts if p.strip()]


def classify_ability(text: str) -> tuple[bool, int, int, str]:
    """Return (is_aoe, secondary_pct, max_secondary_targets, deciding sentence)."""
    best: tuple[bool, int, int, str] = (False, 0, 0, "")
    # Falloff is read from the WHOLE ability, because Riot routinely states it
    # in its own sentence: Caitlyn's Q is "a narrow piercing bullet" in one
    # sentence and "reduces subsequent damage by 40%" in the next.
    whole_pct = 100
    if (reduced := _REDUCED.search(text or "")):
        whole_pct = int(reduced.group(1))
    elif (falloff := _FALLOFF.search(text or "")):
        whole_pct = max(0, 100 - int(falloff.group(1)))
    for sentence in _sentences(text):
        if not _DAMAGE.search(sentence):
            continue
        if not _MULTI.search(sentence):
            continue
        # A sentence about vision or healing may still carry the word damage in
        # a trailing clause; it never decides targeting on its own.
        if _NOT_DAMAGE.search(sentence) and not _MULTI.search(sentence):
            continue
        # The spread is real but lands on minions only.
        if _PVE_SPREAD.search(sentence) and not re.search(
                r"\ball enemies\b|\bnearby\b|\bcone\b|\benemies (?:hit|caught|in|within)\b",
                sentence, re.I):
            continue
        if _SINGLE.search(sentence) and not re.search(
                r"\ball enemies\b|\bnearby\b|\bcone\b|\bexplod|\benemies hit\b",
                sentence, re.I):
            continue
        pct = whole_pct
        reach = 1 if _ONE_EXTRA.search(sentence) else SECONDARIES
        if not best[0] or pct > best[1]:
            best = (True, pct, reach, sentence[:200])
    return best


def build(verbose: bool = False) -> tuple[dict, dict]:
    details = _load(DETAILS, {}) or {}
    formulas = _load(FORMULAS, {}) or {}
    aoe_ults = set((_load(ULT_SHAPE, {}) or {}).get("aoeUlts") or [])
    overrides_doc = _load(OVERRIDES, {}) or {}
    overrides = overrides_doc.get("champions") or {}

    # champion_details is slug-keyed; ability_formulas is display-name keyed.
    by_name = {(rec.get("name") or "").strip(): rec for rec in details.values()}

    out: dict[str, dict] = {}
    stats = {"champions": 0, "aoeAbilities": 0, "components": 0,
             "fromUltShape": 0, "fromText": 0, "fromOverride": 0,
             "reduced": 0, "oneExtra": 0, "riderSkipped": 0, "missingText": []}

    for champion, record in sorted(formulas.items()):
        detail = by_name.get(champion)
        abilities = (record.get("abilities") or {})
        texts = {}
        if detail:
            for entry in detail.get("abilities") or []:
                texts[str(entry.get("slot"))] = entry.get("text") or ""
        elif abilities:
            stats["missingText"].append(champion)

        champ_rules: dict[str, dict] = {}
        for slot, ability in abilities.items():
            slot = str(slot)
            components = [c for c in (ability.get("damage") or [])
                          if c.get("name")]
            if not components:
                continue

            # The passive slot is never derived.  A passive's damage rides on
            # basic attacks or a single-target proc, the engine already routes
            # auto damage on its own, and passive tooltips are the densest
            # source of incidental plurals.  Only an override makes one AoE.
            if slot == "P":
                continue

            is_aoe, pct, reach, why = classify_ability(texts.get(slot, ""))
            source = "text" if is_aoe else ""
            # The hand-checked ultimate list outranks the tooltip: it was built
            # precisely because a text heuristic got 7 of 23 ults wrong.
            if slot == "4" and champion in aoe_ults:
                is_aoe, pct, source = True, max(pct, 100), "ult-shape"
                reach = reach or SECONDARIES
            if not is_aoe:
                continue

            stats["aoeAbilities"] += 1
            stats["fromUltShape" if source == "ult-shape" else "fromText"] += 1
            if pct < 100:
                stats["reduced"] += 1
            slot_rules = {}
            for comp in components:
                comp_name = str(comp["name"])
                if _ATTACK_RIDER.search(comp_name):
                    stats["riderSkipped"] += 1
                    continue
                slot_rules[comp_name] = {
                    "primaryPct": 100,
                    "secondaryPct": pct,
                    "maxSecondaryTargets": reach,
                }
                stats["components"] += 1
            if not slot_rules:
                stats["aoeAbilities"] -= 1
                stats["fromUltShape" if source == "ult-shape" else "fromText"] -= 1
                continue
            if reach < SECONDARIES:
                stats["oneExtra"] += 1
            if verbose:
                print(f"  {champion:16} {slot}  {source:10} {pct:3}% x{reach}  {why}")
            champ_rules[slot] = slot_rules

        # Hand curation is applied last so it can both correct a derived rule
        # and introduce a component the derivation never reached.
        for slot, slot_rules in (overrides.get(champion) or {}).items():
            merged = dict(champ_rules.get(str(slot)) or {})
            for comp, rule in slot_rules.items():
                merged[comp] = {k: v for k, v in rule.items()
                                if not k.startswith("_")}
                stats["fromOverride"] += 1
            champ_rules[str(slot)] = merged

        if champ_rules:
            out[champion] = champ_rules
            stats["champions"] += 1

    doc = {
        "_note": ("GENERATED by scripts/derive_ability_aoe.py -- do not hand edit. "
                  "Per-component area targeting for the explicit multi-target fight "
                  "scenario. Hand corrections belong in data/ability_aoe_overrides.json. "
                  "Components absent here are primary-target only. primaryPct fixes "
                  "components such as Graves' cone that cannot hit the initial target; "
                  "secondaryPct is damage dealt to each eligible secondary target."),
        "champions": out,
    }
    return doc, stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="fail if the committed file is stale")
    ap.add_argument("--verbose", action="store_true",
                    help="print every ability the text classifier tagged")
    args = ap.parse_args()

    doc, stats = build(verbose=args.verbose)
    rendered = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"

    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != rendered:
            print("ability_aoe.json is stale; run python -m scripts.derive_ability_aoe",
                  file=sys.stderr)
            return 1
        print("ability_aoe.json is current")
        return 0

    OUT.write_text(rendered, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    print(f"  champions with AoE : {stats['champions']}")
    print(f"  AoE abilities      : {stats['aoeAbilities']} "
          f"({stats['fromText']} from text, {stats['fromUltShape']} from ult_shape)")
    print(f"  damage components  : {stats['components']}")
    print(f"  hand overrides     : {stats['fromOverride']}")
    print(f"  reduced-secondary  : {stats['reduced']}")
    print(f"  one extra target   : {stats['oneExtra']}")
    print(f"  attack riders kept primary-only : {stats['riderSkipped']}")
    if stats["missingText"]:
        print(f"  NO TOOLTIP TEXT    : {len(stats['missingText'])} "
              f"({', '.join(stats['missingText'][:6])})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
