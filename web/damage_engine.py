"""Deterministic Wild Rift damage engine — the lolmath-style core (PoC: Graves).

Given a champion, level, item build, and a target (HP/armor/MR), this computes
the ACTUAL combo burst using the real per-rank ability formulas
(data/champion_formulas.json) and numeric item models (data/item_effects.json),
applying penetration, crit, and item procs. It then answers the only question
that matters for a burst champ: does this build one-shot the target, and by how
much? The optimizer searches item combinations to maximise that burst.

No LLM at runtime — this is pure math on scraped ground-truth numbers.

    python -m web.damage_engine
"""
from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHAMPS = json.loads((ROOT / "data" / "champions_wr.json").read_text(encoding="utf-8"))
FORMULAS = json.loads((ROOT / "data" / "champion_formulas.json").read_text(encoding="utf-8"))
EFFECTS = json.loads((ROOT / "data" / "item_effects.json").read_text(encoding="utf-8"))
ITEMS = {i["slug"]: i for i in json.loads((ROOT / "data" / "items.json").read_text(encoding="utf-8"))}
RULES = json.loads((ROOT / "data" / "item_rules.json").read_text(encoding="utf-8"))
MUTEX = [set(g) for g in RULES.get("mutexGroups", {}).values()]
RUNE_FX = json.loads((ROOT / "data" / "rune_effects.json").read_text(encoding="utf-8"))


def _lvl(rng, level: int) -> float:
    lo, hi = rng
    return lo + (hi - lo) * (level - 1) / 14.0

CHAMP_BY_NAME = {c["name"]: c for c in CHAMPS}
BASE_CRIT_MULT = 1.75  # Wild Rift base critical damage

# --- target presets (level-15-ish) ----------------------------------------
TARGETS = {
    "squishy": {"hp": 2000, "armor": 90, "mr": 50, "bonusHp": 400},
    "bruiser": {"hp": 3200, "armor": 140, "mr": 80, "bonusHp": 1600},
    "tank":    {"hp": 4000, "armor": 200, "mr": 120, "bonusHp": 2600},
}


def champ_ad(name: str, level: int) -> float:
    bs = CHAMP_BY_NAME[name]["baseStats"]["ad"]
    return bs["base"] + bs["perLevel"] * (level - 1)


def aggregate(item_slugs: list[str]) -> dict:
    """Sum the damage-relevant effects of a build."""
    ad = 0.0
    crit = 0.0
    crit_mult = BASE_CRIT_MULT
    flat_pen = 0.0
    pct_pen_factors = []   # multiplicative
    shred = 0.0            # take the max stacking source
    proc_maxhp = 0.0
    first_hit = 0.0
    giant = 0.0
    execute = 0.0
    for s in item_slugs:
        e = EFFECTS.get(s, {})
        if not isinstance(e, dict):
            continue
        ad += e.get("ad", 0)
        crit += e.get("crit", 0)
        crit_mult = max(crit_mult, e.get("critMult", 0))
        flat_pen += e.get("flatPen", 0)
        if e.get("pctPen"):
            pct_pen_factors.append(e["pctPen"])
        shred = max(shred, e.get("armorShredPct", 0))
        proc_maxhp += e.get("procMaxHpPct", 0)
        first_hit += e.get("firstHit", 0)
        giant = max(giant, e.get("giantSlayer", 0))
        execute = max(execute, e.get("executePct", 0))
    crit = min(crit, 1.0)
    pct_pen = 1.0
    for p in pct_pen_factors:
        pct_pen *= (1 - p)
    pct_pen = 1 - pct_pen  # combined % pen
    return {"ad": ad, "crit": crit, "critMult": crit_mult, "flatPen": flat_pen,
            "pctPen": pct_pen, "shred": shred, "procMaxHp": proc_maxhp,
            "firstHit": first_hit, "giant": giant, "execute": execute}


def aggregate_runes(runes: list[str], level: int) -> dict:
    """Fold a rune page into: bonus AD, per-auto on-hit, one-time procs, dmg amp."""
    out = {"bonusAd": 0.0, "onHitFlat": 0.0, "onHitAdRatio": 0.0,
           "procs": [], "ampPct": 0.0}
    ks, mn = RUNE_FX["keystones"], RUNE_FX["minors"]
    for name in runes:
        r = ks.get(name) or mn.get(name)
        if not r:
            continue
        if "bonusAdPerStackRange" in r:  # Conqueror
            out["bonusAd"] += _lvl(r["bonusAdPerStackRange"], level) * r.get("burstStacks", 6)
        out["bonusAd"] += r.get("bonusAdAtStacks", 0)
        if "bonusAdRange" in r:  # Absolute Focus (assume healthy)
            out["bonusAd"] += _lvl(r["bonusAdRange"], level)
        if "onHit" in r:  # Brutal
            out["onHitFlat"] += r["onHit"].get("flat", 0)
            out["onHitAdRatio"] += r["onHit"].get("adRatio", 0)
        if "burstProc" in r:
            p = r["burstProc"]
            if p.get("condition") == "targetBelow50":
                continue  # not applicable to a one-shot from full HP
            flat = _lvl(p["baseRange"], level) if "baseRange" in p else p.get("flat", 0)
            out["procs"].append({"name": name, "flat": flat, "adRatio": p.get("adRatio", 0),
                                 "type": p.get("type", "physical")})
        out["ampPct"] += r.get("ampPct", 0)  # Coup de Grace, First Strike
    return out


def eff_armor(armor: float, agg: dict) -> float:
    a = armor * (1 - agg["shred"])   # % reduction (Black Cleaver)
    a = a * (1 - agg["pctPen"])      # % penetration (Serylda's / Dominik's)
    a = a - agg["flatPen"]           # flat pen (lethality)
    return max(a, 0.0)


