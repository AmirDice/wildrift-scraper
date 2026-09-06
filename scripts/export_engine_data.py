"""Bundle everything the BROWSER fight engine needs into one JSON.

The TypeScript port of web/fight_engine.py (web-next/src/lib/engine.ts) runs
custom-build scoring client-side (users swapping items/runes and seeing live
metrics). This exports its inputs from the same source files the Python engine
uses, so both engines compute from identical data.

Output: web-next/src/data/engine.json

Run after any data refresh:
    python -m scripts.export_engine_data
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from web.advisor import hardcc  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web-next" / "src" / "data" / "engine.json"
ROSTER_OUT = ROOT / "web-next" / "src" / "data" / "roster.json"
STAT_RULES_OUT = ROOT / "web-next" / "src" / "data" / "stat_rules.json"
COMBOS_OUT = ROOT / "web-next" / "src" / "data" / "champion_combos.json"


def _load(name: str):
    p = ROOT / "data" / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}



def apply_cooldown_corrections(formulas: dict) -> int:
    """Fold data/ability_cooldown_corrections.json into the formulas.

    The scrape got Kayn's cooldowns wrong in both forms, and wrong in
    DIFFERENT ways -- it produced two distinct sets where the game has one.
    Owner-verified values live in the overlay so a re-extraction cannot quietly
    put the wrong numbers back.
    """
    path = ROOT / "data" / "ability_cooldown_corrections.json"
    if not path.exists():
        return 0
    overlay = json.loads(path.read_text(encoding="utf-8"))
    applied = 0
    for name, entry in (overlay.get("champions") or {}).items():
        record = formulas.get(name)
        if not record:
            continue
        for slot, fix in (entry.get("abilities") or {}).items():
            ability = (record.get("abilities") or {}).get(slot)
            if not ability or "cooldowns" not in fix:
                continue
            ability["cooldowns"] = [float(v) for v in fix["cooldowns"]]
            applied += 1
    return applied


def apply_formula_corrections(formulas: dict) -> int:
    """Fold data/formula_corrections.json into the formulas.

    Reviewed fixes to the LLM-estimated `knowledge` and `mechanics` blocks:
    wrong resource types (Graves flagged manaless while paying 65-80 per Q),
    and asEfficiency values stuck at the 0.2 caster floor on kits whose
    abilities explicitly count attacks (Twisted Fate, Nilah, Kennen). The
    advisor and the fight engine fold in the same file at load.
    """
    path = ROOT / "data" / "formula_corrections.json"
    if not path.exists():
        return 0
    overlay = json.loads(path.read_text(encoding="utf-8"))
    applied = 0
    for name, entry in (overlay.get("champions") or {}).items():
        rec = formulas.get(name)
        if not rec:
            continue
        know = rec.setdefault("knowledge", {})
        for key, value in (entry.get("knowledge") or {}).items():
            know[key] = value
            applied += 1
        drop = set(entry.get("removeMechanics") or [])
        if drop:
            kept = [m for m in rec.get("mechanics") or [] if m.get("kind") not in drop]
            applied += len(rec.get("mechanics") or []) - len(kept)
            rec["mechanics"] = kept
        # Per-slot ability overrides: `damage` replaces the slot's damage list
        # wholesale. Added for Camille's Q, whose scraped text was missing the
        # recast sentence and with it the 40% true-damage conversion.
        for slot, patch in (entry.get("abilities") or {}).items():
            ability = (rec.get("abilities") or {}).get(slot)
            if ability is not None and "damage" in patch:
                ability["damage"] = patch["damage"]
                applied += 1
            if ability is not None and "empowerLimit" in patch:
                ability["empowerLimit"] = patch["empowerLimit"]
                applied += 1
    return applied


def _apply_recovered_conditions(formulas: dict) -> int:
    """Fold data/ability_conditions.json into the formulas.

    Recovered conditions are written into the fields the engines already read
    -- durationS on a steroid, n on an everyNHit mechanic -- so nothing in
    either simulation changes. The extractor recorded that these effects were
    conditional and then dropped the numbers; this puts them back.
    """
    path = ROOT / "data" / "ability_conditions.json"
    if not path.exists():
        return 0
    overlay = json.loads(path.read_text(encoding="utf-8"))
    applied = 0
    for name, entries in (overlay.get("durations") or {}).items():
        rec = formulas.get(name)
        if not rec:
            continue
        for key, value in entries.items():
            slot, _, idx = key.partition(":")
            steroids = ((rec.get("abilities") or {}).get(slot) or {}).get("steroids") or []
            if idx.isdigit() and int(idx) < len(steroids):
                steroids[int(idx)]["durationS"] = value["seconds"]
                applied += 1
    for name, entry in (overlay.get("everyN") or {}).items():
        for mech in (formulas.get(name) or {}).get("mechanics") or []:
            if mech.get("kind") == "everyNHit":
                mech["n"] = entry["n"]
                applied += 1
    return applied


def main() -> None:
    champs_all = _load("champions_wr.json")
    # Transform forms ship as champions of their own so the browser engine can
    # simulate the kit the user is actually looking at. Without this the
    # customizer would price Rhaast's build against Shadow Assassin's kit,
    # which is the mismatch the whole form split exists to remove. They are not
    # in the roster, so nothing lists them -- only a lookup by name finds them.
    champs_all = champs_all + [f for c in champs_all for f in (c.get("forms") or [])]
    champion_overrides = _load("champion_stat_overrides.json").get("champions", {})
    item_stat_rules = _load("item_stat_rules.json").get("items", {})
    rune_stat_rules = _load("rune_stat_rules.json").get("runes", {})
    for champion in champs_all:
        override = champion_overrides.get(champion.get("name"), {})
        for stat, values in override.get("baseStats", {}).items():
            champion.setdefault("baseStats", {})[stat] = {
                key: value for key, value in values.items()
                if key in {"base", "perLevel", "lvl15"}
            }
        if override.get("statRules"):
            champion["statRules"] = override["statRules"]
    formulas = _load("ability_formulas.json")
    # Combos come from champion_combos.json, not from the extraction.
    #
    # ability_formulas.json carries a `combo` field, but it is the one thing in
    # that file not grounded in the tooltip text, and the prompt that produced it
    # asked for the "standard all-in burst sequence" -- a different question from
    # the one the damage calculator needs. Asked instead for the HIGHEST DAMAGE
    # combo, the same model moved Xin Zhao from a W-opener to an E-opener, which
    # is what his kit actually wants.
    #
    # The overlay also survives re-extraction, so a human correction pinned there
    # is not silently overwritten the next time formulas are rebuilt.
    _apply_recovered_conditions(formulas)
    fixed = apply_cooldown_corrections(formulas)
    if fixed:
        print(f"applied {fixed} owner-verified cooldown corrections")
    fixed = apply_formula_corrections(formulas)
    if fixed:
        print(f"applied {fixed} formula knowledge/mechanics corrections")
    combos_file = _load("champion_combos.json") or {}
    combos = combos_file.get("champions") or {}
    for name, entry in combos.items():
        if name in formulas and entry.get("combo"):
            formulas[name]["combo"] = entry["combo"]
    items = _load("items.json")
    item_fx = _load("item_engine.json")
    for slug, fx in _load("item_engine_overrides.json").items():
        if isinstance(fx, dict):
            item_fx.setdefault(slug, {}).update({k: v for k, v in fx.items()
                                                 if not k.startswith("_")})
    # A spellblade's damage TYPE is read from the item's own passive text
    # (mirrors fight_engine's text scan). The TS engine ships no passives
    # text, so the flag is stamped into itemFx here at export time.
    for it in items:
        fx = item_fx.get(it.get("slug") or "")
        if not fx or not (fx.get("spellbladeBaseAdPct") or fx.get("spellbladeApPct")):
            continue
        txt = " ".join(it.get("passives") or []).lower()
        if "spellblade" in txt and "magic damage" in txt:
            fx["spellbladeMagic"] = 1
    rune_fx = _load("rune_effects.json")
    rune_engine = _load("rune_engine.json")
    runes = _load("runes.json")
    rules = _load("item_rules.json")
    slots = _load("rune_slots.json").get("trees", {})
    guide = _load("wrf_guide_meta.json")

    site_p = ROOT / "web-next" / "src" / "data" / "site.json"
    site = json.loads(site_p.read_text(encoding="utf-8")) if site_p.exists() else {}
    champ_class = {c["name"]: c.get("class", "") for c in site.get("champions", [])}

    slot_of = {}
    for tree, ss in slots.items():
        for s, names in ss.items():
            for n in names:
                slot_of[n] = int(s)

    from web.fight_engine import (kit_adjust, repeats_on_hit, damage_metric,
                                  attack_speed_ratio, AS_CURVE)

    out = {
        "champions": {
            c["name"]: {
                "baseStats": c.get("baseStats", {}),
                "mechanics": c.get("mechanics", []),
                "class": champ_class.get(c["name"], ""),
                "primaryDamage": c.get("primaryDamage", ""),
                "scalesWith": c.get("scalesWith", []),
                "skillOrder": (guide.get(c["name"]) or {}).get("skillOrder", {}),
                "statRules": c.get("statRules", {}),
                # precomputed in Python (needs full ability text) for TS parity
                "kitShift": kit_adjust(c["name"]),
                # Does this kit's on-hit fire on EVERY attack? Decides whether
                # an item that re-applies on-hits re-applies the kit's own
                # (Gwen's Thousand Cuts, yes; Lux's consumed mark, no).
                "repeatsOnHit": repeats_on_hit(c["name"]),
                # Which axis this champion is judged on: burst / sustained /
                # durability. Ranking a burst mage on 8-second sustained damage
                # is what made on-hit items look strong on casters.
                "damageMetric": damage_metric(c["name"]),
                # Attack speed RATIO (what % bonuses multiply) and per-level
                # growth, verified in game. Absent growth means the champion
                # has not been measured, and the TS engine must then behave
                # exactly as before: no level scaling.
                "asRatio": attack_speed_ratio(
                    c["name"],
                    (c.get("baseStats", {}).get("attackSpeed", {}) or {}).get("base", 0.75) or 0.75),
                "asGrowth": float((AS_CURVE.get(c["name"]) or {}).get("attackSpeedGrowth") or 0.0),
            }
            # Stats and skill ranks exist for the full roster. Structured
            # formulas are optional and only control live damage breakdowns.
            for c in champs_all
        },
        "formulas": formulas,
        "items": {
            it["slug"]: {"name": it["name"], "cost": it["cost"], "icon": it["icon"],
                         "category": it["category"], "stats": it["stats"]}
            for it in items
        },
        "itemFx": {k: v for k, v in item_fx.items() if v and not k.startswith("_")},
        "runeFx": {"keystones": {k: v for k, v in rune_fx.get("keystones", {}).items()},
                   "minors": {k: v for k, v in rune_fx.get("minors", {}).items()}},
        "runeEngine": {k: v for k, v in rune_engine.items() if v},
        "runes": {
            r["name"]: {"slug": r["slug"], "icon": r["icon"], "tree": r.get("tree", ""),
                        "type": r["type"], "slot": slot_of.get(r["name"], 0),
                        "description": r.get("description", "")}
            for r in runes
        },
        # `hardExclusive` replaced the flat `mutexGroups` map and nests the
        # slugs alongside their evidence; fall back to the old shape so an
        # older data file still exports something rather than nothing.
        "mutex": {
            name: (group["slugs"] if isinstance(group, dict) else group)
            for name, group in (rules.get("hardExclusive")
                                or rules.get("mutexGroups") or {}).items()
            if not name.startswith("_")
        },
        "situationalOnly": (rules.get("situationalOnly") or {}).get("slugs", []),
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size/1024:.0f} KB, "
          f"{len(out['champions'])} champions, {len(out['items'])} items, "
          f"{len(out['runes'])} runes)")

    # Full-roster threat data for the enemy-team optimizer: every champion the
    # enemy could pick, with the fields needed to derive a threat profile and a
    # real defensive target (damage type, kit mechanics, class, base stats).
    site_meta = {c["name"]: c for c in site.get("champions", [])}
    # Champions with no leaderboard data yet are absent from site.json, so
    # their class/role/icon would export EMPTY until the first scrape lands --
    # Skarner and Yunara both shipped that way and looked broken in every
    # picker. Release-day fallback; site.json wins the moment it knows them.
    prerelease_meta = {
        "Cho'Gath": {"class": "Tank", "role": "Baron",
                     "icon": "https://ddragon.leagueoflegends.com/cdn/16.11.1/img/champion/Chogath.png"},
    }
    # The scraped `mechanics` tags are too blunt to describe a threat: `heal`
    # sits on 109 of 141 champions and `cc` on 134, so a comp of any five reads
    # "everyone sustains, everyone has crowd control" and the threat panel says
    # nothing. Jinx shipped as a healer on the strength of that tag.
    #
    # Healing and shielding are re-derived from the extracted formulas, where a
    # `defensive` component is real evidence rather than a keyword; hard crowd
    # control is re-derived from the ability tooltips, which name the effect
    # (the formulas' unmodeled notes miss Malphite's ultimate entirely). dash
    # and onHit keep their scraped tags -- those are already specific.
    # The effect must be something the champion does TO ENEMIES: Kai'Sa's
    # passive mentions what nearby ALLIES immobilise and she counted as a
    # crowd-control threat because of it.
    # The hard-crowd-control regexes that used to sit here were a verbatim
    # copy of the advisor's, and the copies had already drifted apart in
    # what they were asked to do. One module now, imported by both.

    # Owner corrections to the scraped class / roles / damage type. The scrape
    # allows one class and one role each, which mislabels kits (Warwick is not
    # an assassin) and pretends nobody flexes (Olaf is Baron only, so a jungle
    # main was never offered the best answer in the game to a crowd-control
    # composition). See data/champion_meta_overrides.json.
    meta_overrides = (_load("champion_meta_overrides.json") or {}).get("champions", {})

    def deals_pct_hp(name: str) -> bool:
        """Damage that scales with the target's max health.

        The one property that decides whether a pick answers a heavy enemy
        frontline, and it cannot be read off a class: Fiora and Gwen carry it,
        most bruisers do not. 45 of 142 champions have it, so it discriminates
        where "is a bruiser" does not.
        """
        for ability in ((formulas.get(name) or {}).get("abilities") or {}).values():
            for dmg in (ability.get("damage") or []):
                if any(r.get("stat") == "targetMaxHp" for r in (dmg.get("ratios") or [])):
                    return True
        return False

    #: Kits that shrug off crowd control rather than merely surviving it:
    #: Olaf's ultimate removes every debuff and makes him immune, Sivir's
    #: spell shield eats the ability outright. Read from the champion's own
    #: ability text, and only when the sentence is about the champion --
    #: "reduces the duration of" or "immune to" applied to an ALLY is somebody
    #: else's answer, and the word "cleanse" shows up in enemy-facing text too.
    cc_immunity = re.compile(
        r"(immune to (?:all )?(?:crowd control|cc)|crowd[- ]control immunity"
        r"|remove[sd]? all (?:crowd control|cc|debuff)"
        r"|becomes? (?:unstoppable|untargetable)|cannot be (?:stopped|interrupted)"
        r"|spell shield|blocks? the next enemy ability)", re.I)

    #: Same trap as the hard-crowd-control scan: the sentence has to be about
    #: the CHAMPION. Darius's ultimate text lists "the target ... becomes
    #: untargetable" as a case where his reset FAILS, and Zilean's revives an
    #: ally who "become[s] untargetable". Both read as self-immunity without
    #: this guard.
    immunity_not_mine = re.compile(r"\b(target|ally|allies|enemy|enemies|they)\b", re.I)

    def clears_cc(champ: dict) -> bool:
        """Whether this champion's own kit answers being locked down.

        The single most decision-relevant fact against a crowd-control comp,
        and invisible to class: Olaf is a bruiser like a dozen others and is
        the one who ignores the whole composition. Reported as a trait because
        the pick ranker had NO representation of it and put three champions
        above Olaf into five enemies who all lock you down.
        """
        text = " ".join((a.get("text") or "") + " " + (a.get("name") or "")
                        for a in (champ.get("abilities") or []))
        for m in cc_immunity.finditer(text):
            if not immunity_not_mine.search(text[max(0, m.start() - 80):m.start()]):
                return True
        return False

    def with_forms(champ: dict) -> list[str]:
        """This champion's formula key plus every form it can transform into."""
        return [champ["name"]] + [f["name"] for f in (champ.get("forms") or [])]

    def deals_true_damage(name: str) -> bool:
        """True damage ignores resistances, so it answers a stacked frontline
        the way percent-health damage does. Olaf carries it on Reckless Swing
        and carries no percent-health damage at all, which is why he never
        registered as an answer to a team of tanks."""
        for ability in ((formulas.get(name) or {}).get("abilities") or {}).values():
            for dmg in (ability.get("damage") or []):
                if dmg.get("type") == "true":
                    return True
        return False

    def derived_mechanics(champ: dict) -> list[str]:
        kept = [m for m in (champ.get("mechanics") or []) if m in ("dash", "onHit")]
        formula = (formulas.get(champ["name"]) or {}).get("abilities") or {}
        kinds = {d.get("kind")
                 for ability in formula.values()
                 for d in (ability.get("defensive") or [])}
        if "heal" in kinds:
            kept.append("heal")
        if "shield" in kinds:
            kept.append("shield")
        if hardcc.has_hard_cc(champ.get("abilities"), champ["name"]):
            kept.append("cc")
        return kept

    # What a COMPOSITION is trying to do, which no tooltip states. A draft is
    # usually beaten by answering the plan rather than the five champions
    # separately: Fiora plus Twisted Fate is side-lane pressure with a global
    # follow-up, not "a bruiser and a mage". Owner-maintained, and absence
    # means "not this", so a missing entry costs sensitivity and never invents
    # a threat.
    archetypes = (_load("draft_archetypes.json") or {}).get("tags", {})
    archetype_of = {}
    for tag, names in archetypes.items():
        for name in names:
            archetype_of.setdefault(name, []).append(tag)

    #: A shield or a heal that lands on somebody ELSE. Blitzcrank's passive
    #: reads "Blitzcrank gains a shield that absorbs 90 damage upon falling
    #: below 35% Health" -- that is him surviving, not him protecting a carry,
    #: and counting it as protection made him the top recommendation for
    #: keeping an immobile hypercarry alive against a dive composition.
    #:
    #: Lulu says "On Allies: Grants a shield", Janna "Blesses herself and the
    #: allied champion", Alistar "heals himself for 27 and nearby allied
    #: champions for 54". Naming an ally in the same ability is the whole
    #: discrimination, and it is a reliable one: a defensive ability that
    #: mentions allies is doing something for them.
    protective_word = re.compile(r"\b(shield\w*|heal\w*|restor\w*)", re.I)
    ally_word = re.compile(r"\ball(?:y|ies|ied)\b", re.I)

    def protects_allies(champ: dict) -> bool:
        for ability in champ.get("abilities") or []:
            text = ability.get("text") or ""
            if protective_word.search(text) and ally_word.search(text):
                return True
        return False

    def cc_depth(champ: dict) -> int:
        """How many of this champion's abilities lock somebody down.

        Presence alone cannot tell Sona -- one stun, on a long ultimate --
        from Alistar, who has three and lands them on demand, and the overlay
        was drawing both as the same threat. The bundle carries the number so
        the draft panel can show an intensity instead of a boolean."""
        return hardcc.hard_cc_depth(champ.get("abilities"), champ["name"])

    roster = {}
    # Forms are deliberately absent here. The roster is the list of champions
    # the site shows and the threat model iterates; a form is a kit, not an
    # extra champion to pick, and letting one in would put "Kayn (Rhaast)" in
    # every enemy-team picker beside Kayn himself.
    for c in champs_all:
        if c.get("formOf"):
            continue
        name = c["name"]
        meta = site_meta.get(name) or prerelease_meta.get(name, {})
        bs = c.get("baseStats", {})
        override = meta_overrides.get(name) or {}
        primary_role = meta.get("role", "")
        roles = override.get("roles") or ([primary_role] if primary_role else [])
        roster[name] = {
            "slug": c["slug"], "name": name,
            "class": override.get("class") or meta.get("class", ""),
            # Every class the kit really is, primary first. Kayn is both, and
            # which one depends on the form he transforms into.
            "classes": override.get("classes")
                or ([override.get("class") or meta.get("class", "")]
                    if (override.get("class") or meta.get("class")) else []),
            "role": roles[0] if roles else primary_role,
            # Every role the champion is actually played in, primary first.
            "roles": roles,
            "icon": meta.get("icon", ""),
            "primaryDamage": override.get("damage") or c.get("primaryDamage", ""),
            "scalesWith": c.get("scalesWith", []),
            "mechanics": derived_mechanics(c),
            "ccDepth": cc_depth(c),
            "protectsAllies": protects_allies(c),
            "archetypes": sorted(archetype_of.get(name, [])),
            # Traits union over the champion's TRANSFORM FORMS. Kayn's
            # percent-health damage lives entirely on Rhaast, and the roster
            # excludes forms, so base Kayn read as no answer to a team of
            # tanks -- while a player drafting Kayn is choosing Rhaast as part
            # of the pick. What the pick can become is what the pick offers.
            "pctHpDamage": any(deals_pct_hp(n) for n in with_forms(c)),
            "trueDamage": any(deals_true_damage(n) for n in with_forms(c)),
            "ccImmune": clears_cc(c) or any(
                clears_cc(f) for f in (c.get("forms") or [])),
            "baseStats": {k: bs.get(k, {}) for k in ("hp", "armor", "mr", "ad")},
        }
    ROSTER_OUT.write_text(json.dumps(roster, ensure_ascii=False), encoding="utf-8")

    # The same corrections have to reach lib/data.ts, which builds every
    # champion the SITE renders from site.json and would otherwise still call
    # Garen a tank and hide Olaf from the jungle.
    meta_out = ROSTER_OUT.parent / "champion_meta_overrides.json"
    # Keep the {"champions": {...}} shape the source file has: lib/data.ts
    # reads .champions, and writing the bare map made every override silently
    # no-op there while still applying to roster.json.
    meta_out.write_text(json.dumps({"champions": meta_overrides},
                                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {meta_out.relative_to(ROOT)} ({len(meta_overrides)} champions)")
    print(f"wrote {ROSTER_OUT.relative_to(ROOT)} ({ROSTER_OUT.stat().st_size/1024:.0f} KB, "
          f"{len(roster)} champions)")

    stat_rules = {
        "schemaVersion": 1,
        # Read from the data, not hard-coded here. It WAS hard-coded, so
        # applying 7.2b updated champion_stat_overrides.json and this
        # exporter then wrote "7.2a" straight back over it -- the site would
        # have shipped 7.2b numbers under a 7.2a label, including in the
        # build cache key, which is keyed on the patch.
        "targetPatch": _load("champion_stat_overrides.json").get(
            "targetPatch", "unknown"),
        "champions": champion_overrides,
        "items": item_stat_rules,
        "runes": rune_stat_rules,
    }
    STAT_RULES_OUT.write_text(json.dumps(stat_rules, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    print(f"wrote {STAT_RULES_OUT.relative_to(ROOT)}")

    # The champion page shows the combo with the model's reasoning attached, so
    # the whole record ships rather than just the sequence baked into formulas.
    COMBOS_OUT.write_text(json.dumps(combos_file, indent=1, ensure_ascii=False),
                          encoding="utf-8")
    print(f"wrote {COMBOS_OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
