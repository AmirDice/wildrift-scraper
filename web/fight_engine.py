"""Deterministic Wild Rift fight engine — generalized from the Graves PoC.

Given a champion, level, items and runes, simulates a rotation over a fight
window (abilities on cooldown + autos at attack speed, with penetration, crit,
spellblade, on-hits, procs and amps) against reference targets, and computes:

    burst3   damage in a 3s all-in vs a squishy
    dps8     sustained damage per second over 8s vs a bruiser
    ttk      seconds to kill the squishy (rotation solved iteratively)
    ehp      effective HP vs mixed damage (incl. lifeline shields and DR)
    sustain  self-healing over the 8s window (vamp etc.)
    score    variant-weighted fight value: kill fast AND live to kill more

Data in:  data/ability_formulas.json   (LLM-extracted, number-grounded)
          data/item_engine.json (+ overrides), data/items.json (stats)
          data/rune_effects.json, data/champions_wr.json (base stats)

No LLM at runtime — pure math on transcribed numbers.

    python -m web.fight_engine            # demo: score the generated builds
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str):
    p = ROOT / "data" / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


CHAMPS = {c["name"]: c for c in _load("champions_wr.json")}
FORMULAS = _load("ability_formulas.json")
ITEMS = {i["slug"]: i for i in _load("items.json")}
ENGINE_FX = _load("item_engine.json")
for slug, fx in _load("item_engine_overrides.json").items():
    if isinstance(fx, dict):
        ENGINE_FX.setdefault(slug, {}).update({k: v for k, v in fx.items() if not k.startswith("_")})
RUNE_FX = _load("rune_effects.json")
RUNE_ENGINE = _load("rune_engine.json")  # LLM-extracted, used when not hand-curated
GUIDE_META = _load("wrf_guide_meta.json")  # real skill orders from wildriftfire

BASE_CRIT_MULT = 1.75
BASE_MANA_ASSUMED = 500.0   # champion base mana is not scraped yet (flagged gap)
AS_CAP = 2.5
SPELLBLADE_CD = 1.5

# Reference targets. The squishy is a REAL champion with zero defensive tools
# in her kit (Ashe: no shields, heals, armor or damage reduction anywhere),
# computed from scraped base stats at the sim's level — a full-glass crit build
# adds ~no HP, so bonusHp stays 0 and giant-slayer effects correctly do nothing.
SQUISHY_REF = "Ashe"


def target_squishy(level: int) -> dict:
    c = CHAMPS.get(SQUISHY_REF)
    if not c:
        return {"hp": 2200, "armor": 85, "mr": 45, "bonusHp": 0}
    bs = c["baseStats"]

    def v(k, d=0.0):
        s = bs.get(k)
        return (s["base"] + s["perLevel"] * (level - 1)) if s else d

    return {"hp": v("hp", 2200), "armor": v("armor", 85), "mr": v("mr", 45), "bonusHp": 0}


TARGETS = {
    "squishy": target_squishy(13),  # kept for module-level compat
    "bruiser": {"hp": 3400, "armor": 130, "mr": 85, "bonusHp": 1700},
}

# offense/defense weights per build variant: the "kill fast vs live to kill
# more" dial. Tunable — this is the experiment knob.
VARIANT_WEIGHTS = {
    "oneshot": (0.85, 0.15), "burst": (0.80, 0.20), "damage": (0.70, 0.30),
    "crit": (0.70, 0.30), "poke": (0.70, 0.30), "battlemage": (0.55, 0.45),
    "balanced": (0.55, 0.45), "tanky": (0.30, 0.70), "utility": (0.25, 0.75),
}
# offense normalization: burst-flavoured variants score on the 3s all-in,
# sustained ones on 8s DPS.
BURSTY = {"oneshot", "burst", "poke", "crit"}
REF_BURST, REF_DPS, REF_DEF = 2400.0, 700.0, 7000.0

# Gold reality: WR games run 15-20 min, so a build's value is dominated by what
# you can actually afford at the mid-game fight. Role GPM assumptions (tunable;
# junglers farm fastest, supports least).
ROLE_GPM = {"Jungle": 850, "Mid": 750, "Dragon": 780, "Baron": 700, "Support": 550}
MID_MINUTE = 15          # the "most games are decided around here" checkpoint
MID_LEVEL, FULL_LEVEL = 13, 15
MID_WEIGHT, FULL_WEIGHT = 0.6, 0.4  # combined score favours the 15-min reality


def kit_adjust(name: str) -> float:
    """Champion-specific shift of weight toward offense (positive) or defense.

    A kit with escape tools (stealth/untargetability/dashes) or innate defenses
    (kit shields/heals, high HP growth) buys the right to build glassier —
    Kha'Zix/Evelynn style. Immobile kits shift the other way. Derived from
    scraped kit data, capped at +/-0.12.
    """
    c = CHAMPS.get(name)
    if not c:
        return 0.0
    full = " ".join((a.get("text") or "").lower() for a in c.get("abilities", []))
    mech = set(c.get("mechanics") or [])
    shift = 0.0
    if any(k in full for k in ("invisib", "camouflage", "stealth", "untargetable")):
        shift += 0.06
    if "dash" in mech:
        shift += 0.03
    if "shield" in mech or "heal" in mech:
        shift += 0.02
    if c.get("baseStats", {}).get("hp", {}).get("perLevel", 0) >= 125:
        shift += 0.02
    if "dash" not in mech and not any(k in full for k in ("invisib", "stealth", "untargetable")):
        shift -= 0.05
    return max(-0.12, min(0.12, shift))


def affordable(item_slugs: list[str], gold: float) -> list[str]:
    """Items actually buyable by `gold`, in build order (boots slot after item 1)."""
    order = list(item_slugs)
    if len(order) >= 2:  # boots (appended last by caller) move to 2nd purchase
        order = [order[0], order[-1]] + order[1:-1]
    out, spent = [], 0.0
    for slug in order:
        cost = (ITEMS.get(slug) or {}).get("cost", 0) or 0
        if spent + cost > gold:
            break
        spent += cost
        out.append(slug)
    return out


def _lvl_range(v, level: int) -> float:
    if isinstance(v, dict) and "lvlRange" in v:
        lo, hi = v["lvlRange"]
        return lo + (hi - lo) * (level - 1) / 14.0
    return float(v)


def _rank_val(arr, rank: int) -> float:
    if isinstance(arr, (int, float)):
        return float(arr)
    if not arr:
        return 0.0
    return float(arr[min(rank, len(arr) - 1)])


def resolve_stats(name: str, level: int, item_slugs: list[str],
                  rune_names: list[str] | None = None) -> dict:
    """Champion base stats + item stats + engine passives + kit steroids."""
    bs = CHAMPS[name]["baseStats"]

    def base(k, default=0.0):
        s = bs.get(k)
        return (s["base"] + s["perLevel"] * (level - 1)) if s else default

    st = {
        "baseAd": base("ad", 60), "bonusAd": 0.0, "ap": 0.0,
        "hp": base("hp", 1800), "bonusHp": 0.0,
        "armor": base("armor", 60), "mr": base("mr", 45),
        "baseAsPct": 0.0,  # bonus attack speed %
        "baseAs": bs.get("attackSpeed", {}).get("base", 0.75) or 0.75,
        "crit": 0.0, "critMult": BASE_CRIT_MULT,
        "haste": 0.0, "mana": BASE_MANA_ASSUMED,
        "flatPen": 0.0, "pctPenFactors": [], "flatMagicPen": 0.0, "pctMagicPen": 0.0,
        "baseMs": bs.get("moveSpeed", {}).get("base", 330) or 330, "bonusMs": 0.0,
        "abilityAmp": 0.0, "damageAmp": 0.0, "giant": 0.0, "execute": 0.0,
        "spellbladeBaseAdPct": 0.0, "spellbladePctMaxHp": 0.0,
        "onHitPhys": 0.0, "onHitMagic": 0.0, "onHitPctCurrentHp": 0.0, "onHitPctMaxHp": 0.0,
        "burstProcs": [], "dotDps": 0.0, "procMaxHpPct": 0.0, "firstHit": 0.0,
        "armorShred": 0.0, "vamp": 0.0, "healOnHit": 0.0,
        "shield": 0.0, "shieldPctBonusHp": 0.0, "shieldPctMaxHp": 0.0, "dr": 0.0,
    }

    for slug in item_slugs:
        it = ITEMS.get(slug)
        if not it:
            continue
        for k, v in it["stats"].items():
            val, pct = v["value"], v["percent"]
            if k == "ad":
                st["bonusAd"] += val
            elif k == "ap":
                st["ap"] += val
            elif k == "hp":
                st["hp"] += val; st["bonusHp"] += val
            elif k == "armor":
                st["armor"] += val
            elif k == "mr":
                st["mr"] += val
            elif k == "attackSpeed":
                st["baseAsPct"] += val
            elif k == "crit":
                st["crit"] += val / 100.0
            elif k == "abilityHaste":
                st["haste"] += val
            elif k == "mana":
                st["mana"] += val
            elif k == "magicPen":
                if pct:
                    st["pctMagicPen"] = 1 - (1 - st["pctMagicPen"]) * (1 - val / 100.0)
                else:
                    st["flatMagicPen"] += val
            elif k == "physicalPen":
                st["flatPen"] += val
            elif k == "moveSpeed":
                if pct:
                    st["bonusMs"] += st["baseMs"] * val / 100.0
                else:
                    st["bonusMs"] += val

        fx = ENGINE_FX.get(slug) or {}
        g = lambda k: _lvl_range(fx[k], level) if k in fx else 0.0  # noqa: E731
        st["flatPen"] += g("flatPen")
        if fx.get("pctPen"):
            st["pctPenFactors"].append(g("pctPen") / 100.0)
        st["armorShred"] = max(st["armorShred"], g("armorShredPct") / 100.0)
        st["critMult"] = max(st["critMult"], float(fx.get("critMult", 0)) or 0)
        st["abilityAmp"] += g("abilityAmpPct") / 100.0
        st["damageAmp"] += g("damageAmpPct") / 100.0
        st["giant"] = max(st["giant"], g("giantSlayerPct") / 100.0)
        st["execute"] = max(st["execute"], g("executePct") / 100.0)
        st["spellbladeBaseAdPct"] = max(st["spellbladeBaseAdPct"], g("spellbladeBaseAdPct"))
        st["spellbladePctMaxHp"] = max(st["spellbladePctMaxHp"], g("spellbladePctMaxHp"))
        st["onHitPhys"] += g("onHitFlatPhys")
        st["onHitMagic"] += g("onHitFlatMagic")
        st["onHitPctCurrentHp"] += g("onHitPctCurrentHp") / 100.0
        st["onHitPctMaxHp"] += g("onHitPctMaxHp") / 100.0
        st["procMaxHpPct"] += g("procMaxHpPct") / 100.0
        st["firstHit"] += g("firstHit")
        if fx.get("burstProcFlat") or fx.get("burstProcApPct"):
            st["burstProcs"].append((g("burstProcFlat"), g("burstProcApPct") / 100.0))
        st["dotDps"] += g("dotDps")
        st["vamp"] += (g("physVampPct") + g("omnivampPct") + g("lifestealPct")) / 100.0
        st["healOnHit"] += g("healOnHitFlat")
        st["shield"] += g("shieldFlat")
        st["shieldPctBonusHp"] += g("shieldPctBonusHp") / 100.0
        st["shieldPctMaxHp"] += g("shieldPctMaxHp") / 100.0
        st["dr"] = max(st["dr"], g("drPct") / 100.0)
        st["adFlatPassive"] = g("adFlatPassive")
        st["bonusAd"] += g("adFlatPassive")
        st["ap"] += g("apFlatPassive")
        st["haste"] += g("hasteFlatPassive")
        st["hp"] += g("hpFlatPassive"); st["bonusHp"] += g("hpFlatPassive")
        st["bonusMs"] += g("msFlat") + st["baseMs"] * g("msPct") / 100.0
        st["bonusAd"] += g("adFromManaPct") / 100.0 * st["mana"]
        st["ap"] += g("apFromBonusHpPct") / 100.0 * st["bonusHp"]

    # runes (numeric models: bonus AD, on-hit, procs, amp, move speed, haste)
    ragg = {"bonusAd": 0.0, "onHitFlat": 0.0, "onHitAdRatio": 0.0, "procs": [], "ampPct": 0.0}
    ms_amp = 0.0
    ks, mn = RUNE_FX.get("keystones", {}), RUNE_FX.get("minors", {})
    for rn in rune_names or []:
        r = ks.get(rn) or mn.get(rn)
        if not r:
            # fall back to the LLM-extracted numeric model
            fx = RUNE_ENGINE.get(rn) or {}
            g = lambda k: _lvl_range(fx[k], level) if k in fx else 0.0  # noqa: E731
            adaptive_ad, adaptive_ap = g("adaptiveAd"), g("adaptiveAp")
            if adaptive_ad or adaptive_ap:  # adaptive: follow the build's dominant stat
                if st["ap"] >= st["bonusAd"]:
                    st["ap"] += adaptive_ap
                else:
                    st["bonusAd"] += adaptive_ad
            st["bonusAd"] += g("bonusAd")
            st["ap"] += g("bonusAp")
            st["haste"] += g("hasteFlat")
            st["hp"] += g("hpFlat"); st["bonusHp"] += g("hpFlat")
            st["armor"] += g("armorFlat")
            st["mr"] += g("mrFlat")
            ragg["onHitFlat"] += g("onHitFlat")
            ragg["ampPct"] += g("ampPct") / 100.0
            if fx.get("burstProcFlat") or fx.get("burstProcApRatio") or fx.get("burstProcAdRatio"):
                ragg["procs"].append((g("burstProcFlat"), g("burstProcAdRatio") / 100.0,
                                      fx.get("burstProcType", "magic")))
            continue
        st["bonusMs"] += st["baseMs"] * r.get("msPctAvg", 0) / 100.0
        st["haste"] += r.get("hasteFlat", 0)
        ms_amp += r.get("msAmpPct", 0) / 100.0
        if "bonusAdPerStackRange" in r:
            lo, hi = r["bonusAdPerStackRange"]
            ragg["bonusAd"] += (lo + (hi - lo) * (level - 1) / 14.0) * r.get("burstStacks", 6)
        ragg["bonusAd"] += r.get("bonusAdAtStacks", 0)
        if "bonusAdRange" in r:
            lo, hi = r["bonusAdRange"]
            ragg["bonusAd"] += lo + (hi - lo) * (level - 1) / 14.0
        if "onHit" in r:
            ragg["onHitFlat"] += r["onHit"].get("flat", 0)
            ragg["onHitAdRatio"] += r["onHit"].get("adRatio", 0)
        if "burstProc" in r:
            p = r["burstProc"]
            if p.get("condition") != "targetBelow50":
                lo, hi = p.get("baseRange", [p.get("flat", 0)] * 2)
                ragg["procs"].append((lo + (hi - lo) * (level - 1) / 14.0,
                                      p.get("adRatio", 0), p.get("type", "physical")))
        ragg["ampPct"] += r.get("ampPct", 0)
    st["bonusAd"] += ragg["bonusAd"]
    st["runeOnHitFlat"] = ragg["onHitFlat"] + ragg["onHitAdRatio"] * st["bonusAd"]
    st["runeProcs"] = ragg["procs"]
    st["damageAmp"] += ragg["ampPct"]
    st["bonusMs"] *= 1 + ms_amp  # Celerity amplifies all MS bonuses

    # kit steroids (max rank), incl. conversions like Warpath bonusMS -> AD
    f = FORMULAS.get(name, {}).get("abilities", {})
    for ab in f.values():
        for s in ab.get("steroids") or []:
            stat = s.get("stat")
            pct = _rank_val(s.get("pct"), 3) if s.get("pct") is not None else 0.0
            if s.get("from") == "bonusMs" and stat == "ad" and pct:
                continue  # applied after MS totals below
            if stat == "attackSpeed":
                st["baseAsPct"] += pct or _rank_val(s.get("flat"), 3)
            elif stat == "ad" and s.get("flat"):
                st["bonusAd"] += _rank_val(s["flat"], 3)
            elif stat == "moveSpeed" and pct:
                st["bonusMs"] += st["baseMs"] * pct / 100.0 * 0.5  # avg uptime
            elif stat in ("armor", "mr") and s.get("flat"):
                st[stat] += _rank_val(s["flat"], 3)
    for ab in f.values():  # conversions last, after all MS sources counted
        for s in ab.get("steroids") or []:
            if s.get("from") == "bonusMs" and s.get("stat") == "ad" and s.get("pct") is not None:
                st["bonusAd"] += st["bonusMs"] * _rank_val(s["pct"], 3) / 100.0

    st["ad"] = st["baseAd"] + st["bonusAd"]
    st["as"] = min(st["baseAs"] * (1 + st["baseAsPct"] / 100.0), AS_CAP)
    st["crit"] = min(st["crit"], 1.0)
    pct_pen = 1.0
    for p in st["pctPenFactors"]:
        pct_pen *= (1 - p)
    st["pctPen"] = 1 - pct_pen
    return st


def _mults(st: dict, target: dict) -> tuple[float, float]:
    armor = target["armor"] * (1 - st["armorShred"])
    armor = armor * (1 - st["pctPen"]) - st["flatPen"]
    mr = target["mr"] * (1 - st["pctMagicPen"]) - st["flatMagicPen"]
    return 100 / (100 + max(armor, 0)), 100 / (100 + max(mr, 0))


def rotation(name: str, st: dict, target: dict, window: float, level: int = 13) -> dict:
    """Damage dealt over `window` seconds: abilities on cooldown + autos."""
    f = FORMULAS.get(name, {}).get("abilities", {})
    phys_m, magic_m = _mults(st, target)
    giant = 1 + st["giant"] * min(1.0, target["bonusHp"] / 1700)
    crit_ev = 1 + st["crit"] * (st["critMult"] - 1)
    haste_m = 100 / (100 + st["haste"])

    total = 0.0
    parts: list[tuple[str, float]] = []
    casts_total = 0

    def comp_dmg(comp, rank) -> float:
        base = _rank_val(comp.get("base"), rank)
        if comp.get("when") == "dot total" and comp.get("durationS"):
            base *= float(comp["durationS"])
        val = base
        for r in comp.get("ratios") or []:
            stat, pct = r.get("stat"), _rank_val(r.get("pct", 0), rank) / 100.0
            src = {"ad": st["ad"], "bonusAd": st["bonusAd"], "ap": st["ap"],
                   "targetMaxHp": target["hp"], "targetCurrentHp": target["hp"] * 0.7,
                   "targetMissingHp": target["hp"] * 0.3, "ownMaxHp": st["hp"],
                   "ownBonusHp": st["bonusHp"], "armor": st["armor"], "mr": st["mr"],
                   "bonusMs": st["bonusMs"], "bonusArmor": 0, "bonusMr": 0}.get(stat, 0)
            val += pct * src
        val *= int(comp.get("hits", 1) or 1)
        m = {"physical": phys_m, "magic": magic_m, "true": 1.0}[comp["type"]]
        return val * m * (giant if comp["type"] == "physical" else 1.0)

    per_auto_comps = []
    # Skill-order realism: prefer the REAL recommended order scraped from the
    # guide (which levels each ability gets points at); fall back to a damage-
    # priority heuristic (two maxed + one rank 2 at level 13).
    basic_slots = [s for s in ("1", "2", "3") if s in f]
    so = (GUIDE_META.get(name) or {}).get("skillOrder") or {}
    if so:
        rank_of = {s: max(0, sum(1 for lv in so.get(s, []) if lv <= level) - 1)
                   for s in basic_slots}
    elif level >= 14:
        rank_of = {s: 3 for s in basic_slots}
    else:
        def _max_rank_dmg(slot):
            comps = [c for c in f[slot].get("damage") or [] if not c.get("alt")]
            return sum(comp_dmg(c, 3) for c in comps)
        prio = sorted(basic_slots, key=_max_rank_dmg, reverse=True)
        rank_of = {s: (3 if i < 2 else 1) for i, s in enumerate(prio)}
    rank_of["4"] = 2 if level >= 13 else 1  # ult ranks at 5/9/13

    # Short windows follow the champion's actual all-in COMBO sequence when one
    # is authored (each action ~0.45s); longer windows use the cooldown rotation.
    combo_seq = FORMULAS.get(name, {}).get("combo") or []
    if window <= 4.0 and combo_seq:
        budget = max(1, int(window / 0.45))
        seq = combo_seq[:budget]
        n_autos_seq = sum(1 for a in seq if a == "auto")
        for slot in seq:
            if slot == "auto" or slot not in f:
                continue
            comps = [c for c in f[slot].get("damage") or []
                     if not c.get("alt") and c.get("when") != "per auto"]
            per_auto_comps += [(c, slot) for c in f[slot].get("damage") or []
                               if not c.get("alt") and c.get("when") == "per auto"
                               and (c, slot) not in per_auto_comps]
            rank = 2 if slot == "4" else 3
            d = sum(comp_dmg(c, rank) for c in comps) * (1 + st["abilityAmp"])
            parts.append((f"[{slot}] {f[slot].get('name', slot)}", d))
            total += d
            casts_total += 1
        n_autos = max(n_autos_seq, int(window * st["as"] * 0.5))
        auto = st["ad"] * crit_ev * phys_m * giant
        auto += st["onHitPhys"] * phys_m + st["onHitMagic"] * magic_m
        auto += (st["onHitPctCurrentHp"] * target["hp"] * 0.7
                 + st["onHitPctMaxHp"] * target["hp"]) * phys_m
        auto += st["runeOnHitFlat"] * phys_m
        for comp, _slot in per_auto_comps:
            auto += comp_dmg(comp, 3) / max(int(comp.get("hits", 1) or 1), 1)
        total += auto * n_autos
        parts.append((f"autos x{n_autos}", auto * n_autos))
        if st["spellbladeBaseAdPct"] or st["spellbladePctMaxHp"]:
            procs = min(casts_total, n_autos, 1 + int(window / SPELLBLADE_CD))
            d = (st["spellbladeBaseAdPct"] / 100.0 * st["baseAd"]
                 + st["spellbladePctMaxHp"] / 100.0 * target["hp"]) * phys_m * procs
            parts.append((f"spellblade x{procs}", d))
            total += d
        once = st["firstHit"] * phys_m + st["procMaxHpPct"] * target["hp"] * phys_m
        for flat, ap_pct, in [(p[0], p[1]) for p in st["runeProcs"]]:
            once += (flat + ap_pct * st["bonusAd"]) * phys_m
        for flat, ap_r in st["burstProcs"]:
            once += (flat + ap_r * st["ap"]) * magic_m
        if once:
            parts.append(("procs", once))
            total += once
        if st["dotDps"]:
            total += st["dotDps"] * window * magic_m
        return {"total": total * (1 + st["damageAmp"]), "parts": parts,
                "nAutos": n_autos}

    # Casting takes time: budget total ability casts by a ~0.45s action time so a
    # "3s burst" is a real combo, not an infinite instantaneous rotation.
    cast_budget = max(1, int(window / 0.45))
    for slot, ab in sorted(f.items(), key=lambda kv: kv[0] != "4"):  # ult first
        comps = [c for c in ab.get("damage") or [] if not c.get("alt")]
        dmg_comps = [c for c in comps if c.get("when") != "per auto"]
        per_auto_comps += [(c, slot) for c in comps if c.get("when") == "per auto"]
        if not dmg_comps or cast_budget <= 0:
            continue
        cds = ab.get("cooldowns") or []
        rank = rank_of.get(slot, 3)
        cd_idx = min(rank, len(cds) - 1) if cds else 0
        cd = (cds[cd_idx] if cds else 8.0) * haste_m
        casts = 1 + int(window // max(cd, 0.75)) if cd else 1
        if slot == "4":
            casts = 1  # one ult per fight window
        casts = min(casts, cast_budget)
        cast_budget -= casts
        casts_total += casts
        d = sum(comp_dmg(c, rank) for c in dmg_comps) * casts * (1 + st["abilityAmp"])
        parts.append((f"[{slot}] {ab.get('name', slot)} x{casts}", d))
        total += d

    # autos
    n_autos = max(1, int(window * st["as"]))
    auto = st["ad"] * crit_ev * phys_m * giant
    auto += st["onHitPhys"] * phys_m + st["onHitMagic"] * magic_m
    auto += (st["onHitPctCurrentHp"] * target["hp"] * 0.7 + st["onHitPctMaxHp"] * target["hp"]) * phys_m
    auto += st["runeOnHitFlat"] * phys_m
    for comp, _slot in per_auto_comps:  # empowered-auto kit components
        auto += comp_dmg(comp, 3) / max(int(comp.get("hits", 1) or 1), 1)
    d_autos = auto * n_autos
    parts.append((f"autos x{n_autos}", d_autos))
    total += d_autos

    # spellblade
    if st["spellbladeBaseAdPct"] or st["spellbladePctMaxHp"]:
        procs = min(casts_total, n_autos, 1 + int(window / SPELLBLADE_CD))
        d = (st["spellbladeBaseAdPct"] / 100.0 * st["baseAd"]
             + st["spellbladePctMaxHp"] / 100.0 * target["hp"]) * phys_m * procs
        parts.append((f"spellblade x{procs}", d))
        total += d

    # one-time procs + burn
    once = st["firstHit"] * phys_m + st["procMaxHpPct"] * target["hp"] * phys_m
    for flat, ap_pct, in [(p[0], p[1]) for p in st["runeProcs"]]:
        once += (flat + ap_pct * st["bonusAd"]) * phys_m
    for flat, ap_r in st["burstProcs"]:
        once += (flat + ap_r * st["ap"]) * magic_m
    if once:
        parts.append(("procs", once))
        total += once
    if st["dotDps"]:
        d = st["dotDps"] * window * magic_m
        parts.append(("burn", d))
        total += d

    total *= (1 + st["damageAmp"])
    return {"total": total, "parts": parts, "nAutos": n_autos}


def metrics(name: str, item_slugs: list[str], rune_names: list[str] | None = None,
            level: int = 13) -> dict:
    st = resolve_stats(name, level, item_slugs, rune_names)
    squishy = target_squishy(level)
    burst3 = rotation(name, st, squishy, 3.0, level)["total"]
    dmg8 = rotation(name, st, TARGETS["bruiser"], 8.0, level)["total"]
    dps8 = dmg8 / 8.0

    # time-to-kill the squishy (accounting for Collector-style execute)
    need = squishy["hp"] * (1 - st["execute"])
    ttk = None
    for t in [x * 0.25 for x in range(1, 49)]:
        if rotation(name, st, squishy, t, level)["total"] >= need:
            ttk = t
            break

    shield = st["shield"] + st["shieldPctBonusHp"] * st["bonusHp"] + st["shieldPctMaxHp"] * st["hp"]
    mixed_taken = 0.5 * 100 / (100 + st["armor"]) + 0.5 * 100 / (100 + st["mr"])
    ehp = (st["hp"] + shield) / mixed_taken / (1 - st["dr"] if st["dr"] < 1 else 1)
    sustain = st["vamp"] * dmg8 + st["healOnHit"] * rotation(name, st, TARGETS["bruiser"], 8.0, level)["nAutos"]

    return {"burst3": round(burst3), "dps8": round(dps8), "ttk": ttk,
            "ehp": round(ehp), "sustain": round(sustain),
            "ad": round(st["ad"]), "ap": round(st["ap"]), "hp": round(st["hp"])}


def fight_score(m: dict, variant: str, name: str = "") -> float:
    w_off, w_def = VARIANT_WEIGHTS.get(variant, (0.6, 0.4))
    shift = kit_adjust(name) if name else 0.0
    w_off = max(0.15, min(0.9, w_off + shift))
    w_def = 1 - w_off
    off = (m["burst3"] / REF_BURST) if variant in BURSTY else (m["dps8"] / REF_DPS)
    deff = (m["ehp"] + 0.5 * m["sustain"]) / REF_DEF
    return round(100 * (w_off * off + w_def * deff), 1)


def _build_lists(bd: dict) -> tuple[list[str], list[str]]:
    items = [i["slug"] for i in bd.get("coreBuild") or []]
    if bd.get("boots"):
        items.append(bd["boots"]["slug"])
    runes = []
    r = bd.get("runes") or {}
    if r.get("keystone"):
        runes.append(r["keystone"]["name"])
    runes += [m["name"] for m in r.get("treeMinors") or []]
    if r.get("flexMinor"):
        runes.append(r["flexMinor"]["name"])
    return items, runes


def score_items(name: str, items: list[str], runes: list[str], variant: str,
                role: str = "") -> dict:
    """Score an ordered item list (last slot = boots) at the 15-min gold reality
    AND at full build; combine. The mid-game score dominates (games are 15-20
    min): items you can't afford by the deciding fight barely count."""
    gpm = ROLE_GPM.get(role, 720)
    gold_mid = gpm * MID_MINUTE
    items_mid = affordable(items, gold_mid)

    full = metrics(name, items, runes, FULL_LEVEL)
    mid = metrics(name, items_mid, runes, MID_LEVEL)
    s_full = fight_score(full, variant, name)
    s_mid = fight_score(mid, variant, name)

    out = dict(full)
    out["scoreFull"] = s_full
    out["scoreMid"] = s_mid
    out["goldMid"] = int(gold_mid)
    out["itemsMid"] = len(items_mid)
    out["score"] = round(MID_WEIGHT * s_mid + FULL_WEIGHT * s_full, 1)
    return out


def score_build(name: str, bd: dict, variant: str, role: str = "") -> dict:
    items, runes = _build_lists(bd)
    return score_items(name, items, runes, variant, role)


def score_champion_builds(name: str, rec: dict, level: int = 13) -> dict:
    """Score every variant of one champion_builds.json record."""
    out = {}
    if name not in FORMULAS or name not in CHAMPS:
        return out
    role = rec.get("role", "")
    for variant, bd in (rec.get("builds") or {}).items():
        out[variant] = score_build(name, bd, variant, role)
    return out


if __name__ == "__main__":
    builds = _load("champion_builds.json")
    for name in sorted(builds):
        if name not in FORMULAS:
            continue
        print(f"=== {name} ===")
        for variant, m in score_champion_builds(name, builds[name]).items():
            ttk = f"{m['ttk']:.2f}s" if m["ttk"] else ">12s"
            print(f"  {variant:10} burst3 {m['burst3']:>5} | dps8 {m['dps8']:>4} | "
                  f"ttk {ttk:>6} | ehp {m['ehp']:>5} | sustain {m['sustain']:>4} | "
                  f"score {m['score']:>5}")