def combo_damage(name: str, level: int, item_slugs: list[str], target: dict,
                 runes: list[str] | None = None) -> dict:
    f = FORMULAS[name]
    agg = aggregate(item_slugs)
    ragg = aggregate_runes(runes or [], level)
    bonus_ad = agg["ad"] + ragg["bonusAd"]           # AD from items + runes
    total_ad = champ_ad(name, level) + bonus_ad
    armor = eff_armor(target["armor"], agg)
    phys_mult = 100 / (100 + armor)
    mr = max(target["mr"], 0.0)
    magic_mult = 100 / (100 + mr)
    # Giant Slayer: up to `giant` bonus vs enemy bonus HP (full at 1200 bonus HP)
    giant_bonus = 1 + agg["giant"] * min(1.0, target["bonusHp"] / 1200)
    # expected crit multiplier on autos
    auto_crit = 1 + agg["crit"] * (agg["critMult"] - 1)

    parts: list[tuple[str, float]] = []
    for step in f["combo"]:
        if step == "auto":
            raw = f["auto"]["adRatio"] * total_ad * auto_crit
            dmg = raw * phys_mult * giant_bonus
            if agg["firstHit"]:
                dmg += agg["firstHit"] * phys_mult
            if ragg["onHitFlat"] or ragg["onHitAdRatio"]:  # Brutal
                dmg += (ragg["onHitFlat"] + ragg["onHitAdRatio"] * bonus_ad) * phys_mult
            parts.append(("Auto (shotgun)", dmg))
        else:
            ab = f["abilities"][step]
            rank = f["abilityLevels"].get(step, ab["maxRank"]) - 1
            sub = 0.0
            for inst in ab["instances"]:
                ratio = 0.0
                if "ad" in inst:
                    r = inst["ad"]
                    ratio_val = r[rank] if isinstance(r, list) else r
                    base = inst["base"][rank] + ratio_val * total_ad
                    base *= phys_mult * giant_bonus
                elif "ap" in inst:
                    base = inst["base"][rank]  # no AP items in an AD build
                    base *= magic_mult
                else:
                    base = inst["base"][rank]
                sub += base
            parts.append((f"{step} {ab['name']}", sub))
    # Eclipse-style % max-HP proc (once, physical)
    if agg["procMaxHp"]:
        parts.append(("Eclipse proc (%maxHP)", agg["procMaxHp"] * target["hp"] * phys_mult))
    # rune burst procs (Electrocute physical -> armor applies; Sudden Impact true -> ignores)
    for p in ragg["procs"]:
        raw = p["flat"] + p["adRatio"] * bonus_ad
        dmg = raw * (phys_mult if p["type"] == "physical" else 1.0)
        parts.append((f"Rune: {p['name']}", dmg))

    total = sum(p for _, p in parts) * (1 + ragg["ampPct"])  # Coup de Grace / First Strike
    need = target["hp"] * (1 - agg["execute"])  # Collector execute finishes the kill
    return {"total": total, "parts": parts, "targetHp": target["hp"],
            "needed": need, "oneshot": total >= need, "effArmor": armor, "totalAd": total_ad}


def is_legal(item_slugs) -> bool:
    """Reject builds with >1 item from any Wild Rift mutex group."""
    s = set(item_slugs)
    return all(len(s & group) <= 1 for group in MUTEX)


def optimize(name: str, level: int, target: dict, pool: list[str], k: int = 5, top: int = 3):
    results = []
    for combo in combinations(pool, k):
        if not is_legal(combo):
            continue
        d = combo_damage(name, level, list(combo), target)
        results.append((d["total"], list(combo), d))
    results.sort(key=lambda x: x[0], reverse=True)
    return results[:top]


if __name__ == "__main__":
    name, level = "Graves", 15
    tgt = TARGETS["squishy"]
    pool = [s for s in EFFECTS if isinstance(EFFECTS[s], dict) and EFFECTS[s].get("ad")]

    print(f"=== {name} @ level {level}  vs {tgt['hp']} HP / {tgt['armor']} armor squishy ===\n")

    # 1) score a specific build (the LLM's one-shot build for Graves)
    build = ["eclipse", "youmuus-ghostblade", "seryldas-grudge", "the-collector", "infinity-edge"]
    d = combo_damage(name, level, build, tgt)
    print("Build:", ", ".join(ITEMS[s]["name"] for s in build))
    print(f"  total AD {d['totalAd']:.0f} | enemy armor {tgt['armor']}->{d['effArmor']:.0f} after pen")
    for label, dmg in d["parts"]:
        print(f"    {label:26} {dmg:7.0f}")
    print(f"  --------------------------------")
    print(f"  COMBO BURST (Q+auto+R):   {d['total']:7.0f}")
    print(f"  needs {d['needed']:.0f} to kill  ->  {'ONE-SHOT ✅  (+%.0f overkill)' % (d['total']-d['needed']) if d['oneshot'] else 'NOT a one-shot ❌ (short %.0f)' % (d['needed']-d['total'])}")

    # 2) let the engine FIND the max-burst 5-item build
    print(f"\n=== max-burst builds the engine computed (from {len(pool)} candidate items) ===")
    for rank, (total, combo, dd) in enumerate(optimize(name, level, tgt, pool), 1):
        tag = "one-shots" if dd["oneshot"] else "no 1shot"
        print(f"  {rank}. {total:6.0f}  [{tag}]  " + " + ".join(ITEMS[s]["name"] for s in combo))
