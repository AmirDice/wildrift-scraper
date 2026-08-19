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
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str):
    p = ROOT / "data" / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _with_forms(champs: list[dict]) -> dict:
    """Champions by name, plus each transform form as a champion of its own.

    A form ("Kayn (Rhaast)") is a different kit on the same base stats, so it
    simulates as a separate champion. Keeping it nested inside the parent in
    champions_wr.json means the roster stays 141 -- only code that asks for
    forms sees them."""
    out = {}
    for c in champs:
        out[c["name"]] = c
        for form in c.get("forms") or []:
            out[form["name"]] = form
    return out


CHAMPS = _with_forms(_load("champions_wr.json"))
FORMULAS = _load("ability_formulas.json")


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


def _apply_formula_corrections(formulas: dict) -> int:
    """Fold data/formula_corrections.json into the formulas.

    Reviewed fixes to the LLM-estimated `knowledge` and `mechanics` blocks
    (wrong resource types, asEfficiency stuck at the caster floor for kits
    whose abilities count attacks). asEfficiency multiplies straight into
    attack speed below, so a wrong value here distorts every simulation.
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


_apply_recovered_conditions(FORMULAS)
_apply_formula_corrections(FORMULAS)
# Combos are overlaid from champion_combos.json, the same source the exported
# engine.json uses, so the Python and browser engines open with the same
# sequence. The extraction's own combo answers a different question ("standard
# burst" rather than "highest damage") and is rewritten on every re-extraction.
for _name, _entry in ((_load("champion_combos.json") or {}).get("champions") or {}).items():
    if _name in FORMULAS and _entry.get("combo"):
        FORMULAS[_name]["combo"] = _entry["combo"]
ITEMS = {i["slug"]: i for i in _load("items.json")}
ENGINE_FX = _load("item_engine.json")
for slug, fx in _load("item_engine_overrides.json").items():
    if isinstance(fx, dict):
        ENGINE_FX.setdefault(slug, {}).update({k: v for k, v in fx.items() if not k.startswith("_")})
KIT_AMPS = (_load("kit_amps.json") or {}).get("champions", {})
# Who a kit heal lands on, per champion and slot: "self", "ally" or "both".
# Everything the engine used to do assumed "ally", which is right for an
# enchanter and wrong for every bruiser who sustains through his own kit.
HEAL_TARGETS = (_load("heal_targets.json") or {}).get("champions", {})
# How hurt a champion is when a missing-health heal lands. Healing off missing
# health is worth nothing at full health and everything at death's door; this is
# the one number in the heal model that the tooltips cannot supply.
MISSING_HP_IN_FIGHT = 0.4


def heal_target(name: str, slot: str) -> str:
    """Hand-verified; anything unlisted keeps the historical ally-facing read."""
    return (HEAL_TARGETS.get(name) or {}).get(slot, "ally")


def kit_heal(name: str, st: dict, level: int, window: float, audience: str,
             dmg_by_slot: dict | None = None, dmg_total: float = 0.0) -> float:
    """Healing and shielding this kit produces for `audience` over a fight.

    Shared by the ally-value model and the champion's own sustain so the two
    read the same components and cannot disagree about what a kit does."""
    f = (FORMULAS.get(name, {}) or {}).get("abilities", {}) or {}
    amp = 1 + st["healShieldAmp"]
    haste_m = 100 / (100 + st["haste"])
    total = 0.0
    for slot, ab in f.items():
        target = heal_target(name, slot)
        if target != "both" and target != audience:
            continue
        comps = [c for c in (ab.get("defensive") or [])
                 if not c.get("alt") and c.get("kind") in ("heal", "shield")]
        if not comps:
            continue
        cds = ab.get("cooldowns") or []
        cd = (_rank_val(cds, 3) if cds else 8.0) * haste_m
        casts = 1 if slot == "4" else max(1, 1 + int(window // max(cd, 0.75)))
        for c in comps:
            v = _scale_val(c.get("base"), 3, level)
            for r in c.get("ratios") or []:
                pct = _scale_val(r.get("pct", 0), 3, level) / 100.0
                stat = r.get("stat")
                if stat == "damageDealt":
                    # Heals for a share of what THIS ability dealt in the
                    # simulated fight -- derived, not assumed. Deliberately the
                    # ability's own damage and not the champion's total: reading
                    # Warwick's passive percentage against everything he does
                    # gave him 4,759 healing over 8 seconds, more than his health
                    # bar. On-hit passives are not tracked per slot, so they
                    # contribute nothing here rather than something invented.
                    src = (dmg_by_slot or {}).get(slot, 0.0)
                elif stat == "ownMissingHp":
                    # Darius heals off MISSING health, which only exists once he
                    # has been hurt. MISSING_HP_IN_FIGHT is the one assumption
                    # here: a champion mid-fight, not one at full health.
                    src = st["hp"] * MISSING_HP_IN_FIGHT
                else:
                    src = {"ap": st["ap"], "ad": st["ad"], "bonusAd": st["bonusAd"],
                           "ownMaxHp": st["hp"], "ownBonusHp": st["bonusHp"]}.get(stat, 0.0)
                v += pct * src
            if c.get("when") == "dot total" and c.get("durationS"):
                v *= float(c["durationS"])
            total += v * casts
    return total * amp
# Ultimates that hit an area. Only Axiom Arcanist cares: it amplifies an ult by
# 10%, or by 5% when the damage is AoE.
AOE_ULTS = set((_load("ult_shape.json") or {}).get("aoeUlts", []))
RUNE_FX = _load("rune_effects.json")
RUNE_ENGINE = _load("rune_engine.json")  # LLM-extracted, used when not hand-curated
# Per-ability mana costs (wr-meta, patch 7.2). Read straight from the scrape
# rather than merged into champions_wr.json, which a re-scrape would overwrite.
WRMETA_CHAMPS = _load("wrmeta_champions.json")
GUIDE_META = _load("wrf_guide_meta.json")  # real skill orders from wildriftfire

_SITE_P = ROOT / "web-next" / "src" / "data" / "site.json"
_SITE = json.loads(_SITE_P.read_text(encoding="utf-8")) if _SITE_P.exists() else {}

BASE_CRIT_MULT = 1.75
# Font of Life procs on hitting a champion; in a real fight that lands roughly
# every few seconds, not every tick. Used to turn its per-proc heal into a rate.
FONT_PROC_EVERY = 3.0
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
    # Standard is the champion's best all-around build for a typical game: a
    # damage-leaning overall score (~45% damage, 30% survival, 25% utility/
    # mobility folded in) with NO forced offense/defense split, so it adapts to
    # the kit (glass for Zed, bruiser for Hecarim, tank for Ornn).
    "standard": (0.60, 0.40),
    "oneshot": (0.85, 0.15), "burst": (0.80, 0.20), "damage": (0.72, 0.28),
    "dps": (0.72, 0.28), "antitank": (0.70, 0.30), "crit": (0.70, 0.30),
    "poke": (0.70, 0.30), "sustained": (0.60, 0.40), "battlemage": (0.55, 0.45),
    "balanced": (0.55, 0.45), "survivability": (0.35, 0.65),
    "tanky": (0.30, 0.70), "utility": (0.25, 0.75),
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
    if isinstance(arr, dict):
        # A per-level range read where no level is in scope (hit counts, cooldowns):
        # take the level-15 end rather than crashing on the dict.
        r = arr.get("lvlRange") or [0]
        return float(r[-1])
    if not arr:
        return 0.0
    return float(arr[min(rank, len(arr) - 1)])


def _scale_val(v, rank: int, level: int) -> float:
    """A formula number: flat, per-ability-rank, or per-CHAMPION-level.

    Extraction writes level-scaling values (Teemo's "8 - 36 bonus magic damage",
    Aatrox's "4% - 13% of maximum Health") as {"lvlRange":[lo,hi]}, the same
    shape items and runes already use. Everything else stays a rank lookup."""
    if isinstance(v, dict) and "lvlRange" in v:
        return _lvl_range(v, level)
    return _rank_val(v, rank)


def _prefers_ap(name: str) -> bool:
    """Which half of an Adaptive grant this champion takes. Deliberately cheap
    (no simulation): resolve_stats runs inside the marginal-value probe, so
    calling the probe from here would recurse."""
    rec = FORMULAS.get(name) or {}
    champ = CHAMPS.get(name) or {}
    prim = rec.get("primaryDamage") or champ.get("primaryDamage")
    if prim:
        return prim == "magic"
    scales = champ.get("scalesWith") or []
    return "ap" in scales and "ad" not in scales


def _apply_stat(st: dict, k: str, val: float, pct: bool = False) -> None:
    """Add one raw stat to a stat block. Shared by item stats and the synthetic
    probe in stat_marginal_value, so both go through identical handling."""
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
    elif k == "magicPenFlat":
        st["flatMagicPen"] += val
    elif k in ("physicalPen", "lethality"):
        # % armor pen is multiplicative against armor; flat pen subtracts. These
        # were both dumped into flatPen, so Dominik's 36% READ AS 36 FLAT.
        if pct:
            st["pctPenFactors"].append(val / 100.0)
        else:
            st["flatPen"] += val
    elif k == "physicalPenFlat":
        st["flatPen"] += val
    elif k == "moveSpeed":
        if pct:
            st["bonusMs"] += st["baseMs"] * val / 100.0
        else:
            st["bonusMs"] += val
    elif k == "healShieldPower":
        # Same channel the healShieldAmpPct item effect feeds. Was dropped
        # entirely, so "+10% Heal and Shield Strength" did nothing.
        st["healShieldAmp"] += val / 100.0
    elif k == "physicalVamp":
        # Mirrors the physVampPct item effect.
        st["vamp"] += val / 100.0
        st["lifestealPct"] += val / 100.0


def resolve_stats(name: str, level: int, item_slugs: list[str],
                  rune_names: list[str] | None = None,
                  bonus: dict | None = None) -> dict:
    """Champion base stats + item stats + engine passives + kit steroids.

    `bonus` injects raw stats (the marginal-value probe) through the same
    derivation, so reload / fixed-AS / asEfficiency mechanics still apply."""
    bs = CHAMPS[name]["baseStats"]

    def base(k, default=0.0):
        s = bs.get(k)
        return (s["base"] + s["perLevel"] * (level - 1)) if s else default

    st = {
        "baseAd": base("ad", 60), "bonusAd": 0.0, "ap": 0.0,
        "hp": base("hp", 1800), "bonusHp": 0.0,
        "armor": base("armor", 60), "mr": base("mr", 45),
        "baseAsPct": 0.0,  # bonus attack speed %
        "baseAs": attack_speed_ratio(
            name, bs.get("attackSpeed", {}).get("base", 0.75) or 0.75),
        "crit": 0.0, "critMult": BASE_CRIT_MULT, "critDamagePerExcessCrit": 0.0,
        "critDisabled": 0.0,
        # Real per-champion mana, scraped at last. A manaless kit has no entry
        # and correctly starts at 0, so Muramana's "AD = % of max mana" grants
        # it nothing without any special-casing.
        "haste": 0.0, "mana": base("mana", 0.0),
        "flatPen": 0.0, "pctPenFactors": [], "flatMagicPen": 0.0, "pctMagicPen": 0.0,
        "baseMs": bs.get("moveSpeed", {}).get("base", 330) or 330, "bonusMs": 0.0,
        "abilityAmp": 0.0, "damageAmp": 0.0, "giant": 0.0, "execute": 0.0,
        # Procs whose condition the rotation has to verify, and ult-only amp.
        "conditionalProcs": [], "ultAmp": 0.0,
        "spellbladeBaseAdPct": 0.0, "spellbladePctMaxHp": 0.0,
        "spellbladeApPct": 0.0, "spellbladeMagic": 0.0,
        "extraOnHitApplications": 0.0,
        "onHitPhys": 0.0, "onHitMagic": 0.0, "onHitPctCurrentHp": 0.0, "onHitPctMaxHp": 0.0,
        "burstProcs": [], "dotDps": 0.0, "dotPctMaxHp": 0.0, "procMaxHpPct": 0.0, "firstHit": 0.0,
        "armorShred": 0.0, "mrShred": 0.0, "mrShredFlat": 0.0,
        "apAmp": 0.0, "hastePct": 0.0, "cdRefundPctPerAuto": 0.0,
        "cleaveFlat": 0.0, "cleavePctBonusHp": 0.0,
        "vamp": 0.0, "healOnHit": 0.0,
        "shield": 0.0, "shieldPctBonusHp": 0.0, "shieldPctMaxHp": 0.0, "dr": 0.0,
        "healShieldAmp": 0.0, "runeHealPerSec": 0.0, "runeAllyHealPerSec": 0.0,
        "allyShield": 0.0,
        "graspPct": 0.0, "graspEvery": 5.0,
        # component healing shares (for the breakdown; total still == "vamp")
        "lifestealPct": 0.0, "omnivampPct": 0.0,
    }

    # AD/AP/HP-from-mana percentages, applied after runes (see below).
    mana_conv = {"ad": 0.0, "ap": 0.0, "hp": 0.0}
    # Adaptive on-hits (Nashor's Gnaw): the amount scales with FINAL AD/AP, so
    # accumulation is deferred until every stat source (Overkill included) has
    # landed; the damage TYPE follows the kit like the adaptive stat grant.
    adaptive_onhit = {"flat": 0.0, "adPct": 0.0, "apPct": 0.0}
    # Attack-rate estimate for stack ramp-up, from the build's own AS items.
    # Deliberately rough (ignores runes and AS passives): it only decides how
    # fast stacking items reach max, a second-order effect.
    _as_pct = sum((it["stats"].get("attackSpeed") or {}).get("value", 0)
                  for it in (ITEMS.get(s) for s in item_slugs) if it)
    _atk_rate = min(AS_CAP, (bs.get("attackSpeed", {}).get("base", 0.75) or 0.75)
                    * (1 + _as_pct / 100.0))

    for slug in item_slugs:
        it = ITEMS.get(slug)
        if not it:
            continue
        for k, v in it["stats"].items():
            _apply_stat(st, k, v["value"], v["percent"])
        # synthetic stat probe (used by stat_marginal_value); goes through the
        # same path so mechanics like reload / asEfficiency still apply.
        fx = ENGINE_FX.get(slug) or {}
        # STACK RAMP-UP: attack-stacked effects were granted at max from second
        # zero of the fight, which is the convention that parked Terminus in 18
        # of 48 builds (its 33%/33% pen needs SIX alternating attacks to exist).
        # Scale the stack-built keys by the average stack fraction over the 8s
        # window at this build's attack rate. Always-on parts (Terminus' flat 35
        # on-hit, Guinsoo's adaptive) are untouched.
        if fx.get("rampAttacks"):
            _tau = float(fx["rampAttacks"]) / max(_atk_rate, 0.1)
            _ramp = max(0.35, min(1.0, 1 - _tau / 16.0 if _tau <= 8.0
                                  else 4.0 / _tau))
            fx = {**fx, **{k: (v * _ramp if isinstance(v, (int, float)) else
                               {"lvlRange": [x * _ramp for x in v["lvlRange"]]}
                               if isinstance(v, dict) and "lvlRange" in v else v)
                           for k, v in fx.items()
                           if k in ("pctPen", "mrShredPct", "armorShredPct",
                                    "asPctPassive")}}
        g = lambda k: _lvl_range(fx[k], level) if k in fx else 0.0  # noqa: E731
        st["flatPen"] += g("flatPen")
        if fx.get("pctPen"):
            st["pctPenFactors"].append(g("pctPen") / 100.0)
        st["armorShred"] = max(st["armorShred"], g("armorShredPct") / 100.0)
        st["critMult"] = max(st["critMult"], float(fx.get("critMult", 0)) or 0)
        if fx.get("disablesCrit"):
            st["critDisabled"] = 1.0
        st["abilityAmp"] += g("abilityAmpPct") / 100.0
        st["damageAmp"] += g("damageAmpPct") / 100.0
        st["giant"] = max(st["giant"], g("giantSlayerPct") / 100.0)
        st["execute"] = max(st["execute"], g("executePct") / 100.0)
        st["spellbladeBaseAdPct"] = max(st["spellbladeBaseAdPct"], g("spellbladeBaseAdPct"))
        # Divine Sunderer pays ranged champions 7%, not the melee 10%.
        _sb_max = g("spellbladePctMaxHp")
        if (CHAMP_CLASS.get(name, "") in RANGED_CLASSES
                and fx.get("spellbladePctMaxHpRanged")):
            _sb_max = g("spellbladePctMaxHpRanged")
        st["spellbladePctMaxHp"] = max(st["spellbladePctMaxHp"], _sb_max)
        st["spellbladeApPct"] = max(st["spellbladeApPct"], g("spellbladeApPct"))
        # Dusk and Dawn's second clause: "apply on-hits to the target 1
        # additional time", on the same spellblade proc. Worth more than its
        # small spellblade half to an on-hit build (Nashor's, Wit's End), and
        # invisible before this key existed.
        st["extraOnHitApplications"] = max(st["extraOnHitApplications"],
                                           g("extraOnHitOnSpellblade"))
        # Damage TYPE is read from the item's own text, not asked of the model: a
        # flag key would have to be grounded, and the literal "1" of a boolean
        # never appears in a tooltip, so it could never survive the filter.
        if fx.get("spellbladeBaseAdPct") or fx.get("spellbladeApPct"):
            _txt = " ".join((ITEMS.get(slug) or {}).get("passives") or []).lower()
            if "spellblade" in _txt and "magic damage" in _txt:
                st["spellbladeMagic"] = 1.0
        st["onHitPhys"] += g("onHitFlatPhys")
        st["onHitMagic"] += g("onHitFlatMagic")
        # Wild Rift %HP on-hits pay ranged champions less (BotRK: 10% melee, 8.5%
        # ranged). Extraction stores the melee number in the base key; prefer the
        # "...Ranged" companion when this champion attacks from range.
        _rngd = CHAMP_CLASS.get(name, "") in RANGED_CLASSES
        for _base in ("onHitPctCurrentHp", "onHitPctMaxHp"):
            _k = _base + "Ranged" if (_rngd and (_base + "Ranged") in fx) else _base
            st[_base] += g(_k) / 100.0
        st["procMaxHpPct"] += g("procMaxHpPct") / 100.0
        st["firstHit"] += g("firstHit")
        if fx.get("burstProcFlat") or fx.get("burstProcApPct"):
            st["burstProcs"].append((g("burstProcFlat"), g("burstProcApPct") / 100.0))
        st["dotDps"] += g("dotDps")
        # %max-HP burns (Searing Crown) are target-scaled, so they are summed
        # here and priced at fight time. Ranged users pay the reduced rate.
        st["dotPctMaxHp"] += g("dotPctMaxHpPerSecRanged" if (_rngd and fx.get(
            "dotPctMaxHpPerSecRanged")) else "dotPctMaxHpPerSec") / 100.0
        if (fx.get("adaptiveOnHitFlat") or fx.get("adaptiveOnHitBonusAdPct")
                or fx.get("adaptiveOnHitApPct")):
            adaptive_onhit["flat"] += g("adaptiveOnHitFlat")
            adaptive_onhit["adPct"] += g("adaptiveOnHitBonusAdPct") / 100.0
            adaptive_onhit["apPct"] += g("adaptiveOnHitApPct") / 100.0
        st["vamp"] += (g("physVampPct") + g("omnivampPct") + g("lifestealPct")) / 100.0
        st["lifestealPct"] += (g("physVampPct") + g("lifestealPct")) / 100.0
        st["omnivampPct"] += g("omnivampPct") / 100.0
        st["healOnHit"] += g("healOnHitFlat")
        st["shield"] += g("shieldFlat")
        st["shieldPctBonusHp"] += g("shieldPctBonusHp") / 100.0
        st["shieldPctMaxHp"] += g("shieldPctMaxHp") / 100.0
        # A revive is, for EHP purposes, a shield worth X% of max HP: they have
        # to kill you twice. Conservative -- ignores the stasis window, during
        # which the enemy often disengages entirely.
        st["shieldPctMaxHp"] += g("reviveHpPct") / 100.0
        # Attack speed granted by a PASSIVE rather than the stat line. There was
        # no key for this at all, so Guinsoo's 32% and Youmuu's 25% were lost.
        st["baseAsPct"] += g("asPctPassive")
        st["critDamagePerExcessCrit"] += g("critDamagePerExcessCrit")
        # "Every Nth attack deals ..." (Hullbreaker's Skipper). Emphatically NOT
        # a spellblade and NOT an on-hit: it fires once per N autos, so only 1/N
        # of attacks carry it. Modelled as an averaged on-hit, scaled by the
        # ranged multiplier where the item has one.
        _n = g("everyNthAttack")
        if _n >= 2:
            _mult = (g("everyNthRangedMult") / 100.0
                     if (_rngd and fx.get("everyNthRangedMult")) else 1.0)
            st["onHitPhys"] += g("everyNthBaseAdPct") / 100.0 * st["baseAd"] * _mult / _n
            st["onHitPctMaxHp"] += g("everyNthPctMaxHp") / 100.0 * _mult / _n
        # "Gain 25 Attack Damage OR 50 Ability Power (Adaptive)" grants exactly
        # ONE. Storing both as adFlatPassive+apFlatPassive handed Lucian 25 AD
        # AND 50 AP off Nashor's. Pick by the kit's primary damage type; using
        # the marginal-value probe here would recurse (it calls resolve_stats).
        if fx.get("adaptiveAdFlat") or fx.get("adaptiveApFlat"):
            if _prefers_ap(name):
                st["ap"] += g("adaptiveApFlat")
            else:
                st["bonusAd"] += g("adaptiveAdFlat")
        st["dr"] = max(st["dr"], g("drPct") / 100.0)
        st["adFlatPassive"] = g("adFlatPassive")
        st["bonusAd"] += g("adFlatPassive")
        st["ap"] += g("apFlatPassive")
        st["haste"] += g("hasteFlatPassive")
        st["hp"] += g("hpFlatPassive"); st["bonusHp"] += g("hpFlatPassive")
        st["bonusMs"] += g("msFlat") + st["baseMs"] * g("msPct") / 100.0
        # Mana conversions are DEFERRED, not applied here: runes add mana after
        # this loop (Manaflow Band grants 300), and a resourceless kit zeroes it
        # later still. Converting now used the wrong mana and needed the total
        # subtracting back out again for noResource champions.
        mana_conv["ad"] += g("adFromManaPct")
        mana_conv["ap"] += g("apFromManaPct")
        mana_conv["hp"] += g("hpFromManaPct")
        st["ap"] += g("apFromBonusHpPct") / 100.0 * st["bonusHp"]
        st["mrShred"] = max(st["mrShred"], g("mrShredPct") / 100.0)
        st["mrShredFlat"] += g("mrShredFlat")
        # Percent resists from a PASSIVE (Amaranth's Endurance at average
        # in-combat stacks; the override stores the pre-averaged value).
        st["armor"] *= 1 + g("armorPctPassive") / 100.0
        st["mr"] *= 1 + g("mrPctPassive") / 100.0
        st["apAmp"] += g("apAmpPct") / 100.0
        st["hastePct"] += g("hastePctPassive") / 100.0
        st["cdRefundPctPerAuto"] += g("cdRefundPctPerAuto")
        st["cleaveFlat"] += g("cleaveFlat")
        st["cleavePctBonusHp"] += g("cleavePctBonusHp") / 100.0
        st["healShieldAmp"] += g("healShieldAmpPct") / 100.0  # e.g. Harmonic Echo

    for _k, _v in (bonus or {}).items():  # marginal-value probe
        _apply_stat(st, _k, _v)

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
            # Ally-gated runes (Guardian, Font of Life) only pay out with an
            # ally in range. Applied here, before any key is read, so every part
            # of the rune is discounted together.
            if rn in ALLY_GATED_RUNES:
                _up = _ally_uptime(name)
                fx = {k: ({"lvlRange": [x * _up for x in v["lvlRange"]]}
                          if isinstance(v, dict) and "lvlRange" in v
                          else (v * _up if isinstance(v, (int, float)) else v))
                      for k, v in fx.items()}
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
            # Mana is not a dead stat: it feeds the AD/AP-from-mana conversions
            # (Muramana, Archangel's). Manaflow Band's 300 was being dropped.
            st["mana"] += g("manaFlat")
            st["armor"] += g("armorFlat")
            st["mr"] += g("mrFlat")
            st["armor"] *= 1 + g("armorPct") / 100.0
            st["mr"] *= 1 + g("mrPct") / 100.0
            # Font of Life: a self+ally heal. The ally half is priced by
            # support_value via runeAllyHealPerSec.
            _heal = g("healPctMaxHp") / 100.0 * st["hp"] + g("healApRatio") / 100.0 * st["ap"]
            st["runeHealPerSec"] += _heal / FONT_PROC_EVERY
            st["runeAllyHealPerSec"] += (g("allyHealPctMaxHp") / 100.0 * st["hp"]
                                         + g("healApRatio") / 100.0 * st["ap"]) / FONT_PROC_EVERY
            # Guardian: shields YOU and the ally. Neither half was applied at
            # all -- the keystone's entire effect was being dropped. Note bonus
            # HP and max HP are different scalings: Guardian reads "+ 6% bonus
            # Health", and charging it off MAX HP nearly doubled the shield.
            _sh = (g("shieldFlat")
                   + g("shieldPctMaxHp") / 100.0 * st["hp"]
                   + g("shieldPctBonusHp") / 100.0 * st["bonusHp"]
                   + g("shieldApRatio") / 100.0 * st["ap"])
            st["shield"] += _sh
            st["allyShield"] += g("allyShieldFlat") + (_sh - g("shieldFlat")
                                                       if g("allyShieldFlat") else 0.0)
            ragg["onHitFlat"] += g("onHitFlat")
            ragg["ampPct"] += g("ampPct") / 100.0
            # Ability amplification from a RUNE. The same key was read for
            # items but never here, so Battle Zeal's ramping ability damage
            # ("up to a maximum of 6%") was extracted, stored, and dropped.
            st["abilityAmp"] += g("abilityAmpPct") / 100.0
            st["ultAmp"] += (g("ultAmpPctAoe") if name in AOE_ULTS
                             else g("ultAmpPct")) / 100.0
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
        # Vamp from a rune. Only items and the LLM rune path fed these, so a
        # curated rune granting omnivamp or lifesteal healed for nothing.
        _vamp = (r.get("omnivampPct", 0) + r.get("lifestealPct", 0)
                 + r.get("physVampPct", 0)) / 100.0
        st["vamp"] += _vamp
        st["omnivampPct"] += r.get("omnivampPct", 0) / 100.0
        st["lifestealPct"] += (r.get("lifestealPct", 0) + r.get("physVampPct", 0)) / 100.0
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
            cond = p.get("condition")
            if cond == "targetBelowHalfInWindow":
                # Checked later against the simulated rotation rather than
                # assumed: the proc is earned only if this champion's damage
                # actually takes the target below half health.
                flat = p.get("flat", 0) + p.get("perSoul", 0) * p.get("assumedSouls", 0)
                st["conditionalProcs"].append(
                    {"need": 0.5, "flat": flat, "adRatio": p.get("adRatio", 0),
                     "apRatio": p.get("apRatio", 0), "type": p.get("type", "magic")})
            elif cond != "targetBelow50":
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
    st["timedSteroids"] = []
    for _ab_slot, ab in f.items():
        for s in ab.get("steroids") or []:
            stat = s.get("stat")
            pct = _scale_val(s.get("pct"), 3, level) if s.get("pct") is not None else 0.0
            if s.get("from") == "bonusMs" and stat == "ad" and pct:
                continue  # applied after MS totals below
            # Ability buffs were applied permanently. Xin Zhao's E gives +67.5%
            # attack speed for FIVE seconds and the sim used it for the whole
            # fight. Duration is structured on nine steroids and stated in prose
            # on forty-two more, so both are read; anything with neither stays
            # permanent, which is right for passives.
            note_s = re.search(r"(\d+(?:\.\d+)?)\s*second", str(s.get("note") or ""), re.I)
            duration = (s.get("durationS") if isinstance(s.get("durationS"), (int, float))
                        else float(note_s.group(1)) if note_s else None)
            if duration and duration > 0:
                cds = ab.get("cooldowns") or []
                st["timedSteroids"].append({
                    "stat": stat,
                    "asPct": (pct or _scale_val(s.get("flat"), 3, level)) if stat == "attackSpeed" else 0.0,
                    "adFlat": _scale_val(s["flat"], 3, level) if stat == "ad" and s.get("flat") else 0.0,
                    "durationS": float(duration),
                    "cooldownS": _scale_val(cds, 3, level) if cds else 12.0,
                })
            if stat == "attackSpeed":
                st["baseAsPct"] += pct or _scale_val(s.get("flat"), 3, level)
            elif stat == "ad" and s.get("flat"):
                st["bonusAd"] += _scale_val(s["flat"], 3, level)
            elif stat == "moveSpeed" and pct:
                st["bonusMs"] += st["baseMs"] * pct / 100.0 * 0.5  # avg uptime
            elif stat in ("armor", "mr") and s.get("flat"):
                st[stat] += _scale_val(s["flat"], 3, level)
            elif stat == "damageReduction":
                # Flat damage reduction from a kit (Alistar's ultimate). Takes
                # the strongest source, mirroring how the rune path treats drPct.
                st["dr"] = max(st["dr"], _scale_val(s.get("pct"), 3, level) / 100.0)
            elif stat == "hp":
                # Transform ultimates grant flat Health (Shyvana, Nasus,
                # Volibear). It is bonus HP, so shield/HP-scaling effects see it.
                _hp = _scale_val(s.get("flat"), 3, level)
                if not _hp and s.get("pct"):
                    _hp = st["hp"] * _scale_val(s["pct"], 3, level) / 100.0
                st["hp"] += _hp
                st["bonusHp"] += _hp
    for ab in f.values():  # conversions last, after all MS sources counted
        for s in ab.get("steroids") or []:
            if s.get("from") == "bonusMs" and s.get("stat") == "ad" and s.get("pct") is not None:
                st["bonusAd"] += st["bonusMs"] * _scale_val(s["pct"], 3, level) / 100.0

    # Percent CDR (Ionian) is not flat haste: X% CDR == haste of 100X/(100-X).
    if st["hastePct"]:
        p = min(st["hastePct"], 0.9)
        st["haste"] += 100.0 * p / (1.0 - p)
    # Navori: each auto cuts remaining cooldowns, which is haste-equivalent
    # uptime. Approximated as haste; a real model needs per-cast cooldown state.
    if st["cdRefundPctPerAuto"]:
        st["haste"] += st["cdRefundPctPerAuto"] * 2.0

    # Guinsoo's Wrath: "Attacks ... no longer Critical Strike". The converted
    # magic damage is already in the item's onHitFlatMagic, so leaving crit
    # standing paid for the same conversion twice.
    if st.get("critDisabled"):
        st["crit"] = 0.0
        st["critMult"] = BASE_CRIT_MULT
        st["critDamagePerExcessCrit"] = 0.0

    # Infinity Edge "Limit Break": crit rate past 100% is wasted, so it converts
    # to crit DAMAGE. Runs here, once every crit source (items, runes) is summed.
    if st["critDamagePerExcessCrit"] and st["crit"] > 1.0:
        excess_pct = (st["crit"] - 1.0) * 100.0
        st["critMult"] += st["critDamagePerExcessCrit"] * excess_pct / 100.0
    st["crit"] = min(st["crit"], 1.0)

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
        st["mana"] = 0.0
    # Mana conversions land HERE: after items, after runes (Manaflow Band's 300),
    # and after a resourceless kit has zeroed mana -- so Manamune simply grants
    # nothing on Katarina rather than being granted and subtracted back.
    if mana_conv["ad"]:
        st["bonusAd"] += mana_conv["ad"] / 100.0 * st["mana"]
    if mana_conv["ap"]:
        st["ap"] += mana_conv["ap"] / 100.0 * st["mana"]
    if mana_conv["hp"]:
        _hp_mana = mana_conv["hp"] / 100.0 * st["mana"]
        st["hp"] += _hp_mana
        st["bonusHp"] += _hp_mana
    # Rabadon's "Overkill" multiplies TOTAL AP, so it must land after every AP
    # source above (items, runes, adaptive grants, Archangel's mana conversion).
    # It used to run BEFORE the mana conversions, contradicting this very
    # comment: Seraph's AP-from-mana escaped the 30% on every Deathcap build.
    if st["apAmp"]:
        st["ap"] *= 1 + st["apAmp"]
    # Adaptive on-hit (Gnaw) lands with FINAL stats. The old model paid the
    # flat 15 twice (once physical, once magic) and dropped the scaling half
    # entirely, which on an AP on-hit champion is most of the item.
    if adaptive_onhit["flat"] or adaptive_onhit["adPct"] or adaptive_onhit["apPct"]:
        _dmg = (adaptive_onhit["flat"] + adaptive_onhit["adPct"] * st["bonusAd"]
                + adaptive_onhit["apPct"] * st["ap"])
        if _prefers_ap(name):
            st["onHitMagic"] += _dmg
        else:
            st["onHitPhys"] += _dmg
    st["doubleShotMult"] = 1.0
    if "doubleShot" in mech:
        pct = float(mech["doubleShot"].get("secondShotPct", 50))
        st["doubleShotMult"] = 1 + pct / 100.0 * 0.6  # post-ability uptime approx
    # multiShot: one attack fires N projectiles (Graves' shotgun). Each pellet
    # rolls crit and carries on-hit, so this scales the whole auto — without it
    # the sim thinks such champions barely auto-attack.
    if "multiShot" in mech:
        shots = float(mech["multiShot"].get("shots", 1) or 1)
        per = float(mech["multiShot"].get("damagePerShotPct", 100) or 100)
        st["doubleShotMult"] *= max(1.0, shots * per / 100.0)
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
        # Attack speed GROWS with level, and the engine used to ignore that
        # entirely -- every champion fought at its level-1 rate. The bonus from
        # levels is innate, so asEfficiency (which discounts ITEM attack speed
        # on kits that convert it poorly) must not touch it.
        st["as"] = min(st["baseAs"] * (1 + level_as_bonus(name, level) + as_pct / 100.0),
                       AS_CAP)
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
    # MR shred mirrors armour shred (Abyssal Mask, Bloodletter's Curse). Only
    # armour had a shred channel, so magic shred items did nothing.
    mr = target["mr"] * (1 - st["mrShred"]) - st["mrShredFlat"]
    mr = mr * (1 - st["pctMagicPen"]) - st["flatMagicPen"]
    return 100 / (100 + max(armor, 0)), 100 / (100 + max(mr, 0))


# Sustained-window auto uptime by class: melee champions can't stick to a
# target for a whole fight (kiting, peel), so their auto count is discounted in
# long windows. Ranged classes keep full uptime. (Attack range isn't scraped,
# so class is the proxy.)
MELEE_AUTO_UPTIME = 0.75
# Titanic Hydra arms Cleave on a timer ("Every 1.75 second(s), your next attack
# deals..."), so the interval is a property of the item, not of the extraction.
CLEAVE_EVERY = 1.75
RANGED_CLASSES = {"Marksman", "Mage", "Enchanter"}
# Runes whose trigger requires sustained basic attacking; casters get 45% value.
AUTO_GATED_RUNES = {"Empowerment", "Lethal Tempo"}

# Runes whose value REQUIRES an ally beside you. Guardian only shields while
# "guarding allies within 350 units"; Font of Life heals "the lowest Health
# allied champion nearby". The engine simulates a 1v1, so it cannot see that
# condition and read them as a free shield/heal -- which is how a support
# keystone won the rune search on a solo jungler. Scaled by how much of a fight
# that role realistically spends next to an ally.
ALLY_GATED_RUNES = {"Guardian", "Font of Life"}
ALLY_UPTIME_BY_ROLE = {
    "Support": 0.90,   # glued to the carry: this is what the rune is designed for
    "Dragon": 0.75,    # botlane carry, usually with the support
    "Jungle": 0.30,    # alone in the jungle; only ganks and objectives
    "Baron": 0.25,     # solo lane
    "Mid": 0.30,
}


def _ally_uptime(name: str) -> float:
    return ALLY_UPTIME_BY_ROLE.get(CHAMP_ROLE.get(name, ""), 0.35)
CHAMP_CLASS: dict[str, str] = {c["name"]: c.get("class", "")
                               for c in _SITE.get("champions", [])}
CHAMP_ROLE: dict[str, str] = {c["name"]: c.get("role", "")
                              for c in _SITE.get("champions", [])}


def _mobility_profile(name: str) -> tuple[bool, bool]:
    """(needs_mobility, has_dash). A champion is mobility-reliant when it must
    fight at short / committed range with no safe poke: any melee, plus
    auto-attack marksmen (Graves, Lucian) who must stay in attack range. Ranged
    casters (mages, enchanters) keep their distance, so they value it less."""
    champ = CHAMPS.get(name, {})
    mechs = set(champ.get("mechanics") or [])
    cls = CHAMP_CLASS.get(name, "")
    melee = cls not in RANGED_CLASSES
    auto_marksman = cls == "Marksman" or "onHit" in mechs or "attackSpeed" in (champ.get("scalesWith") or [])
    ranged_caster = cls in ("Mage", "Enchanter")
    needs_mobility = (melee or auto_marksman) and not ranged_caster
    return needs_mobility, "dash" in mechs


def _auto_uptime(name: str, window: float, st: dict | None = None) -> float:
    if window <= 4.0:  # a burst combo happens at point blank either way
        return 1.0
    cls = CHAMP_CLASS.get(name, "")
    if cls in RANGED_CLASSES:
        return 1.0
    up = MELEE_AUTO_UPTIME
    # move speed lets a melee stick to its target -> more attacks land.
    if st is not None:
        up = min(0.93, up + st.get("bonusMs", 0.0) * 0.0016)
    return up


_ORDINALS = {"second": 2, "other": 2, "two": 2, "third": 3, "three": 3,
             "fourth": 4, "four": 4, "fifth": 5, "five": 5, "sixth": 6, "six": 6}


def every_n_share(name: str) -> tuple[float, bool]:
    """How often an everyNHit passive fires, and whether abilities feed it.

    Per-auto components were added to EVERY attack, including passives whose own
    evidence says "Every third attack deals an additional 13 (22% AD)" -- three
    times too much damage from a condition the extractor had already recorded
    and nothing read. Twelve champions state N; two more state it only in the
    prose, which is parsed here; six state neither and fall back to three, which
    is an assumption rather than a reading.
    """
    mech = next((m for m in FORMULAS.get(name, {}).get("mechanics") or []
                 if m.get("kind") == "everyNHit"), None)
    if not mech:
        return 1.0, False
    ev = str(mech.get("evidence") or "").lower()
    abilities_stack = "abilit" in ev
    n = mech.get("n")
    if isinstance(n, (int, float)) and n > 1:
        return 1.0 / n, abilities_stack
    for word, value in _ORDINALS.items():
        if f"every {word}" in ev:
            return 1.0 / value, abilities_stack
    digits = re.search(r"every\s+(\d+)", ev) or re.search(
        r"(\d+)\s+(?:consecutive\s+)?(?:attacks|hits|stacks)", ev)
    if digits and 1 < int(digits.group(1)) <= 10:
        return 1.0 / int(digits.group(1)), abilities_stack
    return 1.0 / 3.0, abilities_stack


def empower_limits(name: str) -> dict[str, int]:
    """Abilities that empower a LIMITED number of following attacks.

    Xin Zhao's Q empowers three and was applied to every auto of the fight. The
    count sits in the prose the extractor could not model, so it is read from
    there rather than curated per champion.
    """
    out: dict[str, int] = {}
    for slot, ab in (FORMULAS.get(name, {}).get("abilities") or {}).items():
        for u in ab.get("unmodeled") or []:
            m = re.search(r"empower\w*\s+(?:the\s+|his\s+|her\s+|their\s+)?next\s+"
                          r"(\w+)\s+(?:basic\s+)?attack", str(u), re.I)
            if not m:
                continue
            word = m.group(1).lower()
            out[slot] = max(1, _ORDINALS.get(word, 0) or (int(word) if word.isdigit() else 1))
    return out


def cooldown_relief(name: str) -> tuple[float, str]:
    """Seconds shaved off OTHER cooldowns per empowered hit, and the source slot.

    Xin Zhao's Q: "each attack reduces other ability cooldowns by 1s". Three
    empowered attacks per cast is three seconds off W, E and R every cycle.
    """
    for slot, ab in (FORMULAS.get(name, {}).get("abilities") or {}).items():
        for u in ab.get("unmodeled") or []:
            m = re.search(r"reduc\w*\s+(?:all\s+|his\s+|her\s+|their\s+)?other\s+"
                          r"(?:ability\s+)?cooldowns?\s+by\s+([\d.]+)\s*s", str(u), re.I)
            if m:
                return float(m.group(1)), slot
    return 0.0, ""


def _auto_split(st, target, phys_m, magic_m, giant, crit_ev, per_auto_comps, comp_dmg, per_auto_share=None):
    """One auto-attack's damage, split by type (physical / magic / true).

    Pre-doubleShot, pre-count: the caller scales by uptime and multiplies. Kept
    in one place so both rotation paths decompose autos identically.
    """
    a_phys = st["ad"] * crit_ev * phys_m * giant
    a_phys += st["onHitPhys"] * phys_m
    a_phys += (st["onHitPctCurrentHp"] * target["hp"] * 0.7
               + st["onHitPctMaxHp"] * target["hp"]) * phys_m
    a_phys += st["runeOnHitFlat"] * phys_m
    # Titanic Cleave arms every CLEAVE_EVERY seconds, not every auto, so only a
    # fraction of attacks carry it: faster attacks dilute it rather than scale it.
    if st["cleaveFlat"] or st["cleavePctBonusHp"]:
        cleave = st["cleaveFlat"] + st["cleavePctBonusHp"] * st["bonusHp"]
        a_phys += cleave * min(1.0, (1.0 / CLEAVE_EVERY) / max(st["as"], 0.1)) * phys_m
    a_magic = st["onHitMagic"] * magic_m
    k_phys, k_magic, k_true = _kit_per_auto(st, per_auto_comps, comp_dmg, per_auto_share)
    return a_phys + k_phys, a_magic + k_magic, k_true


_REPEAT_ON_HIT_CACHE: dict[str, bool] = {}


def repeats_on_hit(name: str) -> bool:
    """Whether this kit's on-hit component fires on EVERY attack.

    The distinction matters for anything that re-applies on-hits. Gwen's
    Thousand Cuts is on every auto, so re-applying it is real damage. Lux's
    Illumination is a MARK consumed by one attack and Diana's Moonsilver is
    every third, so re-applying those would invent damage the game does not
    give. `repeatedOnHitReliance` already draws exactly this line ("applies an
    on-hit effect ONCE" versus "over and over"), so it is reused rather than
    curated again here.
    """
    if name not in _REPEAT_ON_HIT_CACHE:
        value = False
        try:
            from web.advisor import profiles as _profiles
            value = _profiles.combat_profile(name).get("repeatedOnHitReliance") == "high"
        except Exception:
            value = False
        _REPEAT_ON_HIT_CACHE[name] = value
    return _REPEAT_ON_HIT_CACHE[name]


#: Verified attack speed ratios and per-level growth (data/champion_attack_speed.json).
#: A champion absent from here keeps the old behaviour: no level scaling at all.
AS_CURVE = (_load("champion_attack_speed.json") or {}).get("champions", {})


def attack_speed_ratio(name: str, fallback: float) -> float:
    """The champion's attack speed RATIO -- the number percentage bonuses
    multiply. Falls back to the scraped level-1 value, which is the same thing
    for any champion with no starting bonus attack speed."""
    entry = AS_CURVE.get(name) or {}
    value = entry.get("attackSpeedRatio")
    return float(value) if value else fallback


def level_as_bonus(name: str, level: int) -> float:
    """Bonus attack speed from LEVELS, as a fraction.

    Wild Rift kept League's curve, confirmed in game against Ekko, Akali, Lux
    and Fiddlesticks:

        bonus = growth * (L-1) * (0.7025 + 0.0175 * (L-1))

    Returns 0 for champions we have not measured, so their numbers do not move
    until someone reads the real values off the client.
    """
    growth = float((AS_CURVE.get(name) or {}).get("attackSpeedGrowth") or 0.0)
    if not growth or level <= 1:
        return 0.0
    return growth * (level - 1) * (0.7025 + 0.0175 * (level - 1))


_METRIC_CACHE: dict[str, str] = {}


def damage_metric(name: str) -> str:
    """Which axis this champion is actually judged on: burst, sustained, or
    durability.

    Everything used to be ranked on 8-second sustained damage, which is the
    wrong yardstick for half the roster and quietly favours attack-speed and
    on-hit items on champions who never fight that long. Measured on the right
    axis the engine already knows better: on BURST it prefers Luden's Echo over
    Nashor's Tooth for Ekko, Diana and Fiddlesticks, and only on SUSTAINED does
    that invert.

    Class decides, because that is what the axis means -- a mage or assassin
    wins by removing someone inside a few seconds, a bruiser or marksman by
    still swinging at second eight. The attack pattern overrides it for the
    on-hit casters (Teemo, Kennen) whose damage genuinely is repeated attacks.
    """
    if name not in _METRIC_CACHE:
        cls = CHAMP_CLASS.get(name, "")
        pattern = ""
        try:
            from web.advisor import profiles as _profiles
            pattern = _profiles.combat_profile(name).get("basicAttackPattern") or ""
        except Exception:
            pattern = ""
        if cls == "Tank":
            metric = "durability"
        elif pattern in ("basic-attack-carry", "repeated-attacks"):
            metric = "sustained"
        elif cls in ("Mage", "Assassin"):
            metric = "burst"
        else:
            metric = "sustained"
        _METRIC_CACHE[name] = metric
    return _METRIC_CACHE[name]


def _kit_per_auto(st, per_auto_comps, comp_dmg, per_auto_share=None):
    """The KIT's own on-hit components, split by type.

    Gwen's Thousand Cuts and Skip 'n Slash are on-hit effects the champion
    carries, not stats: an item that re-applies on-hits re-applies these too.
    Factored out of _auto_split so the extra-application path can charge the
    same damage without restating the loop.
    """
    p = m = t = 0.0
    for comp, _slot in per_auto_comps:  # empowered-auto kit components
        # A multiShot kit's shotgun is already modelled by doubleShotMult, which
        # scales the WHOLE auto (so pellets crit and carry on-hit -- the better
        # model). The passive tooltip describes the same pellets as a per-auto
        # AD ratio, so once extraction recovers it the shotgun counts TWICE:
        # Graves' bare kit jumped to 3629 damage. Prefer the mechanic; skip the
        # passive's redundant pure-AD restatement of it.
        if (st.get("doubleShotMult", 1.0) > 1.0 and _slot == "P"
                and all(r.get("stat") in ("ad", "bonusAd")
                        for r in comp.get("ratios") or [])):
            continue
        cd = comp_dmg(comp, 3) / max(int(_rank_val(comp.get("hits", 1), 3) or 1), 1)
        if per_auto_share is not None:
            cd *= per_auto_share(_slot)
        typ = comp["type"]
        if typ == "magic":
            m += cd
        elif typ == "true":
            t += cd
        else:
            p += cd
    return p, m, t


def _proc_split(st, target, phys_m, magic_m):
    """One-time procs (first-hit, %max-HP, rune procs, burst procs), by type."""
    once_p = st["firstHit"] * phys_m + st["procMaxHpPct"] * target["hp"] * phys_m
    for flat, ap_pct in [(p[0], p[1]) for p in st["runeProcs"]]:
        once_p += (flat + ap_pct * st["bonusAd"]) * phys_m
    once_m = 0.0
    for flat, ap_r in st["burstProcs"]:
        once_m += (flat + ap_r * st["ap"]) * magic_m
    return once_p, once_m


def _on_hit_bundle(st, target, phys_m, magic_m, kit=None):
    """One application of everything that fires ON HIT, by damage type.

    The attack itself is deliberately excluded: an effect that re-applies
    on-hits (Dusk and Dawn) repeats Nashor's, Wit's End and the %HP on-hits,
    not the auto-attack's own AD.

    `kit` carries the champion's OWN on-hit components (Gwen's Thousand Cuts,
    Skip 'n Slash). In game "apply on-hits" includes those, and excluding them
    was the conservative first cut: on an on-hit caster they are most of what
    a re-application is worth.
    """
    on_p = (st["onHitPhys"] + st["runeOnHitFlat"]
            + st["onHitPctCurrentHp"] * target["hp"] * 0.7
            + st["onHitPctMaxHp"] * target["hp"]) * phys_m
    on_m = st["onHitMagic"] * magic_m
    on_t = 0.0
    if kit:
        on_p += kit[0]
        on_m += kit[1]
        on_t += kit[2]
    return on_p, on_m, on_t


def _for_window(name: str, st: dict, window: float) -> dict:
    """The stat block as it averages over a fight of this length.

    A buff is up for its duration once per cooldown, so across a window it is
    worth its uptime rather than its peak. The DISPLAYED stat block is left
    alone -- the player really does have that attack speed while it runs -- and
    only the simulation averages.
    """
    timed = st.get("timedSteroids") or []
    if not timed or window <= 0:
        return st
    haste_m = 100 / (100 + st["haste"])
    as_lost = ad_lost = 0.0
    for s in timed:
        cd = max(0.5, (s["cooldownS"] or 12) * haste_m)
        casts = 1 + int(window / cd)
        uptime = min(1.0, (s["durationS"] * casts) / window)
        as_lost += s["asPct"] * (1 - uptime)
        ad_lost += s["adFlat"] * (1 - uptime)
    if not as_lost and not ad_lost:
        return st

    adj = dict(st)
    mechs = {m.get("kind"): m for m in FORMULAS.get(name, {}).get("mechanics") or []}
    know = FORMULAS.get(name, {}).get("knowledge") or {}
    if ad_lost:
        adj["bonusAd"] = max(0.0, st["bonusAd"] - ad_lost)
        adj["ad"] = adj["baseAd"] + adj["bonusAd"]
    if as_lost and not mechs.get("fixedAttackSpeed"):
        # Mirrors the attack-speed maths in resolve_stats, so they cannot drift.
        as_pct = max(0.0, st["baseAsPct"] - as_lost)
        if not mechs.get("reload"):
            as_pct *= know.get("asEfficiency") or 1
        adj["as"] = min(adj["baseAs"] * (1 + as_pct / 100.0), AS_CAP)
        if mechs.get("reload"):
            mag = float(mechs["reload"].get("magazine") or 2)
            reload_s = float(know.get("reloadSeconds") or 1.0)
            adj["as"] = mag / (mag / adj["as"] + reload_s)
    return adj


def rotation(name: str, st: dict, target: dict, window: float, level: int = 13) -> dict:
    """Damage dealt over `window` seconds: abilities on cooldown + autos."""
    st = _for_window(name, st, window)
    f = FORMULAS.get(name, {}).get("abilities", {})
    _cdr_per_hit, _cdr_slot = cooldown_relief(name)
    _limits = empower_limits(name)
    phys_m, magic_m = _mults(st, target)
    giant = 1 + st["giant"] * min(1.0, target["bonusHp"] / 1700)
    crit_ev = 1 + st["crit"] * (st["critMult"] - 1)
    haste_m = 100 / (100 + st["haste"])

    total = 0.0
    auto_dmg = 0.0  # damage gated by attacking: autos + on-hit + spellblade
    by_type = {"physical": 0.0, "magic": 0.0, "true": 0.0}
    # Damage per ability slot, so an effect that amplifies ONE ability (Axiom
    # Arcanist's ultimate, Smolder's per-ability empowerments) has something to
    # amplify. by_type alone cannot answer "how much of this was the ult".
    by_slot_dmg: dict[str, float] = {}
    parts: list[tuple[str, float]] = []
    cast_log: dict[str, dict] = {}
    casts_total = 0

    def add_t(dtype: str, amt: float) -> None:
        by_type[dtype] = by_type.get(dtype, 0.0) + amt

    def kit_amps(total_now: float) -> float:
        """Kit amplification: a percentage bonus on damage already counted.

        No per-ability formula can express these -- Amumu's Cursed Touch turns
        his own magic damage into extra true damage, Shadow Assassin adds magic
        to everything he does for 3 seconds. Values and the assumptions behind
        them live in data/kit_amps.json. Called on BOTH rotation paths: the
        short-window combo path returns early, and that is exactly the window a
        3-second burst amp is worth the most in."""
        added = 0.0
        for entry in (KIT_AMPS.get(name) or {}).get("amps", []):
            pct = _lvl_range(entry.get("pct", 0), level) / 100.0
            if not pct:
                continue
            slot = entry.get("slot")
            if slot:                                   # amplifies ONE ability
                src = by_slot_dmg.get(slot, 0.0)
            elif entry.get("appliesTo") == "all":
                src = total_now
            else:
                src = by_type.get(entry.get("appliesTo", "magic"), 0.0)
            # A stated duration is a real limit, not a guess: a 3s effect inside
            # an 8s fight earns three eighths of it.
            dur = entry.get("durationS")
            if dur:
                src *= min(1.0, float(dur) / max(window, 1e-9))
            bonus = src * pct
            if bonus:
                parts.append((f"kit amp ({entry.get('appliesTo', slot)})", bonus))
                add_t(entry.get("dealtAs", "magic"), bonus)
                added += bonus
        # Ultimate-only amplification (Axiom Arcanist): the slot breakdown is
        # what makes this expressible at all.
        if st["ultAmp"] and by_slot_dmg.get("4"):
            bonus = by_slot_dmg["4"] * st["ultAmp"]
            parts.append(("ult amp", bonus))
            add_t("magic", bonus)
            added += bonus
        # Procs gated on a condition the SIMULATION can check. Dark Harvest only
        # fires on a target below half health, so it is earned when this
        # champion's own damage in this window gets them there -- and skipped
        # when it does not, which is the whole difference between a kit that
        # farms souls and one that cannot.
        for pr in st["conditionalProcs"]:
            # How reliably does THIS champion get the target into proc range in
            # THIS window? Full credit once its own damage covers the threshold,
            # tapering below it. A hard on/off would be a cliff: Zed at 48% of a
            # squishy's health would score zero and Jhin at 52% full value, so a
            # 4% damage change would flip a keystone on and the item search
            # would chase that discontinuity.
            reach = (total_now + added) / max(target["hp"] * pr["need"], 1e-9)
            reach = min(1.0, reach)
            if reach <= 0:
                continue
            dmg = (pr["flat"] + pr["adRatio"] / 100.0 * st["bonusAd"]
                   + pr["apRatio"] / 100.0 * st["ap"])
            # "Adaptive" follows the build's dominant stat, like every other
            # adaptive source: magic on an AP build, physical on an AD one.
            dtype = pr["type"]
            if dtype == "adaptive":
                dtype = "magic" if st["ap"] >= st["bonusAd"] else "physical"
            dmg *= (magic_m if dtype == "magic" else phys_m) * reach
            parts.append(("Dark Harvest", dmg))
            add_t(dtype, dmg)
            added += dmg
        return added

    def comp_dmg(comp, rank) -> float:
        base = _scale_val(comp.get("base"), rank, level)
        if comp.get("when") == "dot total" and comp.get("durationS"):
            base *= float(comp["durationS"])
        val = base
        for r in comp.get("ratios") or []:
            stat, pct = r.get("stat"), _scale_val(r.get("pct", 0), rank, level) / 100.0
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
                by_slot_dmg[slot] = by_slot_dmg.get(slot, 0.0) + cd
                d += cd
            parts.append((f"[{slot}] {f[slot].get('name', slot)}", d))
            total += d
            casts_total += 1
        n_autos = max(n_autos_seq, int(window * st["as"] * 0.5))
        # Frequency of each per-auto component: a passive that fires every Nth
        # attack rides 1/N of them, and an ability that empowers N attacks per
        # cast rides N x its casts. Both were riding every attack.
        _share_p, _abilities_stack = every_n_share(name)
        _limits = empower_limits(name)

        def per_auto_share(slot, _n=None):
            if slot == "P":
                if not _abilities_stack or not n_autos:
                    return _share_p
                hits = sum(v["casts"] for v in cast_log.values())
                return min(1.0, _share_p * ((n_autos + hits) / n_autos))
            limit = _limits.get(slot)
            if limit and n_autos:
                casts = cast_log.get(slot, {}).get("casts", 0)
                if casts <= 0:
                    cds = (FORMULAS.get(name, {}).get("abilities", {})
                           .get(slot, {}).get("cooldowns") or 12)
                    cd = _rank_val(cds, 3) or 12
                    casts = max(1, 1 + int(window / max(0.5, cd * haste_m)))
                return min(1.0, (limit * casts) / n_autos)
            return 1.0
        a_phys, a_magic, a_true = _auto_split(st, target, phys_m, magic_m, giant,
                                              crit_ev, per_auto_comps, comp_dmg,
                                              per_auto_share)
        dsm = st.get("doubleShotMult", 1.0)
        auto = (a_phys + a_magic + a_true) * dsm * n_autos
        add_t("physical", a_phys * dsm * n_autos)
        add_t("magic", a_magic * dsm * n_autos)
        add_t("true", a_true * dsm * n_autos)
        total += auto
        auto_dmg += auto
        parts.append((f"autos x{n_autos}", auto))
        if st["spellbladeBaseAdPct"] or st["spellbladePctMaxHp"] or st["spellbladeApPct"]:
            procs = min(casts_total, n_autos, 1 + int(window / SPELLBLADE_CD))
            # Lich Bane is "75% base AD + 45% AP" and deals MAGIC damage; there
            # was no AP key at all, so its AP half was lost and the whole hit was
            # charged against armour. Type follows the item.
            _magic = st["spellbladeMagic"] > 0
            _m = magic_m if _magic else phys_m
            d = (st["spellbladeBaseAdPct"] / 100.0 * st["baseAd"]
                 + st["spellbladeApPct"] / 100.0 * st["ap"]
                 + st["spellbladePctMaxHp"] / 100.0 * target["hp"]) * _m * procs
            parts.append((f"spellblade x{procs}", d))
            add_t("magic" if _magic else "physical", d)
            total += d
            auto_dmg += d
            if st["extraOnHitApplications"]:
                _kit = (_kit_per_auto(st, per_auto_comps, comp_dmg, per_auto_share)
                        if repeats_on_hit(name) else None)
                _ep, _em, _et = _on_hit_bundle(st, target, phys_m, magic_m, _kit)
                _mult = st["extraOnHitApplications"] * procs
                _extra = (_ep + _em + _et) * _mult
                parts.append((f"extra on-hit x{procs}", _extra))
                add_t("physical", _ep * _mult)
                add_t("magic", _em * _mult)
                add_t("true", _et * _mult)
                total += _extra
                auto_dmg += _extra
        once_p, once_m = _proc_split(st, target, phys_m, magic_m)
        once = once_p + once_m
        if once:
            parts.append(("procs", once))
            add_t("physical", once_p)
            add_t("magic", once_m)
            total += once
        if st["dotDps"] or st["dotPctMaxHp"]:
            d = (st["dotDps"] + st["dotPctMaxHp"] * target["hp"]) * window * magic_m
            add_t("magic", d)
            total += d
        amp = 1 + st["damageAmp"]
        total += kit_amps(total)
        return {"total": total * amp, "parts": parts, "nAutos": n_autos, "bySlot": dict(by_slot_dmg),
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
        if _cdr_per_hit and slot != _cdr_slot and window > 0:
            # Seconds of cooldown removed across the window, spread evenly and
            # capped at halving, so a long fight cannot drive one to nothing.
            _empowered = _limits.get(_cdr_slot, 0)
            _src_cds = (f.get(_cdr_slot, {}) or {}).get("cooldowns") or 12
            _src_cd = max(0.5, (_rank_val(_src_cds, 3) or 12) * haste_m)
            _seconds = _cdr_per_hit * _empowered * (1 + int(window / _src_cd))
            cd = max(cd * 0.5, cd - _seconds / max(1.0, window / max(cd, 0.75)))
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
            by_slot_dmg[slot] = by_slot_dmg.get(slot, 0.0) + cd
            d += cd
        parts.append((f"[{slot}] {ab.get('name', slot)} x{casts}", d))
        total += d

    # autos
    n_autos = max(1, int(window * st["as"] * _auto_uptime(name, window, st)))
    # Frequency of each per-auto component: a passive that fires every Nth
    # attack rides 1/N of them, and an ability that empowers N attacks per
    # cast rides N x its casts. Both were riding every attack.
    _share_p, _abilities_stack = every_n_share(name)
    _limits = empower_limits(name)

    def per_auto_share(slot, _n=None):
        if slot == "P":
            if not _abilities_stack or not n_autos:
                return _share_p
            hits = sum(v["casts"] for v in cast_log.values())
            return min(1.0, _share_p * ((n_autos + hits) / n_autos))
        limit = _limits.get(slot)
        if limit and n_autos:
            casts = cast_log.get(slot, {}).get("casts", 0)
            if casts <= 0:
                cds = (FORMULAS.get(name, {}).get("abilities", {})
                       .get(slot, {}).get("cooldowns") or 12)
                cd = _rank_val(cds, 3) or 12
                casts = max(1, 1 + int(window / max(0.5, cd * haste_m)))
            return min(1.0, (limit * casts) / n_autos)
        return 1.0
    a_phys, a_magic, a_true = _auto_split(st, target, phys_m, magic_m, giant,
                                          crit_ev, per_auto_comps, comp_dmg,
                                          per_auto_share)
    dsm = st.get("doubleShotMult", 1.0)
    d_autos = (a_phys + a_magic + a_true) * dsm * n_autos
    add_t("physical", a_phys * dsm * n_autos)
    add_t("magic", a_magic * dsm * n_autos)
    add_t("true", a_true * dsm * n_autos)
    parts.append((f"autos x{n_autos}", d_autos))
    total += d_autos
    auto_dmg += d_autos

    # spellblade -- same maths as the rotation path above, which had gained the
    # AP half and the magic typing while this copy was left on the old model.
    if st["spellbladeBaseAdPct"] or st["spellbladePctMaxHp"] or st["spellbladeApPct"]:
        procs = min(casts_total, n_autos, 1 + int(window / SPELLBLADE_CD))
        _magic = st["spellbladeMagic"] > 0
        _m = magic_m if _magic else phys_m
        d = (st["spellbladeBaseAdPct"] / 100.0 * st["baseAd"]
             + st["spellbladeApPct"] / 100.0 * st["ap"]
             + st["spellbladePctMaxHp"] / 100.0 * target["hp"]) * _m * procs
        parts.append((f"spellblade x{procs}", d))
        add_t("magic" if _magic else "physical", d)
        total += d
        auto_dmg += d
        if st["extraOnHitApplications"]:
            _kit = (_kit_per_auto(st, per_auto_comps, comp_dmg, per_auto_share)
                    if repeats_on_hit(name) else None)
            _ep, _em, _et = _on_hit_bundle(st, target, phys_m, magic_m, _kit)
            _mult = st["extraOnHitApplications"] * procs
            _extra = (_ep + _em + _et) * _mult
            parts.append((f"extra on-hit x{procs}", _extra))
            add_t("physical", _ep * _mult)
            add_t("magic", _em * _mult)
            add_t("true", _et * _mult)
            total += _extra
            auto_dmg += _extra

    # one-time procs + burn
    once_p, once_m = _proc_split(st, target, phys_m, magic_m)
    once = once_p + once_m
    if once:
        parts.append(("procs", once))
        add_t("physical", once_p)
        add_t("magic", once_m)
        total += once
    if st["dotDps"] or st["dotPctMaxHp"]:
        d = (st["dotDps"] + st["dotPctMaxHp"] * target["hp"]) * window * magic_m
        parts.append(("burn", d))
        add_t("magic", d)
        total += d
    if st["graspPct"]:  # Grasp-style recurring %max-HP proc (magic)
        procs = 1 + int(window / st["graspEvery"])
        d = st["graspPct"] / 100.0 * target["hp"] * magic_m * procs
        parts.append((f"Grasp x{procs}", d))
        add_t("magic", d)
        total += d

    total += kit_amps(total)

    amp = 1 + st["damageAmp"]
    total *= amp
    n_autos_ideal = max(1, int(window * st["as"]))  # no uptime discount
    return {"total": total, "parts": parts, "nAutos": n_autos,
            "nAutosIdeal": n_autos_ideal, "castLog": cast_log, "bySlot": dict(by_slot_dmg),
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


def behavior_derived(name: str) -> dict:
    """The champion-behaviour metrics the engine can compute from the kit itself
    (grounded, no game knowledge): how often the champion casts, and whether its
    damage is front-loaded burst or spread out. These feed the scaling engine
    (e.g. high cast rate -> Manamune/Shojin worth more)."""
    f = (FORMULAS.get(name, {}) or {}).get("abilities", {}) or {}
    # spell cast rate: shorter basic-ability cooldowns -> more casts. ~2s -> 1.0,
    # ~12s -> ~0.1.
    cds = []
    for slot in ("1", "2", "3"):
        c = (f.get(slot) or {}).get("cooldowns")
        if c:
            cds.append(_rank_val(c, 3))
    avg_cd = (sum(cds) / len(cds)) if cds else 8.0
    spell_cast_rate = max(0.1, min(1.0, (13.0 - avg_cd) / 11.0))
    # fight length: front-loaded burst (most damage in the first 3s) means short
    # fights; sustained damage over the window means long ones. Measured on the
    # bare kit so it reflects the champion, not the build.
    try:
        st = resolve_stats(name, 13, [], [])
        sq = target_squishy(13)
        b3 = rotation(name, st, sq, 3.0, 13)["total"]
        d8 = rotation(name, st, sq, 8.0, 13)["total"] or 1.0
        burst_share = max(0.0, min(1.0, b3 / d8))
    except Exception:
        burst_share = 0.5
    return {"spellCastRate": round(spell_cast_rate, 2),
            "avgFightLength": round(1.0 - burst_share, 2)}


# Reference ally assumptions, used to price support output over one 8s fight.
SUPPORT_WINDOW = 8.0
ALLY_AUTOS = 8            # buffed ally basic attacks in the window
ALLY_DAMAGE = 2500.0      # damage a buffed ally deals in the window
ALLY_INCOMING = 2500.0    # damage an ally takes in the window
AP_TO_ALLY_DAMAGE = 2.5   # damage an ally gains per point of AP granted
AD_TO_ALLY_DAMAGE = 4.0
REF_SUP = 4000.0          # reference support output, for normalising the score


def support_value(name: str, item_slugs: list[str], rune_names: list[str] | None = None,
                  level: int = 13) -> float:
    """Ally value a build provides over a fight: the healing/shielding it puts on
    allies, plus the damage and mitigation its items hand them.

    An enchanter's entire job lives here. Without it the engine scores Soraka on
    her own damage and survival and picks nonsense, because every support item
    looks like a weak stat stick."""
    try:
        st = resolve_stats(name, level, item_slugs, rune_names or [])
    except Exception:  # noqa: BLE001
        return 0.0
    f = (FORMULAS.get(name, {}) or {}).get("abilities", {}) or {}
    amp = 1 + st["healShieldAmp"]
    haste_m = 100 / (100 + st["haste"])
    total = 0.0

    # 1) heals and shields this kit puts on ALLIES. A self-heal is not ally
    #    value: counting Swain's Demonic Ascension here gave him 255 points of
    #    support he never provided, while his own sustain read zero.
    total += kit_heal(name, st, level, SUPPORT_WINDOW, "ally")

    # 1b) ally healing/shielding from RUNES (Font of Life, Guardian). Without
    #     this the rune search is blind to a support page's whole point, which
    #     is why enchanter rune optimisation had to be blocked outright.
    total += st["runeAllyHealPerSec"] * SUPPORT_WINDOW * amp
    total += st["allyShield"] * amp

    # 2) what the items give allies
    for slug in item_slugs:
        fx = ENGINE_FX.get(slug) or {}
        g = lambda k: _lvl_range(fx[k], level) if k in fx else 0.0  # noqa: E731
        total += (g("allyHealFlat") + g("allyShieldFlat")) * 3 * amp  # a few casts/fight
        total += g("allyOnHitFlatMagic") * ALLY_AUTOS                 # Ardent Censer
        total += g("allyProcFlat") * 2                                # Imperial Mandate
        total += g("allyApFlat") * AP_TO_ALLY_DAMAGE                  # Staff of Flowing Water
        total += g("allyAdFlat") * AD_TO_ALLY_DAMAGE
        total += ALLY_DAMAGE * g("allyAmpPct") / 100.0
        total += ALLY_INCOMING * g("allyDrPct") / 100.0               # Knight's Vow
    return total


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
    # Kit self-healing counts toward staying alive, the same as lifesteal. It
    # used to be credited entirely as ally value, so a champion who sustains
    # through his own kit scored as though he had no sustain at all.
    r8 = rotation(name, st, TARGETS["bruiser"], 8.0, level)
    sustain = (st["vamp"] * dmg8 + st["runeHealPerSec"] * 8.0 * (1 + st["healShieldAmp"])
               + kit_heal(name, st, level, 8.0, "self", r8["bySlot"], r8["total"])
               + st["healOnHit"] * r8["nAutos"])

    return {"burst3": round(burst3), "dps8": round(dps8), "ttk": ttk,
            "ehp": round(ehp), "sustain": round(sustain),
            "support": round(support_value(name, item_slugs, rune_names, level)),
            "ad": round(st["ad"]), "ap": round(st["ap"]), "hp": round(st["hp"]),
            "armor": round(st["armor"]), "mr": round(st["mr"]),
            "moveSpeed": round(st["baseMs"] + st["bonusMs"]),
            "attackSpeed": round(st["as"], 2), "haste": round(st["haste"]),
            "crit": round(st["crit"] * 100), "mana": round(st["mana"])}


# How much of a build's worth is what it does for ALLIES. A protect enchanter is
# almost entirely this; a carry support partly; a solo-laner not at all.
def _support_weight(variant: str, name: str) -> float:
    cls = CHAMP_CLASS.get(name, "")
    if variant == "utility":
        return 0.65
    if cls == "Enchanter":
        return {"standard": 0.5, "survivability": 0.4, "poke": 0.15}.get(variant, 0.25)
    if CHAMP_ROLE.get(name, "") == "Support":
        return {"standard": 0.25, "survivability": 0.2}.get(variant, 0.0)
    return 0.0


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
    self_val = w_off * off + w_def * deff
    # For supports, what you do for allies IS the build's value. Blend it in so
    # Ardent/Redemption/Mandate can win on their real contribution instead of
    # being judged on the enchanter's own (irrelevant) damage.
    sup_w = _support_weight(variant, name) if name else 0.0
    if sup_w > 0:
        sup = m.get("support", 0) / REF_SUP
        return round(100 * ((1 - sup_w) * self_val + sup_w * sup), 1)
    return round(100 * self_val, 1)


# Approx Wild Rift gold per unit of every purchasable stat, so an item's raw
# stats can be priced. Passive value is NOT priced here — it flows through the
# battle score, which is exactly what lets a strong passive justify a
# stat-inefficient item (Sterak's on a mage, Shojin's amp, etc.).
STAT_GOLD = {
    "ad": 35.0, "ap": 21.75, "abilityHaste": 26.7, "hp": 2.67,
    "armor": 20.0, "mr": 20.0, "attackSpeed": 30.0, "crit": 40.0,
    "magicPen": 41.7, "physicalPen": 41.7, "lethality": 50.0,
    "magicPenFlat": 41.7, "physicalPenFlat": 50.0,
    "healShieldPower": 26.7, "physicalVamp": 40.0,
    "mana": 1.4, "moveSpeed": 13.0,
}
# Stats that occur as BOTH flat and percent under a single key: scales the
# percent value to its flat equivalent so one STAT_GOLD rate prices both. 1% MS
# is ~3.4 flat MS at a ~340 base. attackSpeed/crit are percent-ONLY, so their
# rate is already per-percent and they must not be listed here.
STAT_GOLD_PCT_SCALE = {"moveSpeed": 3.4}
# FinalScore = BattleScore * efficiency**ALPHA. Small alpha => an efficient item
# is barely touched, an inefficient one is nudged down but can still win on
# combat value. Never a ban.
EFFICIENCY_ALPHA = 0.5
# Efficiency scales the score, so an efficiency of exactly 0 multiplied it to 0:
# a hard ban, which the design explicitly rejects. It reached 0 whenever a
# champion could use NONE of an item's stats (Rabadon's on Aatrox, who has no AP
# ratios), and that zeroed the item's PASSIVE too, even though a passive is
# often the whole reason to buy. The floor keeps a passive able to argue for
# itself. Nothing is lost by being lenient here: the simulation already prices
# unusable stats at ~0 damage, so BattleScore rejects genuinely dead items on
# its own without efficiency needing to veto them.
EFFICIENCY_FLOOR = 0.05


# A meaningful increment of each offensive stat, used to probe its marginal
# value. Sized so each probe costs a comparable amount of gold.
# Defensive stats are probed too, not floored. Sizes are chosen so each probe
# costs a comparable amount of gold (see STAT_GOLD), which is what makes the
# per-gold comparison between, say, crit and armour meaningful.
PROBE = {"ad": 50.0, "ap": 80.0, "attackSpeed": 30.0, "crit": 25.0,
         "abilityHaste": 20.0, "magicPen": 10.0, "physicalPen": 10.0}
_MARGINAL_CACHE: dict[str, dict] = {}


def _offense_value(name: str, level: int, bonus: dict | None) -> float:
    """Damage composite used to price stats: sustained DPS plus all-in burst."""
    st = resolve_stats(name, level, [], [], bonus=bonus)
    d8 = rotation(name, st, TARGETS["bruiser"], 8.0, level)["total"] / 8.0
    b3 = rotation(name, st, target_squishy(level), 3.0, level)["total"] / 3.0
    return 0.6 * d8 + 0.4 * b3


def _fight_value(name: str, level: int, bonus: dict | None) -> float:
    """What a stat is worth ON THE SCALE fight_score actually optimises.

    Offense used to be MEASURED (and normalised so the champion's best stat =
    1.0) while defense was a hardcoded floor (hp .8 / armor .75 / mr .75) that
    was identical on every champion. Those two are not commensurable, and the
    normalisation made it worse: Graves' best offensive stat is physical pen, so
    everything else scaled below it and crit landed at 0.17 -- against an
    absolute 0.75 for armour. Armour therefore priced 4.5x more useful than crit
    TO A MARKSMAN, Sunfire out-scored Infinity Edge on efficiency, and every
    "standard" build drifted tank. Pricing both halves through the same
    objective removes the mismatch by construction rather than by tuning.
    """
    st = resolve_stats(name, level, [], [], bonus=bonus)
    squishy = target_squishy(level)
    dmg8 = rotation(name, st, TARGETS["bruiser"], 8.0, level)["total"]
    burst3 = rotation(name, st, squishy, 3.0, level)["total"]
    off = 0.6 * (dmg8 / 8.0) / REF_DPS + 0.4 * burst3 / REF_BURST

    shield = st["shield"] + st["shieldPctBonusHp"] * st["bonusHp"] + st["shieldPctMaxHp"] * st["hp"]
    shield *= 1 + st["healShieldAmp"]
    mixed_taken = 0.5 * 100 / (100 + st["armor"]) + 0.5 * 100 / (100 + st["mr"])
    ehp = (st["hp"] + shield) / mixed_taken / (1 - st["dr"] if st["dr"] < 1 else 1)
    _r8 = rotation(name, st, TARGETS["bruiser"], 8.0, level)
    sustain = (st["vamp"] * dmg8 + st["runeHealPerSec"] * 8.0 * (1 + st["healShieldAmp"])
               + kit_heal(name, st, level, 8.0, "self", _r8["bySlot"], _r8["total"]))
    deff = (ehp + 0.5 * sustain) / REF_DEF
    # standard's neutral 60/40: stat_weights is variant-independent, and this is
    # the blend "the best all-around build" is defined by.
    return 0.6 * off + 0.4 * deff


def stat_marginal_value(name: str, level: int = 13) -> dict:
    """MEASURED value of each offensive stat for this champion: add a probe of
    the stat, re-simulate, and price the damage it actually bought per gold.

    This replaces flag-guessing. Because it runs the real sim, it respects
    ratio MAGNITUDE (a token 5% AP ratio buys almost nothing), auto-reliance
    (crit is worthless if you rarely auto) and kit mechanics (Graves' reload
    caps attack speed; on-hit kits love it). Normalised so the champion's best
    offensive stat = 1.0."""
    if name in _MARGINAL_CACHE:
        return _MARGINAL_CACHE[name]
    try:
        base = _offense_value(name, level, None)
        raw = {}
        for stat, amt in PROBE.items():
            gain = max(0.0, _offense_value(name, level, {stat: amt}) - base)
            raw[stat] = gain / (amt * STAT_GOLD[stat])  # damage per gold
        mx = max(raw.values()) or 1.0
        out = {k: round(min(1.0, v / mx), 3) for k, v in raw.items()}
    except Exception:  # noqa: BLE001 — fall back to neutral if a kit won't sim
        out = {k: 0.5 for k in PROBE}
    _MARGINAL_CACHE[name] = out
    return out


def stat_usability(name: str) -> dict:
    """How much of each OFFENSIVE stat a champion's kit can use (0..1), from its
    ability ratios and scaling — NOT its class. An AP caster uses AP fully but
    AD only as far as it auto-attacks; an ADC is the reverse."""
    champ = CHAMPS.get(name, {})
    scales = set(champ.get("scalesWith") or [])
    mechs = set(champ.get("mechanics") or [])
    ratio_stats = set()
    for ab in (FORMULAS.get(name, {}).get("abilities") or {}).values():
        for c in ab.get("damage") or []:
            for r in c.get("ratios") or []:
                ratio_stats.add(r.get("stat"))
    has_ap = "ap" in ratio_stats or "ap" in scales
    has_ad = any(s in ratio_stats for s in ("ad", "bonusAd")) or any(s in scales for s in ("ad", "bonusAd"))
    autos = "attackSpeed" in scales or "onHit" in mechs or champ.get("primaryDamage") == "physical"
    ap_use = 1.0 if has_ap else 0.05
    ad_use = 1.0 if has_ad else (0.35 if autos else 0.05)  # AD only feeds autos w/o AD ratios
    as_use = 1.0 if autos else 0.15
    crit_use = 1.0 if (autos and (has_ad or "crit" in scales or champ.get("primaryDamage") == "physical")) else 0.0
    return {"ad": ad_use, "ap": ap_use, "attackSpeed": as_use, "crit": crit_use,
            "magicPen": ap_use, "physicalPen": ad_use, "lethality": ad_use}


def mana_pressure(name: str, level: int = 15, window: float = 8.0) -> float:
    """Fraction of the mana pool a full rotation burns in one fight, 0..1.

    Replaces a behaviour guess with the real numbers: per-ability mana costs and
    cooldowns are now scraped, so an ability spammer on a small pool (Hecarim
    casting Rampage every 3s) is separable from a champion who casts rarely or
    sits on a huge pool. That is what should make Manamune and mana regen worth
    buying, without naming any champion.

    0 for resourceless kits: they have no mana entry at all.
    """
    bs = (CHAMPS.get(name) or {}).get("baseStats") or {}
    m = bs.get("mana")
    if not m:
        return 0.0
    pool = m["base"] + m["perLevel"] * (level - 1)
    if pool <= 0:
        return 0.0
    drain = 0.0
    for a in ((WRMETA_CHAMPS.get(name) or {}).get("abilities") or []):
        costs, cds = a.get("manaCosts") or [], a.get("cooldowns") or []
        if not costs or not cds:
            continue
        cd = cds[-1]           # max rank: the state a build is judged in
        if cd > 0:
            drain += costs[-1] / cd
    return min(1.0, drain * window / pool)


def _support_stat_weight(name: str) -> float:
    """Usefulness of Heal and Shield Power. Derived from the kit, not a list: a
    champion who neither heals nor shields gains nothing from amplifying them."""
    rec = FORMULAS.get(name) or {}
    for ab in (rec.get("abilities") or {}).values():
        for d in ab.get("defensive") or []:
            if d.get("kind") in ("heal", "shield"):
                return 0.9
    return 0.1


def stat_weights(name: str) -> dict:
    """Per-champion usefulness (0..1) of EVERY item stat, for gold efficiency.

    Offensive stats come from kit scaling (stat_usability). Defensive stats keep
    a high universal weight — survival is real value on any champion, so this
    never punishes Guardian Angel / Sterak's / Randuin's. Haste helps everyone's
    abilities; mana is dead on resourceless kits."""
    # Offensive stats are PRICED BY MEASUREMENT (probe the sim), not by flags:
    # this is what stops a token AP ratio making AP "fully usable" on Graves, or
    # crit looking free on an ability bruiser like Hecarim. Kit mechanics are
    # respected because the probe runs the real rotation.
    u = stat_marginal_value(name)
    champ = CHAMPS.get(name, {})
    mechs = set(champ.get("mechanics") or [])
    no_resource = any(m.get("kind") == "noResource"
                      for m in FORMULAS.get(name, {}).get("mechanics") or [])
    mobile, has_dash = _mobility_profile(name)
    # short-range / committed champs (melee, or auto-attack marksmen like Graves,
    # Lucian) live in danger and need move speed to reposition, kite and stick.
    # Dash champs also value ability haste highly (more dashes = more mobility).
    ms_w = 0.75 if mobile else 0.45
    haste_w = 0.9 if has_dash else 0.85
    # Behaviour model (A3): a champion that casts a lot values ability haste and
    # mana more (Manamune/Shojin on Hecarim); one with long fights values mana as
    # a resource. Emergent from the metric, not a per-champion rule.
    beh = (FORMULAS.get(name, {}) or {}).get("behavior") or {}
    cast = beh.get("spellCastRate")
    if isinstance(cast, (int, float)):
        haste_w = min(1.0, haste_w + 0.15 * (cast - 0.5))   # +/- up to 0.075
    # Mana is priced by MEASURED drain now that costs and cooldowns are scraped.
    # Two things this fixes over the old cast-rate guess:
    #   - a champion with NO mana entry in baseStats is resourceless, full stop.
    #     The noResource mechanic is only extracted for some of them, so Viego,
    #     Sett and Aatrox were all being sold mana. The stat block is authority.
    #   - the cast-rate bump is gone rather than stacked on top: it was a proxy
    #     for exactly what mana_pressure now measures, so keeping both
    #     double-counted (it pushed Ziggs to 0.70 over a measured 0.40).
    has_mana = bool(((CHAMPS.get(name) or {}).get("baseStats") or {}).get("mana"))
    if no_resource or not has_mana:
        mana_w = 0.0
    else:
        mana_w = min(0.85, 0.15 + 0.9 * mana_pressure(name))
    # haste stays behaviour-driven: the probe quantises casts to whole numbers so
    # it under-reads haste, while cast-rate captures its real worth.
    return {
        "ad": u["ad"], "ap": u["ap"], "attackSpeed": u["attackSpeed"], "crit": u["crit"],
        "magicPen": u["magicPen"], "physicalPen": u["physicalPen"], "lethality": u["physicalPen"],
        # Flat variants mirror their percent twin. Without these they fall to the
        # 0.5 default in build_efficiency, which would price flat armor pen as
        # half-useful to EVERY champion (Malphite's % pen weight is 0.12).
        "physicalPenFlat": u["physicalPen"], "magicPenFlat": u["magicPen"],
        # Defensive weights stay FLOORED, and the reason is worth recording.
        # Measuring them through the same objective (see _fight_value) was tried
        # and made the tank drift WORSE, not better: HP came out as the best stat
        # on EVERY champion, Ziggs and Lucian included, and Sunfire's efficiency
        # went 0.78 -> 0.89 against Infinity Edge's 0.61 -> 0.40.
        #
        # That is not a weighting bug, it is the objective. fight_score is
        # ADDITIVE (w_off*off + w_def*deff), EHP is linear in HP, and HP costs
        # 2.67 gold/point against AD's 35 -- so per gold, defense really does buy
        # more of THIS score, and nothing in it models dying or contributing
        # nothing. A real fight is multiplicative (kill them before they kill
        # you); an additive sum cannot say that. Until the objective is fixed,
        # these floors are a deliberate counterweight, not a measurement.
        "abilityHaste": haste_w, "hp": 0.8, "armor": 0.75, "mr": 0.75,
        "mana": mana_w, "moveSpeed": ms_w,
        "healShieldPower": _support_stat_weight(name),
        # Physical vamp only converts damage you actually deal with attacks, so
        # it tracks how much of this kit's damage is physical autos.
        "physicalVamp": u["ad"] * 0.8,
    }


def build_efficiency(name: str, item_slugs: list[str]) -> float:
    """Fraction of a build's raw-stat gold that the champion's kit can use."""
    w = stat_weights(name)
    useful = total = 0.0
    for s in item_slugs:
        for k, v in ((ITEMS.get(s) or {}).get("stats") or {}).items():
            g = STAT_GOLD.get(k)
            if g is None:
                continue
            val = v.get("value", 0) if isinstance(v, dict) else v
            pct = v.get("percent", False) if isinstance(v, dict) else False
            # Some stats appear as BOTH flat and percent under one key, and the
            # flag was ignored: "+5% Move Speed" was priced as "+5 Move Speed",
            # a ~4x underprice. AS/crit are always percent, so their STAT_GOLD
            # rate is already per-percent and must not be rescaled here.
            if pct and k in STAT_GOLD_PCT_SCALE:
                val = (val or 0) * STAT_GOLD_PCT_SCALE[k]
            gold = g * (val or 0)
            total += gold
            useful += gold * w.get(k, 0.5)
    if total <= 0:
        return 1.0
    return max(useful / total, EFFICIENCY_FLOOR)


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

# Wild Rift is a fast game (15-20 min): the first drag/herald land at 6:00 and
# the 2nd-3rd item spikes usually decide games, so a build is scored across its
# whole purchase timeline, weighted heavily toward those early spikes rather
# than the theoretical full-6 inventory. (purchases in build order, weight).
EARLY_GAME_WEIGHTING = True
STAGE_PLAN = [(1, 0.10), (2, 0.30), (3, 0.35), (4, 0.15), (5, 0.07), (6, 0.03)]


def _build_order(items: list[str]) -> list[str]:
    """Item list in purchase order (boots bought 2nd), matching affordable()."""
    order = list(items)
    if len(order) >= 2:
        order = [order[0], order[-1]] + order[1:-1]
    return order


def _value(name: str, item_slugs: list[str], runes: list[str], variant: str,
           level: int, weights, fast: bool) -> float:
    """Battle score at a level, scaled by gold efficiency."""
    m = metrics(name, item_slugs, runes, level, fast=fast)
    eff = build_efficiency(name, [s for s in item_slugs if s in ITEMS])
    return fight_score(m, variant, name, weights) * (eff ** EFFICIENCY_ALPHA)


def _staged_score(name: str, items: list[str], runes: list[str], variant: str,
                  weights, fast: bool) -> float:
    """Early-game-weighted value: score the build at successive purchase stages
    and weight toward the first items that decide WR games."""
    order = _build_order(items)
    acc = tw = 0.0
    for n, w in STAGE_PLAN:
        prefix = order if n is None else order[:min(n, len(order))]
        if not prefix:
            continue
        lvl = PREFIX_LEVELS[min(len(prefix) - 1, len(PREFIX_LEVELS) - 1)]
        acc += w * _value(name, prefix, runes, variant, lvl, weights, fast)
        tw += w
    return acc / tw if tw else 0.0


def score_items(name: str, items: list[str], runes: list[str], variant: str,
                role: str = "", fast: bool = False,
                weights: tuple[float, float] | None = None,
                gold: float | None = None, level: int | None = None) -> dict:
    """Score an ordered item list (last slot = boots).

    Default: the early-game-weighted value across purchase stages (WR's first
    2-3 items decide games), reported alongside the full level-15 stats. When
    `gold` is given, only the affordable prefix is scored at that stage."""
    scored_items = items
    lvl = level or FULL_LEVEL
    if gold is not None:
        scored_items = affordable(items, gold)
        lvl = level or PREFIX_LEVELS[min(len(scored_items), len(PREFIX_LEVELS)) - 1]

    m = metrics(name, scored_items, runes, lvl, fast=fast)
    out = dict(m)
    # gold efficiency: scale the battle score by how much of the build's stat
    # gold the kit actually uses. An AP champ's AD items lose value, but a strong
    # passive still wins through the battle score. Identity via scaling, not class.
    eff = build_efficiency(name, [s for s in scored_items if s in ITEMS])
    if gold is None and level is None and EARLY_GAME_WEIGHTING:
        out["score"] = round(_staged_score(name, items, runes, variant, weights, fast), 1)
    else:
        out["score"] = round(fight_score(m, variant, name, weights) * (eff ** EFFICIENCY_ALPHA), 1)
    out["efficiency"] = round(eff, 3)
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
