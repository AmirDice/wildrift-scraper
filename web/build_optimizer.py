"""Rule-based Wild Rift build + rune optimizer.

Given a champion, generate the best *generic* item build and rune page that
synergise with that champion's archetype. Deterministic and explainable:

  1. Archetype ← champion class (with per-champ overrides).
  2. Damage school (physical/magic, for item gating) ← champion class + the
     scraped ability scalings in data/champions_wr.json, so AP bruisers get AP
     items and AD casters get AD items.
  3. Each item is scored = normalised-stat·weights  + synergy-tag bonuses
     + LLM passiveValue[archetype]  − off-school penalty.
  4. `coreFor` items (from the LLM enrichment) are force-included — this is what
     puts Infinity Edge on crit ADCs and Ardent Censer on enchanters, which a
     pure stat sum misses.
  5. Pick a legal Wild Rift build: 5 core items + 1 boots + 1 enchantment.
  6. Recommend a keystone + minor runes per archetype from data/runes.json.

The dmg↔defense slider and enemy-comp counter-items plug into the SAME scoring
function later (blend the weight vector / add an enemy term). The LLM enrichment
(scripts/enrich_items_llm.py) and any LLM narration run OFFLINE — the runtime
path here stays deterministic.

Data:
    data/items.json          (scripts/scrape_items.py)
    data/runes.json          (scripts/scrape_runes.py)
    data/champions_wr.json   (scripts/scrape_champions.py)
    data/items_enriched.json (scripts/enrich_items_llm.py)  — optional
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ITEMS_PATH = ROOT / "data" / "items.json"
RUNES_PATH = ROOT / "data" / "runes.json"
CHAMPS_PATH = ROOT / "data" / "champions_wr.json"
ENRICHED_PATH = ROOT / "data" / "items_enriched.json"

PASSIVE_SCALE = 2.0  # how much the LLM passiveValue (0-1) can add to a score
CORE_BONUS = 2.5     # score bump for an LLM-flagged coreFor item (not a hard force)

# --- archetypes: stat-weight vector + preferred behavioural tags -----------
ARCHETYPES: dict[str, dict] = {
    "crit-adc": {
        "weights": {"ad": 0.7, "crit": 1.0, "attackSpeed": 0.8, "lifesteal": 0.4,
                    "physicalPen": 0.3, "abilityHaste": 0.1},
        "tags": {"onHit": 0.3, "sustain": 0.2},
    },
    "bruiser": {
        "weights": {"ad": 0.9, "hp": 0.7, "abilityHaste": 0.6, "physicalVamp": 0.5,
                    "attackSpeed": 0.4, "armor": 0.3, "mr": 0.3, "physicalPen": 0.4},
        "tags": {"sustain": 0.4, "armorShred": 0.3, "onHit": 0.2},
    },
    "assassin": {
        "weights": {"ad": 1.0, "lethality": 1.0, "abilityHaste": 0.6,
                    "physicalPen": 0.7, "attackSpeed": 0.2},
        "tags": {"lethality": 0.5, "mobility": 0.2},
    },
    "burst-mage": {
        "weights": {"ap": 1.0, "magicPen": 0.9, "abilityHaste": 0.7, "mana": 0.4},
        "tags": {"burn": 0.3, "magicPen": 0.4},
    },
    "tank": {
        "weights": {"hp": 1.0, "armor": 0.9, "mr": 0.9, "abilityHaste": 0.5,
                    "healShieldPower": 0.2},
        "tags": {"shield": 0.4, "sustain": 0.3, "slow": 0.2, "armorShred": 0.2},
    },
    "enchanter": {
        "weights": {"healShieldPower": 1.0, "abilityHaste": 0.8, "mana": 0.6,
                    "ap": 0.4, "moveSpeed": 0.4},
        "tags": {"shield": 0.5, "sustain": 0.4, "mana": 0.3},
    },
}

# damage school per archetype (used only when the champion scrape can't decide)
ARCHE_SCHOOL = {
    "crit-adc": "physical", "bruiser": "physical", "assassin": "physical",
    "burst-mage": "magic", "tank": "physical", "enchanter": "magic",
}

CLASS_ARCHETYPE = {
    "Marksman": "crit-adc", "Bruiser": "bruiser", "Assassin": "assassin",
    "Mage": "burst-mage", "Tank": "tank", "Enchanter": "enchanter",
}

# per-champion archetype overrides where class alone is wrong
CHAMPION_OVERRIDES: dict[str, str] = {
    "Master Yi": "bruiser", "Kai'Sa": "crit-adc", "Vayne": "crit-adc", "Nasus": "bruiser",
}

# per-archetype rune plan: ordered keystone prefs + minor rune name prefs.
# Names resolve against data/runes.json; unknown names are skipped.
RUNE_PLAN = {
    "crit-adc":   {"keystone": ["Lethal Tempo", "Fleet Footwork"],
                   "minors": ["Legend: Alacrity", "Coup de Grace", "Last Stand", "Legend: Bloodline"]},
    "bruiser":    {"keystone": ["Conqueror", "Grasp of the Undying"],
                   "minors": ["Legend: Tenacity", "Last Stand", "Overgrowth", "Coup de Grace"]},
    "assassin":   {"keystone": ["Electrocute", "Dark Harvest"],
                   "minors": ["Hubris", "Coup de Grace", "Relentless Hunter", "Tyrant"]},
    "burst-mage": {"keystone": ["Electrocute", "Arcane Comet", "Dark Harvest"],
                   "minors": ["Absolute Focus", "Celerity", "Axiom Arcanist", "Coup de Grace"]},
    "tank":       {"keystone": ["Grasp of the Undying", "Guardian"],
                   "minors": ["Overgrowth", "Revitalize", "Courage of the Colossus", "Unshakeable"]},
    "enchanter":  {"keystone": ["Guardian", "Aery"],
                   "minors": ["Revitalize", "Overgrowth", "Celerity", "Unshakeable"]},
}

BOOT_CATEGORIES = {"Boots"}
ENCHANT_CATEGORIES = {"Enchantment"}
SUPPORT_CATEGORIES = {"Support"}


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _load_items() -> list[dict]:
    return json.loads(ITEMS_PATH.read_text(encoding="utf-8"))


def _champ_profiles() -> dict[str, dict]:
    data = _load(CHAMPS_PATH) or []
    return {c["name"]: c for c in data}


def _enriched() -> dict[str, dict]:
    return _load(ENRICHED_PATH) or {}


def _stat(item: dict, key: str) -> float:
    s = item["stats"].get(key)
    return float(s["value"]) if s else 0.0


def _offense_type(item: dict) -> str:
    if any(item["stats"].get(k) for k in ("ad", "crit", "attackSpeed", "lethality", "physicalPen")):
        return "physical"
    if any(item["stats"].get(k) for k in ("ap", "magicPen")):
        return "magic"
    return "none"  # pure defense / utility — usable by anyone


def _derive_tags(item: dict) -> set[str]:
    tags: set[str] = set()
    st = item["stats"]
    passive = " ".join(item["passives"]).lower()
    if st.get("magicPen"):
        tags.add("magicPen")
    if st.get("lethality") or st.get("physicalPen"):
        tags.add("lethality")
    if st.get("attackSpeed"):
        tags.add("attackSpeed")
    if st.get("lifesteal") or st.get("physicalVamp") or st.get("omnivamp"):
        tags.add("sustain")
    if any(k in passive for k in ("grievous", "reduces healing", "healing is reduced")):
        tags.add("antiHeal")
    if any(k in passive for k in ("reduces their armor", "reduce armor", "sunder")):
        tags.add("armorShred")
    if "on-hit" in passive or "on hit" in passive:
        tags.add("onHit")
    if "shield" in passive:
        tags.add("shield")
    if "slow" in passive:
        tags.add("slow")
    if "burn" in passive or "per second for" in passive:
        tags.add("burn")
    if st.get("healShieldPower"):
        tags.add("shield")
    return tags


def _normalisers(items: list[dict]) -> dict[str, float]:
    maxes: dict[str, float] = {}
    for it in items:
        for k, v in it["stats"].items():
            maxes[k] = max(maxes.get(k, 0.0), float(v["value"]))
    return {k: (v or 1.0) for k, v in maxes.items()}


def archetype_for(name: str, champ_class: str) -> tuple[str, dict]:
    key = CHAMPION_OVERRIDES.get(name) or CLASS_ARCHETYPE.get(champ_class, "bruiser")
    return key, ARCHETYPES[key]


def damage_school(arche_key: str, champ_class: str, profile: dict | None) -> str:
    """Physical vs magic, for item gating. Class first, refined by scaled stats."""
    # Pure-AP kits: scale with AP and not AD -> always magic, whatever the class.
    if profile:
        scales = set(profile.get("scalesWith", []))
        has_ad = "ad" in scales or "bonusAd" in scales
        has_ap = "ap" in scales
        if has_ap and not has_ad:
            return "magic"
        if has_ad and not has_ap:
            return "physical"
    # class is authoritative for the common case (AP assassins are classed Mage)
    if champ_class in ("Mage", "Enchanter"):
        return "magic"
    if champ_class in ("Marksman", "Bruiser", "Assassin", "Tank"):
        return "physical"
    return ARCHE_SCHOOL.get(arche_key, "physical")


def _refined_weights(arche: dict, profile: dict | None) -> dict:
    """Small, data-driven nudges from the champion's scraped mechanics."""
    w = dict(arche["weights"])
    if not profile:
        return w
    mech = set(profile.get("mechanics", []))
    scales = set(profile.get("scalesWith", []))
    if "onHit" in mech or "attackSpeed" in scales:
        w["attackSpeed"] = max(w.get("attackSpeed", 0.0), 0.6)
    if "maxHp" in scales:
        w["hp"] = max(w.get("hp", 0.0), 0.5)
    return w


