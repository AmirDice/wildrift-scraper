"""Add Sylas (released in 7.3f, 12 November 2026) to the hand-kept data files.

His kit, base stats and abilities come from wildriftfire via
`python -m scripts.scrape_champions --only sylas --refresh`, and his fight
formulas from `python -m scripts.extract_formulas --only Sylas`. This script
fills what neither of those writes, all from the same wildriftfire guide
(data/wrf_cache/guide_sylas.html), at the owner's instruction to use
wildriftfire rather than wr-meta:

    champion_builds.json + builds.json   the guide's item build, runes and
        summoners, as a "Standard" starter build. No ladder rates and no
        model-confidence score are invented; there is no ladder data on him yet.
    champion_combos.json (both copies)   the rotation the formula extractor
        returned (the combo model's provider was out of quota), pinned with
        medium confidence.
    hard_cc_durations.json   Abduct: 0.5s stun + 0.5s knock-up = 1.0s.

Hijack (stealing an enemy's ultimate) cannot be simulated, so his ultimate
deals no modelled damage; ability_formulas.json says so in its unmodeled notes.

Offline and idempotent. Run after the two commands above:
    python -m scripts.add_sylas
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUIDE = "https://www.wildriftfire.com/guide/sylas"
WRF = "https://www.wildriftfire.com/images/runes/"
DD = "https://ddragon.leagueoflegends.com/cdn/16.11.1/img/spell/"


def _indent_of(raw: str):
    m = re.match(r"\{\n( +)\"", raw)
    return len(m.group(1)) if m else None


def read(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def write_like(rel, value):
    """Rewrite a JSON file keeping its line endings, indent and final newline."""
    path = ROOT / rel
    raw = path.read_bytes().decode("utf-8")
    crlf = "\r\n" in raw
    norm = raw.replace("\r\n", "\n")
    out = json.dumps(value, ensure_ascii=False, indent=_indent_of(norm))
    if norm.endswith("\n"):
        out += "\n"
    if crlf:
        out = out.replace("\n", "\r\n")
    path.write_bytes(out.encode("utf-8"))


def rune(name, slug, tree=None, reason=""):
    r = {"name": name, "slug": slug}
    if tree:
        r["tree"] = tree
    r["icon"] = WRF + slug + ".png"
    if reason:
        r["reason"] = reason
    return r


def build_record() -> dict:
    items = read("web-next/src/data/engine.json")["items"]

    def item(slug):
        meta = items[slug]
        return {"slug": slug, "name": meta["name"], "cost": meta["cost"],
                "icon": meta.get("icon", f"/items/{slug}.webp")}

    runes = {
        "keystone": rune("Electrocute", "electrocute",
                         reason="Abduct, Chain Lash and Kingslayer land three hits in one trade."),
        "primaryTree": "Domination",
        "treeMinors": [
            rune("Sudden Impact", "sudden-impact", "Domination", "Abscond and Kingslayer are both dashes."),
            rune("Chain Assault", "chain-assault", "Domination"),
            rune("Eyeball Collector", "eyeball-collector", "Domination"),
        ],
        "flexMinor": rune("Legend: Haste", "legend-haste", "Precision"),
    }
    guide_meta = read("data/wrf_guide_meta.json")
    guide_meta = guide_meta.get("champions", guide_meta)
    situational = [{"when": s["when"], "items": [item(x) for x in s["items"] if x in items]}
                   for s in (guide_meta.get("Sylas") or {}).get("situational", [])]
    standard = {
        "summary": "wildriftfire's guide build. Fight estimates cover his own kit only: "
                   "Hijack casts the enemy's ultimate, which the engine cannot simulate.",
        "label": "Standard", "pathLabel": "Magic",
        "coreBuild": [item(s) for s in ("lich-bane", "infinity-orb", "rabadons-deathcap",
                                        "void-staff", "zhonyas-hourglass")],
        "boots": item("boots-of-mana"), "bootsEarly": item("boots-of-mana"), "bootsUpgradeAfter": 2,
        "enchantment": None, "situational": situational, "runes": runes,
        "summoners": [{"name": "Flash", "icon": DD + "SummonerFlash.png"},
                      {"name": "Ignite", "icon": DD + "SummonerDot.png"}],
    }
    rec = {"name": "Sylas", "class": "Mage", "role": "Mid", "damageProfile": "ap-burst",
           "canOneshot": False, "source": GUIDE, "variants": ["standard"],
           "builds": {"standard": standard},
           "synergyNotes": ["Petricite Burst rewards weaving an attack after every ability, "
                            "which is why the guide opens Lich Bane.",
                            "Hijack copies the enemy's ultimate; its value depends on the "
                            "enemy team and is not part of any number here."]}
    from web import fight_engine as fe
    slugs = [i["slug"] for i in standard["coreBuild"]] + [standard["boots"]["slug"]]
    names = ([runes["keystone"]["name"]] + [r["name"] for r in runes["treeMinors"]]
             + [runes["flexMinor"]["name"]])
    standard["analysis"] = fe.analyze_build("Sylas", slugs, names, 15)
    return rec


def main():
    rec = build_record()
    for rel in ("data/champion_builds.json", "web-next/src/data/builds.json"):
        data = read(rel)
        data["Sylas"] = rec
        write_like(rel, data)

    combo = {"combo": ["3", "auto", "1", "auto", "2", "auto", "4", "auto"], "confidence": "medium",
             "why": "Abscond/Abduct in, Chain Lash, Kingslayer, weaving a Petricite Burst attack "
                    "after each. Hijack is listed for timing only: the stolen ultimate is not modelled."}
    for rel in ("data/champion_combos.json", "web-next/src/data/champion_combos.json"):
        data = read(rel)
        data["champions"]["Sylas"] = combo
        write_like(rel, data)

    cc = read("data/hard_cc_durations.json")
    cc["champions"]["Sylas"] = 1.0
    write_like("data/hard_cc_durations.json", cc)

    # Draft kit: `generate_draft_kit --only Sylas --force` output of
    # 2026-11-17 (gemini-3.6-flash), pinned here so this script stays offline.
    kit = read("data/champion_draft_kit.json")
    kit["champions"]["Sylas"] = {"frontline": 0.4, "peel": 0.1, "engage": 0.45, "antiDive": 0.25,
                                 "antiTank": 0.15, "disruption": 0.2, "disengage": 0.1,
                                 "sustained": 0.55, "magic": 0.95, "physical": 0.05,
                                 "globalPressure": 0.0}
    # Identity: HAND-WRITTEN in the needs schema every stored card uses
    # (scripts/merge_champion_identity.py). generate_champion_identity still
    # emits the OLD item-naming schema, which that merge removed on purpose
    # because the build model recited the named items, so its card is not used.
    write_like("data/champion_draft_kit.json", kit)
    ident = read("data/champion_identity.json")
    ident["champions"]["Sylas"] = {
        "roles": ["Mid"], "classes": ["Mage", "Fighter"],
        "identitySummary": "Close-range AP skirmisher who dives with Abscond/Abduct, heals through "
                           "Kingslayer and weaves attacks between spells. Weak when his dashes are down.",
        "combat": {"range": "short_ranged", "engagement": "high",
                   "playstyle": ["dive", "skirmishing", "teamfight"], "power_pattern": "mid_game",
                   "primary_win_condition": "teamfighting"},
        "teamComp": {"needs_frontline": True, "needs_peel": False, "benefits_from_engage": True,
                     "benefits_from_cc": True, "primary_team_role": "playmaker"},
        "itemizationNeeds": {"primary_damage": "magic",
                             "scaling_priority": ["ability_power", "penetration", "ability_haste"],
                             "defensive_priority": ["armor", "magic_resistance"],
                             "situational_needs": ["defensive_item_vs_burst", "penetration_vs_resists",
                                                   "anti_heal_vs_healing"]},
        "hardLimits": {"neverArchetypes": [{"path": "AD Crit On-Hit",
                                            "why": "Every ability scales with AP; only Petricite Burst's "
                                                   "primary hit can crit, and Hijack converts AD into AP."}],
                       "avoidStats": ["ad", "crit", "lethality", "armor_pen", "lifesteal"]},
        "statPriorities": ["ap", "magic_pen", "ability_haste", "hp"],
        "_source": "hand-written 2026-11-17 from the wildriftfire kit and guide",
    }
    write_like("data/champion_identity.json", ident)
    print("Sylas: builds, combo, hard CC, draft kit and identity written")


if __name__ == "__main__":
    main()
