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

_SITE_P = ROOT / "web-next" / "src" / "data" / "site.json"
_SITE = json.loads(_SITE_P.read_text(encoding="utf-8")) if _SITE_P.exists() else {}

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

# Named reference targets for multi-target TTK / target-type performance. The
# ADC is the real zero-defense champion (Ashe) computed at level; the rest are
# representative defensive blocks a build should be measured against.
def target_profiles(level: int) -> dict:
    adc = target_squishy(level)
    return {
        "adc": adc,
        "mage": {"hp": 2400, "armor": 80, "mr": 80, "bonusHp": 500},
        "fighter": {"hp": 3000, "armor": 110, "mr": 70, "bonusHp": 1200},
        "bruiser": {"hp": 3400, "armor": 130, "mr": 85, "bonusHp": 1700},
        "tank": {"hp": 5000, "armor": 250, "mr": 180, "bonusHp": 3200},
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
        "healShieldAmp": 0.0, "runeHealPerSec": 0.0, "graspPct": 0.0, "graspEvery": 5.0,
        # component healing shares (for the breakdown; total still == "vamp")
        "lifestealPct": 0.0, "omnivampPct": 0.0,
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
        st["lifestealPct"] += (g("physVampPct") + g("lifestealPct")) / 100.0
        st["omnivampPct"] += g("omnivampPct") / 100.0
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
    _champ = CHAMPS.get(name) or {}
    auto_centric = (CHAMP_CLASS.get(name) == "Marksman"
                    or "onHit" in (_champ.get("mechanics") or []))
    ks, mn = RUNE_FX.get("keystones", {}), RUNE_FX.get("minors", {})
    for rn in rune_names or []:
        r = ks.get(rn) or mn.get(rn)
        if not r:
            # fall back to the LLM-extracted numeric model
            fx = RUNE_ENGINE.get(rn) or {}
            g = lambda k: _lvl_range(fx[k], level) if k in fx else 0.0  # noqa: E731
            # Auto-gated runes (Empowerment: "3 consecutive attacks") only reach
            # full value on auto-centric kits; casters proc them unreliably.
            if rn in AUTO_GATED_RUNES:
                champ = CHAMPS.get(name) or {}
                auto_centric = (CHAMP_CLASS.get(name) == "Marksman"
                                or "onHit" in (champ.get("mechanics") or []))
                if not auto_centric:
                    scaled = {}
                    for k, v in fx.items():
                        if isinstance(v, dict) and "lvlRange" in v:
                            scaled[k] = {"lvlRange": [x * 0.45 for x in v["lvlRange"]]}
                        elif isinstance(v, (int, float)):
                            scaled[k] = v * 0.45
                        else:
                            scaled[k] = v
                    fx = scaled
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
        gate = 0.45 if (rn in AUTO_GATED_RUNES and not auto_centric) else 1.0
        st["bonusMs"] += st["baseMs"] * r.get("msPctAvg", 0) / 100.0
        st["haste"] += r.get("hasteFlat", 0)
        ms_amp += r.get("msAmpPct", 0) / 100.0
        st["baseAsPct"] += r.get("asPctAvg", 0) * gate
        st["hp"] += r.get("hpFlat", 0)
        st["bonusHp"] += r.get("hpFlat", 0)
        st["dr"] = max(st["dr"], r.get("drPct", 0) / 100.0)
        st["healShieldAmp"] += r.get("healShieldAmpPct", 0) / 100.0
        st["runeHealPerSec"] += r.get("healPerSec", 0) + r.get("healPerProc", 0) / 9.0
        if r.get("procTargetMaxHpPct"):
            st["graspPct"] += r["procTargetMaxHpPct"]
            st["graspEvery"] = r.get("procEverySec", 5)
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

    # Kit mechanics (extracted with evidence grounding) that change item math:
    #   fixedAttackSpeed — AS items don't speed this champion's attacks
    #   noResource       — mana items give nothing (Manamune conversion dies)
    #   doubleShot       — autos fire an extra partial shot (Lucian)
    #   reload           — magazine system throttles auto throughput (Graves)
    mech = {m.get("kind"): m for m in FORMULAS.get(name, {}).get("mechanics") or []}
    know = FORMULAS.get(name, {}).get("knowledge") or {}
    # knowledge may confirm resourcelessness even when the tooltip never says it
    if "noResource" not in mech and know.get("resource") in ("energy", "none"):
        mech["noResource"] = {"kind": "noResource", "evidence": "llm-knowledge"}
    if "noResource" in mech:
        # remove the Manamune-style AD we granted from item mana above
        for slug in item_slugs:
            fx0 = ENGINE_FX.get(slug) or {}
            if fx0.get("adFromManaPct"):
                st["bonusAd"] -= _lvl_range(fx0["adFromManaPct"], level) / 100.0 * st["mana"]
        st["mana"] = 0.0
    st["doubleShotMult"] = 1.0
    if "doubleShot" in mech:
        pct = float(mech["doubleShot"].get("secondShotPct", 50))
        st["doubleShotMult"] = 1 + pct / 100.0 * 0.6  # post-ability uptime approx
    st["reloadMag"] = float(mech["reload"].get("magazine", 2)) if "reload" in mech else 0.0

    st["ad"] = st["baseAd"] + st["bonusAd"]
    if "fixedAttackSpeed" in mech:
        st["as"] = st["baseAs"]  # attack speed does nothing for this kit
    else:
        as_pct = st["baseAsPct"]
        # Tier-2 knowledge: AS efficiency for kits that undervalue attack speed
        # WITHOUT an explicit reload model (reload takes precedence; no double dip)
        if not st["reloadMag"]:
            as_pct *= know.get("asEfficiency", 1.0)
        st["as"] = min(st["baseAs"] * (1 + as_pct / 100.0), AS_CAP)
    if st["reloadMag"]:
        # magazine of M shots then reload: throughput = M / (M/AS + reload).
        # Reload seconds from Tier-2 knowledge when available (tooltips are
        # qualitative here), else a documented 1s assumption.
        reload_s = know.get("reloadSeconds", 1.0)
        st["as"] = st["reloadMag"] / (st["reloadMag"] / st["as"] + reload_s)
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


# Sustained-window auto uptime by class: melee champions can't stick to a
# target for a whole fight (kiting, peel), so their auto count is discounted in
# long windows. Ranged classes keep full uptime. (Attack range isn't scraped,
# so class is the proxy.)
MELEE_AUTO_UPTIME = 0.75
RANGED_CLASSES = {"Marksman", "Mage", "Enchanter"}
# Runes whose trigger requires sustained basic attacking; casters get 45% value.
AUTO_GATED_RUNES = {"Empowerment", "Lethal Tempo"}
CHAMP_CLASS: dict[str, str] = {c["name"]: c.get("class", "")
                               for c in _SITE.get("champions", [])}


def _auto_uptime(name: str, window: float) -> float:
    if window <= 4.0:  # a burst combo happens at point blank either way
        return 1.0
    cls = CHAMP_CLASS.get(name, "")
    return 1.0 if cls in RANGED_CLASSES else MELEE_AUTO_UPTIME


def _auto_split(st, target, phys_m, magic_m, giant, crit_ev, per_auto_comps, comp_dmg):
    """One auto-attack's damage, split by type (physical / magic / true).

    Pre-doubleShot, pre-count: the caller scales by uptime and multiplies. Kept
    in one place so both rotation paths decompose autos identically.
    """
    a_phys = st["ad"] * crit_ev * phys_m * giant
    a_phys += st["onHitPhys"] * phys_m
    a_phys += (st["onHitPctCurrentHp"] * target["hp"] * 0.7
               + st["onHitPctMaxHp"] * target["hp"]) * phys_m
    a_phys += st["runeOnHitFlat"] * phys_m
    a_magic = st["onHitMagic"] * magic_m
    a_true = 0.0
    for comp, _slot in per_auto_comps:  # empowered-auto kit components
        cd = comp_dmg(comp, 3) / max(int(_rank_val(comp.get("hits", 1), 3) or 1), 1)
        t = comp["type"]
        if t == "magic":
            a_magic += cd
        elif t == "true":
            a_true += cd
        else:
            a_phys += cd
    return a_phys, a_magic, a_true


def _proc_split(st, target, phys_m, magic_m):
    """One-time procs (first-hit, %max-HP, rune procs, burst procs), by type."""
    once_p = st["firstHit"] * phys_m + st["procMaxHpPct"] * target["hp"] * phys_m
    for flat, ap_pct in [(p[0], p[1]) for p in st["runeProcs"]]:
        once_p += (flat + ap_pct * st["bonusAd"]) * phys_m
    once_m = 0.0
    for flat, ap_r in st["burstProcs"]:
        once_m += (flat + ap_r * st["ap"]) * magic_m
    return once_p, once_m


def rotation(name: str, st: dict, target: dict, window: float, level: int = 13) -> dict:
    """Damage dealt over `window` seconds: abilities on cooldown + autos."""
    f = FORMULAS.get(name, {}).get("abilities", {})
    phys_m, magic_m = _mults(st, target)
    giant = 1 + st["giant"] * min(1.0, target["bonusHp"] / 1700)
    crit_ev = 1 + st["crit"] * (st["critMult"] - 1)
    haste_m = 100 / (100 + st["haste"])

    total = 0.0
    auto_dmg = 0.0  # damage gated by attacking: autos + on-hit + spellblade
    by_type = {"physical": 0.0, "magic": 0.0, "true": 0.0}
    parts: list[tuple[str, float]] = []
    cast_log: dict[str, dict] = {}
    casts_total = 0

    def add_t(dtype: str, amt: float) -> None:
        by_type[dtype] = by_type.get(dtype, 0.0) + amt

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
        val *= max(1, int(_rank_val(comp.get("hits", 1), rank) or 1))
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
            amp_a = 1 + st["abilityAmp"]
            d = 0.0
            for c in comps:
                cd = comp_dmg(c, rank) * amp_a
                add_t(c["type"], cd)
                d += cd
            parts.append((f"[{slot}] {f[slot].get('name', slot)}", d))
            total += d
            casts_total += 1
        n_autos = max(n_autos_seq, int(window * st["as"] * 0.5))
        a_phys, a_magic, a_true = _auto_split(st, target, phys_m, magic_m, giant,
                                              crit_ev, per_auto_comps, comp_dmg)
        dsm = st.get("doubleShotMult", 1.0)
        auto = (a_phys + a_magic + a_true) * dsm * n_autos
        add_t("physical", a_phys * dsm * n_autos)
        add_t("magic", a_magic * dsm * n_autos)
        add_t("true", a_true * dsm * n_autos)
        total += auto
        auto_dmg += auto
        parts.append((f"autos x{n_autos}", auto))
        if st["spellbladeBaseAdPct"] or st["spellbladePctMaxHp"]:
            procs = min(casts_total, n_autos, 1 + int(window / SPELLBLADE_CD))
            d = (st["spellbladeBaseAdPct"] / 100.0 * st["baseAd"]
                 + st["spellbladePctMaxHp"] / 100.0 * target["hp"]) * phys_m * procs
            parts.append((f"spellblade x{procs}", d))
            add_t("physical", d)
            total += d
            auto_dmg += d
        once_p, once_m = _proc_split(st, target, phys_m, magic_m)
        once = once_p + once_m
        if once:
            parts.append(("procs", once))
            add_t("physical", once_p)
            add_t("magic", once_m)
            total += once
        if st["dotDps"]:
            d = st["dotDps"] * window * magic_m
            add_t("magic", d)
            total += d
        amp = 1 + st["damageAmp"]
        return {"total": total * amp, "parts": parts, "nAutos": n_autos,
                "autoDmg": auto_dmg * amp,
                "byType": {k: v * amp for k, v in by_type.items()}}

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
        max_casts = casts  # cd-allowed before action-time budget clamps it
        casts = min(casts, cast_budget)
        cast_budget -= casts
        casts_total += casts
        cast_log[slot] = {"name": ab.get("name", slot), "casts": casts, "max": max_casts}
        amp_a = 1 + st["abilityAmp"]
        d = 0.0
        for c in dmg_comps:
            cd = comp_dmg(c, rank) * casts * amp_a
            add_t(c["type"], cd)
            d += cd
        parts.append((f"[{slot}] {ab.get('name', slot)} x{casts}", d))
        total += d

    # autos
    n_autos = max(1, int(window * st["as"] * _auto_uptime(name, window)))
    a_phys, a_magic, a_true = _auto_split(st, target, phys_m, magic_m, giant,
                                          crit_ev, per_auto_comps, comp_dmg)
    dsm = st.get("doubleShotMult", 1.0)
    d_autos = (a_phys + a_magic + a_true) * dsm * n_autos
    add_t("physical", a_phys * dsm * n_autos)
    add_t("magic", a_magic * dsm * n_autos)
    add_t("true", a_true * dsm * n_autos)
    parts.append((f"autos x{n_autos}", d_autos))
    total += d_autos
    auto_dmg += d_autos

    # spellblade
    if st["spellbladeBaseAdPct"] or st["spellbladePctMaxHp"]:
        procs = min(casts_total, n_autos, 1 + int(window / SPELLBLADE_CD))
        d = (st["spellbladeBaseAdPct"] / 100.0 * st["baseAd"]
             + st["spellbladePctMaxHp"] / 100.0 * target["hp"]) * phys_m * procs
        parts.append((f"spellblade x{procs}", d))
        add_t("physical", d)
        total += d
        auto_dmg += d

    # one-time procs + burn
    once_p, once_m = _proc_split(st, target, phys_m, magic_m)
    once = once_p + once_m
    if once:
        parts.append(("procs", once))
        add_t("physical", once_p)
        add_t("magic", once_m)
        total += once
    if st["dotDps"]:
        d = st["dotDps"] * window * magic_m
        parts.append(("burn", d))
        add_t("magic", d)
        total += d
    if st["graspPct"]:  # Grasp-style recurring %max-HP proc (magic)
        procs = 1 + int(window / st["graspEvery"])
        d = st["graspPct"] / 100.0 * target["hp"] * magic_m * procs
        parts.append((f"Grasp x{procs}", d))
        add_t("magic", d)
        total += d

    amp = 1 + st["damageAmp"]
    total *= amp
    n_autos_ideal = max(1, int(window * st["as"]))  # no uptime discount
    return {"total": total, "parts": parts, "nAutos": n_autos,
            "nAutosIdeal": n_autos_ideal, "castLog": cast_log,
            "autoDmg": auto_dmg * amp,
            "byType": {k: v * amp for k, v in by_type.items()}}


def attack_style(name: str, item_slugs: list[str] | None = None,
                 rune_names: list[str] | None = None, level: int = 15) -> dict:
    """Measure how a champion actually deals damage: autos vs abilities.

    Runs the sustained (8s) rotation and splits total damage into the part
    gated by attacking (autos + on-hit + spellblade) versus ability casts.
    Measured on a real build when given one (reflects the realized playstyle),
    else on the bare kit. Purely derived from the scraped formulas — no opinion.

    Returns autoShare in [0,1] and a style tag:
        basic-attack   autos carry the damage  -> wants AS / crit / on-hit
        ability-caster abilities carry it      -> wants haste / pen / AD-AP ratios
        hybrid         both matter             -> mix, order by what scales harder
    """
    if name not in FORMULAS or name not in CHAMPS:
        return {"autoShare": 0.5, "abilityShare": 0.5, "style": "hybrid"}
    st = resolve_stats(name, level, item_slugs or [], rune_names or [])
    r = rotation(name, st, TARGETS["bruiser"], 8.0, level)
    tot = r["total"] or 1.0
    share = max(0.0, min(1.0, r.get("autoDmg", 0.0) / tot))
    style = "basic-attack" if share >= 0.55 else "ability-caster" if share <= 0.30 else "hybrid"
    return {"autoShare": round(share, 3), "abilityShare": round(1 - share, 3), "style": style}


STYLE_HINT = {
    "basic-attack": "attack speed, crit, on-hit and lethality; autos carry the damage",
    "ability-caster": "ability haste, penetration and big AD/AP ratios; abilities carry the damage",
    "hybrid": "both matter: some attack speed alongside ability haste and penetration",
}


def attack_profile(name: str, item_slugs: list[str] | None = None,
                   rune_names: list[str] | None = None, level: int = 15) -> dict:
    """Robust auto-vs-ability classification, blending two grounded signals.

    1. measured  — auto-share from simulating the champion's real build
                   (`attack_style`); the truth when the kit is fully modeled.
    2. knowledge — the LLM `asEfficiency` scalar (0.2 pure caster .. 1.0 pure
                   auto-attacker), which never has extraction holes.

    The sim is trusted less when ability components are unmodeled (those under-
    count ability damage and inflate the auto-share), so a champion with many
    holes leans on the knowledge signal. Flags data quality when the two
    disagree sharply — a useful pointer at missing formulas.
    """
    base = attack_style(name, item_slugs, rune_names, level)
    fm = FORMULAS.get(name, {}) or {}
    know = fm.get("knowledge", {}) or {}
    ab = fm.get("abilities", {}) or {}
    unmodeled = sum(len(a.get("unmodeled") or []) for a in ab.values()) if isinstance(ab, dict) else 0
    measured = base["autoShare"]
    ase = know.get("asEfficiency")
    if ase is None:
        autoness, quality = measured, "measured-only"
    else:
        know_auto = max(0.0, min(1.0, (float(ase) - 0.2) / 0.8))
        w = 1.0 / (1.0 + unmodeled / 6.0)  # discount the sim as holes accumulate
        autoness = w * measured + (1.0 - w) * know_auto
        quality = "flagged" if abs(measured - know_auto) > 0.35 else "ok"
    style = ("basic-attack" if autoness >= 0.55
             else "ability-caster" if autoness <= 0.35 else "hybrid")
    return {"style": style, "autoness": round(autoness, 3),
            "measuredAutoShare": measured, "asEfficiency": ase,
            "unmodeled": unmodeled, "dataQuality": quality,
            "buildHint": STYLE_HINT[style]}


def metrics(name: str, item_slugs: list[str], rune_names: list[str] | None = None,
            level: int = 13, fast: bool = False) -> dict:
    st = resolve_stats(name, level, item_slugs, rune_names)
    squishy = target_squishy(level)
    burst3 = rotation(name, st, squishy, 3.0, level)["total"]
    dmg8 = rotation(name, st, TARGETS["bruiser"], 8.0, level)["total"]
    dps8 = dmg8 / 8.0

    # time-to-kill the squishy (accounting for Collector-style execute).
    # `fast` skips the iterative solve — fight_score doesn't use ttk, so search
    # loops don't need it.
    need = squishy["hp"] * (1 - st["execute"])
    ttk = None
    for t in ([] if fast else [x * 0.25 for x in range(1, 49)]):
        if rotation(name, st, squishy, t, level)["total"] >= need:
            ttk = t
            break

    shield = st["shield"] + st["shieldPctBonusHp"] * st["bonusHp"] + st["shieldPctMaxHp"] * st["hp"]
    shield *= 1 + st["healShieldAmp"]  # Revitalize-style amplification
    mixed_taken = 0.5 * 100 / (100 + st["armor"]) + 0.5 * 100 / (100 + st["mr"])
    ehp = (st["hp"] + shield) / mixed_taken / (1 - st["dr"] if st["dr"] < 1 else 1)
    sustain = (st["vamp"] * dmg8 + st["runeHealPerSec"] * 8.0 * (1 + st["healShieldAmp"])
               + st["healOnHit"] * rotation(name, st, TARGETS["bruiser"], 8.0, level)["nAutos"])

    return {"burst3": round(burst3), "dps8": round(dps8), "ttk": ttk,
            "ehp": round(ehp), "sustain": round(sustain),
            "ad": round(st["ad"]), "ap": round(st["ap"]), "hp": round(st["hp"]),
            "armor": round(st["armor"]), "mr": round(st["mr"]),
            "moveSpeed": round(st["baseMs"] + st["bonusMs"]),
            "attackSpeed": round(st["as"], 2), "haste": round(st["haste"]),
            "crit": round(st["crit"] * 100), "mana": round(st["mana"])}


def fight_score(m: dict, variant: str, name: str = "",
                weights: tuple[float, float] | None = None) -> float:
    """Variant presets pick the weights; `weights` overrides them directly —
    that's the user-facing playstyle dial (e.g. (0.5, 0.5))."""
    w_off, w_def = weights or VARIANT_WEIGHTS.get(variant, (0.6, 0.4))
    if weights is None:
        shift = kit_adjust(name) if name else 0.0
        w_off = max(0.15, min(0.9, w_off + shift))
        w_def = 1 - w_off
    off = (m["burst3"] / REF_BURST) if variant in BURSTY else (m["dps8"] / REF_DPS)
    deff = (m["ehp"] + 0.5 * m["sustain"]) / REF_DEF
    return round(100 * (w_off * off + w_def * deff), 1)


def _ttk(name: str, st: dict, target: dict, level: int, cap: float = 15.0) -> float | None:
    """Seconds to kill `target`, solved on the 0.25s grid (execute-aware)."""
    need = target["hp"] * (1 - st["execute"])
    steps = int(cap / 0.25)
    for i in range(1, steps + 1):
        t = i * 0.25
        if rotation(name, st, target, t, level)["total"] >= need:
            return round(t, 2)
    return None


def _clean_label(label: str) -> str:
    """'[1] Decisive Strike x3' -> 'Decisive Strike'; 'autos x9' -> 'Autos'."""
    base = label.split(" x")[0]
    if base.startswith("["):
        base = base.split("] ", 1)[-1]
    return base[:1].upper() + base[1:] if base else base


def analyze_build(name: str, items: list[str], runes: list[str] | None = None,
                  level: int = 15, ablation: bool = True) -> dict:
    """Full multi-dimensional simulator readout for one build (on-demand, not in
    the search hot loop). Damage over multiple windows and target profiles, the
    damage-type / source / per-ability / per-item / per-rune breakdown, TTK vs
    five target types, survivability, and gold efficiency."""
    runes = runes or []
    st = resolve_stats(name, level, items, runes)
    profs = target_profiles(level)
    bruiser = TARGETS["bruiser"]

    # burst curve vs a squishy; sustained damage/DPS vs a bruiser
    burst = {str(w): round(rotation(name, st, profs["adc"], w, level)["total"])
             for w in (0.5, 1.0, 2.0, 3.0)}
    win_dmg = {w: rotation(name, st, bruiser, w, level)["total"] for w in (3.0, 5.0, 10.0, 20.0)}
    dps = {str(int(w)): round(win_dmg[w] / w) for w in (5.0, 10.0, 20.0)}

    # time-to-kill each target type
    ttk = {k: _ttk(name, st, t, level) for k, t in profs.items()}

    # damage composition, measured over the 8s bruiser fight
    r8 = rotation(name, st, bruiser, 8.0, level)
    tot = r8["total"] or 1.0
    by_type = {k: round(v) for k, v in r8["byType"].items()}
    by_type_pct = {k: round(100 * v / tot) for k, v in r8["byType"].items()}
    auto = r8["autoDmg"]
    by_source = {"auto": round(auto), "ability": round(max(0.0, tot - auto))}
    by_ability: dict[str, float] = {}
    for label, d in r8["parts"]:
        key = _clean_label(label)
        by_ability[key] = round(by_ability.get(key, 0.0) + d)

    # per-item and per-rune damage contribution by ablation (remove one, re-sim)
    item_attr, rune_attr = [], []
    if ablation:
        for slug in items:
            if slug not in ITEMS:
                continue
            sub = [s for s in items if s != slug]
            d2 = rotation(name, resolve_stats(name, level, sub, runes), bruiser, 8.0, level)["total"]
            item_attr.append({"slug": slug, "name": ITEMS[slug]["name"], "dmg": round(tot - d2)})
        for rn in runes:
            sub = [r for r in runes if r != rn]
            d2 = rotation(name, resolve_stats(name, level, items, sub), bruiser, 8.0, level)["total"]
            rune_attr.append({"name": rn, "dmg": round(tot - d2)})
        item_attr.sort(key=lambda x: x["dmg"], reverse=True)
        rune_attr.sort(key=lambda x: x["dmg"], reverse=True)

    # survivability + gold efficiency
    m = metrics(name, items, runes, level)
    gold = sum((ITEMS.get(s) or {}).get("cost", 0) or 0 for s in items)
    surv = {k: round(m["ehp"] / dps_in, 2) if (dps_in := _incoming_dps(k)) else None
            for k in ("adc", "bruiser", "tank")}
    gold_eff = {
        "gold": gold,
        "dmgPerGold": round(win_dmg[3.0] / gold, 2) if gold else None,
        "ehpPerGold": round(m["ehp"] / gold, 2) if gold else None,
    }

    # #7 healing breakdown over the 8s fight (lifesteal keys off physical damage,
    # omnivamp off all; on-hit and rune heal are flat/time-based).
    phys8 = r8["byType"].get("physical", 0.0)
    healing = {
        "lifesteal": round(st["lifestealPct"] * phys8),
        "omnivamp": round(st["omnivampPct"] * tot),
        "onHit": round(st["healOnHit"] * r8["nAutos"]),
        "rune": round(st["runeHealPerSec"] * 8.0 * (1 + st["healShieldAmp"])),
    }
    healing["total"] = sum(healing.values())

    # #8 shields: peak value + a coarse average uptime (kit shields recur;
    # reactive lifeline shields sit near half-uptime in a drawn-out fight).
    shield_val = st["shield"] + st["shieldPctBonusHp"] * st["bonusHp"] + st["shieldPctMaxHp"] * st["hp"]
    shield_val *= 1 + st["healShieldAmp"]
    reactive = st["shieldPctMaxHp"] > 0 or st["shieldPctBonusHp"] > 0
    shields = {"value": round(shield_val),
               "avgUptime": 0.45 if reactive else (0.7 if shield_val else 0.0),
               "amp": round(st["healShieldAmp"] * 100)}

    # #5 EHP split by damage type; #9 damage prevented vs a reference 8s of
    # incoming pressure split 50/50 physical/magic.
    phys_taken = 100 / (100 + st["armor"])
    magic_taken = 100 / (100 + st["mr"])
    dr = st["dr"] if st["dr"] < 1 else 0.99
    ehp_split = {
        "physical": round((st["hp"] + shield_val) / phys_taken / (1 - dr)),
        "magic": round((st["hp"] + shield_val) / magic_taken / (1 - dr)),
    }
    raw_in = _INCOMING_DPS["bruiser"] * 8.0
    phys_raw, magic_raw = raw_in * 0.5, raw_in * 0.5
    prevented = {
        "armor": round(phys_raw * (1 - phys_taken)),
        "mr": round(magic_raw * (1 - magic_taken)),
        "dr": round((phys_raw * phys_taken + magic_raw * magic_taken) * dr),
        "shield": round(shield_val),
    }
    prevented["total"] = sum(prevented.values())

    # #14 cooldown utilization: casts landed vs cd-allowed in the 8s fight.
    clog = r8.get("castLog", {})
    used = sum(v["casts"] for v in clog.values())
    cap = sum(v["max"] for v in clog.values()) or 1
    cooldown_util = {
        "efficiency": round(100 * used / cap),
        "abilities": {v["name"]: {"casts": v["casts"], "max": v["max"]} for v in clog.values()},
    }

    # #12 damage lost to real-fight friction: auto uptime, and overkill past the
    # squishy's health bar at the kill.
    per_auto = (r8["autoDmg"] / r8["nAutos"]) if r8["nAutos"] else 0.0
    auto_lost = round(max(0, r8["nAutosIdeal"] - r8["nAutos"]) * per_auto)
    tsq = profs["adc"]
    ttk_sq = ttk.get("adc")
    overkill = 0
    if ttk_sq:
        dealt = rotation(name, st, tsq, ttk_sq, level)["total"]
        overkill = round(max(0.0, dealt - tsq["hp"] * (1 - st["execute"])))
    damage_lost = {
        "autoUptimePct": round(100 * r8["nAutos"] / max(1, r8["nAutosIdeal"])),
        "autoDmgLost": auto_lost,
        "overkill": overkill,
    }

    return {
        "level": level, "burst": burst, "dps": dps,
        "damage3s": round(win_dmg[3.0]), "damage8s": round(tot),
        "ttk": ttk, "byType": by_type, "byTypePct": by_type_pct,
        "bySource": by_source, "byAbility": by_ability,
        "items": item_attr, "runes": rune_attr,
        "ehp": m["ehp"], "ehpSplit": ehp_split, "sustain": m["sustain"],
        "survivalTime": surv, "goldEff": gold_eff,
        "healing": healing, "shields": shields, "damagePrevented": prevented,
        "cooldownUtil": cooldown_util, "damageLost": damage_lost,
    }


# Reference incoming pressure (team DPS onto you) by threat archetype, for the
# survivability-time metric. Rough but consistent across builds.
_INCOMING_DPS = {"adc": 900, "bruiser": 650, "tank": 400}


def _incoming_dps(kind: str) -> float:
    return _INCOMING_DPS.get(kind, 0.0)


# Composite Win Score (#20): fold the dimensions into one rankable number with
# role-dependent weights. Assassins favour burst + TTK; ADCs favour sustained
# DPS; tanks favour survivability. Weights sum to 1 and are tunable.
WIN_PRESETS = {
    "assassin": {"ttk": 0.30, "dps": 0.10, "burst": 0.35, "surv": 0.15, "heal": 0.05, "util": 0.05},
    "adc":      {"ttk": 0.30, "dps": 0.40, "burst": 0.05, "surv": 0.15, "heal": 0.05, "util": 0.05},
    "mage":     {"ttk": 0.25, "dps": 0.20, "burst": 0.35, "surv": 0.10, "heal": 0.05, "util": 0.05},
    "bruiser":  {"ttk": 0.30, "dps": 0.25, "burst": 0.10, "surv": 0.25, "heal": 0.05, "util": 0.05},
    "tank":     {"ttk": 0.10, "dps": 0.15, "burst": 0.05, "surv": 0.50, "heal": 0.10, "util": 0.10},
    "default":  {"ttk": 0.40, "dps": 0.25, "burst": 0.15, "surv": 0.10, "heal": 0.05, "util": 0.05},
}
# class -> preset routing
_CLASS_PRESET = {
    "Assassin": "assassin", "Marksman": "adc", "Mage": "mage",
    "Fighter": "bruiser", "Tank": "tank", "Support": "default",
}
REF_TTK, REF_SURV, REF_HEAL = 4.0, 6.0, 1500.0


def win_score(analysis: dict, preset: str = "default", champ_class: str = "") -> dict:
    """Weighted composite of the multi-dimensional readout -> one rankable score.

    `preset` picks the weighting; if left default and a champ_class is given, the
    class routes to its natural preset (assassin/adc/mage/bruiser/tank)."""
    if preset == "default" and champ_class:
        preset = _CLASS_PRESET.get(champ_class, "default")
    w = WIN_PRESETS.get(preset, WIN_PRESETS["default"])
    ttk_b = analysis["ttk"].get("bruiser")
    dps10 = analysis["dps"].get("10", 0)
    burst3 = analysis["burst"].get("3.0", 0)
    surv_b = (analysis.get("survivalTime") or {}).get("bruiser") or 0
    heal = analysis.get("sustain", 0)
    sub = {
        "ttk": (REF_TTK / ttk_b) if ttk_b else 0.0,
        "dps": dps10 / REF_DPS,
        "burst": burst3 / REF_BURST,
        "surv": surv_b / REF_SURV,
        "heal": heal / REF_HEAL,
        "util": 0.5,  # placeholder until CC/shielding utility is modeled
    }
    score = round(100 * sum(w[k] * sub[k] for k in w), 1)
    return {"score": score, "preset": preset,
            "subScores": {k: round(v, 3) for k, v in sub.items()}, "weights": w}


def _ttk_stochastic(name: str, st: dict, target: dict, level: int, rng,
                    cap: float = 15.0) -> float:
    """One randomized time-to-kill: realized crit rate, auto misses and small
    timing jitter vary around the deterministic expectation."""
    import math
    base_crit = st["crit"]
    n_ref = max(1, int(cap * st["as"]))
    # realized crit rate ~ Normal around p with binomial spread over the fight
    if base_crit > 0:
        sd = math.sqrt(max(base_crit * (1 - base_crit) / n_ref, 0.0))
        realized = min(1.0, max(0.0, rng.gauss(base_crit, sd)))
    else:
        realized = 0.0
    miss = rng.uniform(0.0, 0.08)          # dodge / step-back uptime loss
    jitter = rng.uniform(0.92, 1.08)       # cast/animation timing noise
    trial = dict(st)
    trial["crit"] = realized
    trial["as"] = st["as"] * (1 - miss)
    need = target["hp"] * (1 - st["execute"])
    steps = int(cap / 0.25)
    for i in range(1, steps + 1):
        t = i * 0.25
        if rotation(name, trial, target, t * jitter, level)["total"] >= need:
            return round(t, 3)
    return cap


def monte_carlo(name: str, items: list[str], runes: list[str] | None = None,
                level: int = 15, target_kind: str = "bruiser", trials: int = 400,
                opponent: tuple | None = None) -> dict:
    """Thousands of randomized fights -> a TTK distribution instead of a single
    number, plus an optional head-to-head win-rate versus another build.

    opponent = (name, items, runes, class) to race: win = your kill lands first.
    On-demand only; never call this inside the search loop."""
    import random, statistics
    rng = random.Random(0xC0FFEE)  # fixed seed -> reproducible reports
    st = resolve_stats(name, level, items, runes or [])
    target = target_profiles(level).get(target_kind, TARGETS["bruiser"])
    samples = sorted(_ttk_stochastic(name, st, target, level, rng) for _ in range(trials))

    def pct(p):
        return samples[min(len(samples) - 1, int(p * len(samples)))]

    out = {
        "target": target_kind, "trials": trials,
        "meanTtk": round(statistics.fmean(samples), 2),
        "bestTtk": round(samples[0], 2), "worstTtk": round(samples[-1], 2),
        "ci95": [round(pct(0.025), 2), round(pct(0.975), 2)],
        "stdev": round(statistics.pstdev(samples), 3),
    }
    if opponent:
        on, oi, oru, _ = opponent
        ost = resolve_stats(on, level, oi, oru or [])
        rng2 = random.Random(0xBEEF)
        wins = 0
        for _ in range(trials):
            mine = _ttk_stochastic(name, st, target, level, rng2)
            theirs = _ttk_stochastic(on, ost, target, level, rng2)
            wins += 1 if mine < theirs else 0
        out["winRateVs"] = {"name": on, "winRate": round(100 * wins / trials, 1)}
    return out


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


# Level curve as the build comes online: rough WR level when you complete your
# Nth purchase (boots is the 2nd). Used for the gold/prefix curve.
PREFIX_LEVELS = [8, 10, 12, 13, 14, 15]


def score_items(name: str, items: list[str], runes: list[str], variant: str,
                role: str = "", fast: bool = False,
                weights: tuple[float, float] | None = None,
                gold: float | None = None, level: int | None = None) -> dict:
    """Score an ordered item list (last slot = boots).

    Default: UNLIMITED gold — the full build at level 15 (gold caps limited
    build flexibility; the user can set a budget explicitly instead). When
    `gold` is given, only the affordable prefix (in build order) is scored, at
    a level matching that stage of the game."""
    scored_items = items
    lvl = level or FULL_LEVEL
    if gold is not None:
        scored_items = affordable(items, gold)
        lvl = level or PREFIX_LEVELS[min(len(scored_items), len(PREFIX_LEVELS)) - 1]

    m = metrics(name, scored_items, runes, lvl, fast=fast)
    out = dict(m)
    out["score"] = fight_score(m, variant, name, weights)
    out["level"] = lvl
    if gold is not None:
        out["gold"] = int(gold)
        out["itemsOwned"] = len(scored_items)
    return out


def build_curve(name: str, items: list[str], runes: list[str], variant: str,
                role: str = "") -> list[dict]:
    """Engine metrics after each purchase in build order (the user's gold
    slider): prefix of N items -> {gold, level, score, burst3, dps8, ehp}."""
    order = list(items)
    if len(order) >= 2:  # boots (last slot) are bought 2nd, matching affordable()
        order = [order[0], order[-1]] + order[1:-1]
    curve = []
    spent = 0.0
    for i in range(len(order)):
        prefix = order[: i + 1]
        spent += (ITEMS.get(order[i]) or {}).get("cost", 0) or 0
        lvl = PREFIX_LEVELS[min(i, len(PREFIX_LEVELS) - 1)]
        m = metrics(name, prefix, runes, lvl, fast=True)
        curve.append({
            "n": i + 1, "gold": int(spent), "level": lvl,
            "item": (ITEMS.get(order[i]) or {}).get("name", order[i]),
            "score": fight_score(m, variant, name),
            "burst3": m["burst3"], "dps8": m["dps8"], "ehp": m["ehp"],
        })
    return curve


def score_build(name: str, bd: dict, variant: str, role: str = "",
                curve: bool = False) -> dict:
    items, runes = _build_lists(bd)
    out = score_items(name, items, runes, variant, role)
    if curve:
        out["curve"] = build_curve(name, items, runes, variant, role)
    return out


def score_champion_builds(name: str, rec: dict, level: int = 13) -> dict:
    """Score every variant of one champion_builds.json record."""
    out = {}
    if name not in FORMULAS or name not in CHAMPS:
        return out
    role = rec.get("role", "")
    for variant, bd in (rec.get("builds") or {}).items():
        out[variant] = score_build(name, bd, variant, role, curve=True)
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
