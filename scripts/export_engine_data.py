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


def _load(name: str):
    p = ROOT / "data" / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def main() -> None:
    champs_all = _load("champions_wr.json")
    formulas = _load("ability_formulas.json")
    items = _load("items.json")
    item_fx = _load("item_engine.json")
    for slug, fx in _load("item_engine_overrides.json").items():
        if isinstance(fx, dict):
            item_fx.setdefault(slug, {}).update({k: v for k, v in fx.items()
                                                 if not k.startswith("_")})
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

    from web.fight_engine import kit_adjust

    out = {
        "champions": {
            c["name"]: {
                "baseStats": c.get("baseStats", {}),
                "mechanics": c.get("mechanics", []),
                "class": champ_class.get(c["name"], ""),
                "primaryDamage": c.get("primaryDamage", ""),
                "scalesWith": c.get("scalesWith", []),
                "skillOrder": (guide.get(c["name"]) or {}).get("skillOrder", {}),
                # precomputed in Python (needs full ability text) for TS parity
                "kitShift": kit_adjust(c["name"]),
            }
            for c in champs_all if c["name"] in formulas
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
        "mutex": rules.get("mutexGroups", {}),
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
    roster = {}
    for c in champs_all:
        name = c["name"]
        meta = site_meta.get(name, {})
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


if __name__ == "__main__":
    main()
