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
from pathlib import Path

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

    from web.fight_engine import kit_adjust, repeats_on_hit

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
        roster[name] = {
            "slug": c["slug"], "name": name,
            "class": meta.get("class", ""), "role": meta.get("role", ""),
            "icon": meta.get("icon", ""),
            "primaryDamage": c.get("primaryDamage", ""),
            "scalesWith": c.get("scalesWith", []),
            "mechanics": c.get("mechanics", []),
            "baseStats": {k: bs.get(k, {}) for k in ("hp", "armor", "mr", "ad")},
        }
    ROSTER_OUT.write_text(json.dumps(roster, ensure_ascii=False), encoding="utf-8")
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