def score_item(item: dict, weights: dict, arche: dict, school: str,
               norm: dict[str, float], enriched: dict, arche_key: str) -> float:
    score = 0.0
    for stat, wt in weights.items():
        val = _stat(item, stat)
        if val:
            score += wt * (val / norm.get(stat, 1.0))
    tags = _derive_tags(item)
    for tag, bonus in arche.get("tags", {}).items():
        if tag in tags:
            score += bonus
    # LLM passive-value term + core bonus (0 when no enrichment file present)
    ev = enriched.get(item["slug"])
    if ev:
        score += PASSIVE_SCALE * float(ev.get("passiveValue", {}).get(arche_key, 0.0))
        if arche_key in ev.get("coreFor", []):
            score += CORE_BONUS
    # damage-school gating: penalise offensive items of the wrong school
    otype = _offense_type(item)
    if school in ("physical", "magic") and otype != "none" and otype != school:
        score -= 3.0
    return score


def _recommend_runes(arche_key: str) -> dict:
    runes = _load(RUNES_PATH) or []
    by_name = {r["name"]: r for r in runes}
    plan = RUNE_PLAN.get(arche_key, {})
    keystone = next((by_name[n] for n in plan.get("keystone", []) if n in by_name), None)
    minors = [by_name[n] for n in plan.get("minors", []) if n in by_name][:4]
    slim = lambda r: {"name": r["name"], "slug": r["slug"], "tree": r.get("tree", ""),
                      "icon": r["icon"], "description": r["description"]}
    return {"keystone": slim(keystone) if keystone else None,
            "minors": [slim(m) for m in minors]}


def optimize_build(name: str, champ_class: str, items: list[dict] | None = None,
                   profiles: dict | None = None, enriched: dict | None = None) -> dict:
    items = items or _load_items()
    profiles = profiles if profiles is not None else _champ_profiles()
    enriched = enriched if enriched is not None else _enriched()
    norm = _normalisers(items)

    arche_key, arche = archetype_for(name, champ_class)
    profile = profiles.get(name)
    school = damage_school(arche_key, champ_class, profile)
    weights = _refined_weights(arche, profile)

    scored = sorted(
        ((score_item(it, weights, arche, school, norm, enriched, arche_key), it)
         for it in items),
        key=lambda x: x[0], reverse=True,
    )

    def fmt(sc, it):
        ev = enriched.get(it["slug"], {})
        return {"name": it["name"], "slug": it["slug"], "cost": it["cost"],
                "score": round(sc, 3), "tags": sorted(_derive_tags(it)),
                "icon": it["icon"], "note": ev.get("note", "")}

    core, boots, enchant, seen = [], None, None, set()

    # greedy fill by score under Wild Rift build rules (coreFor is a score bonus,
    # applied in score_item — so it's deterministic and school-gated)
    for sc, it in scored:
        cat = it["category"]
        if cat in BOOT_CATEGORIES:
            if boots is None:
                boots = fmt(sc, it)
            continue
        if cat in ENCHANT_CATEGORIES:
            if enchant is None:
                enchant = fmt(sc, it)
            continue
        if cat in SUPPORT_CATEGORIES and arche_key != "enchanter":
            continue
        if it["name"] in seen:
            continue
        if len(core) < 5:
            core.append(fmt(sc, it))
            seen.add(it["name"])

    return {
        "champion": name,
        "class": champ_class,
        "archetype": arche_key,
        "damageSchool": school,
        "scalesWith": (profile or {}).get("scalesWith", []),
        "mechanics": (profile or {}).get("mechanics", []),
        "coreItems": core,
        "boots": boots,
        "enchantment": enchant,
        "runes": _recommend_runes(arche_key),
    }


if __name__ == "__main__":
    demo = [("Hecarim", "Bruiser"), ("Jinx", "Marksman"), ("Lux", "Mage"),
            ("Amumu", "Tank"), ("Master Yi", "Assassin"), ("Thresh", "Enchanter"),
            ("Mordekaiser", "Bruiser")]
    items = _load_items()
    profiles = _champ_profiles()
    enriched = _enriched()
    print(f"enrichment: {'loaded ' + str(len(enriched)) + ' items' if enriched else 'NOT FOUND (run enrich_items_llm.py)'}\n")
    for nm, cl in demo:
        b = optimize_build(nm, cl, items, profiles, enriched)
        ks = b["runes"]["keystone"]
        print(f"=== {nm} ({cl} -> {b['archetype']}, {b['damageSchool']}) ===")
        print(f"  boots:  {b['boots']['name'] if b['boots'] else '-'} + "
              f"{b['enchantment']['name'] if b['enchantment'] else '-'}")
        for c in b["coreItems"]:
            note = f"  — {c['note']}" if c["note"] else ""
            print(f"  {c['score']:5.2f}  {c['name']:26}{note}")
        print(f"  keystone: {ks['name'] if ks else '-'} | "
              f"minors: {', '.join(m['name'] for m in b['runes']['minors'])}\n")
