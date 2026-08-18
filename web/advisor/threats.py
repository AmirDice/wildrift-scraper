"""Structured enemy-threat profiles for the counter builder.

The counter builder used to be handed a shallow per-enemy line -- class, damage
type, a list of mechanic tags -- and left to weigh them itself. That let a
low-damage magic tank and a high-damage magic carry count equally toward "magic
threat", which is exactly the mistake the plan calls out.

This module turns the enemy list into a categorical TEAM THREAT PROFILE and a
ranked list of PRIORITY THREATS, derived deterministically from our own champion
data (class, primary damage, mechanics, the derived combat profile, and the
site's win-rate/tier signal). It invents nothing: where a value cannot be
grounded it stays categorical and low-confidence rather than a fabricated
number. The model still decides which threats to answer -- this only gives it an
honest, weighted picture to reason over.
"""
from __future__ import annotations

import json
from pathlib import Path

from web.advisor import profiles

ROOT = Path(__file__).resolve().parent.parent.parent
DATA = ROOT / "data"


def _load(name: str, default=None):
    for base in (DATA, ROOT):
        path = base / name
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return default


_SITE = _load("web-next/src/data/site.json", {}) or {}
_SITE_BY_NAME = {
    c["name"]: c for c in (_SITE.get("champions") if isinstance(_SITE, dict) else _SITE) or []
}

# How much each class contributes to raw damage threat. A tank on the enemy team
# is a durability problem, not a damage one; a marksman is the opposite. Without
# this weighting, "three magic champions" reads as heavy magic threat even when
# two of them are tanks who barely deal damage.
_DAMAGE_WEIGHT = {
    "Marksman": 1.0, "Assassin": 1.0, "Mage": 1.0,
    "Bruiser": 0.6, "Fighter": 0.6,
    "Tank": 0.25, "Enchanter": 0.2,
    "": 0.5,
}

# Categorical ladder, low to high. Used everywhere a level is reported.
_LEVELS = ["none", "low", "low_medium", "medium", "high", "very_high"]


def _level(score: float) -> str:
    """Map a 0..1-ish accumulated score onto the categorical ladder."""
    if score <= 0:
        return "none"
    if score < 0.5:
        return "low"
    if score < 1.0:
        return "low_medium"
    if score < 1.8:
        return "medium"
    if score < 2.8:
        return "high"
    return "very_high"


def _champ(name: str) -> dict:
    record = dict(profiles.CHAMPIONS.get(name) or {})
    site = _SITE_BY_NAME.get(name) or {}
    # class/role live in site.json, not the raw champion scrape.
    record.setdefault("class", site.get("class") or "")
    record.setdefault("role", site.get("role") or "")
    record["_wr"] = site.get("wr")
    record["_tier"] = site.get("tier")
    return record


def _combat(name: str) -> dict:
    try:
        return profiles.combat_profile(name)
    except Exception:  # noqa: BLE001
        return {}


def _has(record: dict, mech: str) -> bool:
    return mech in (record.get("mechanics") or [])


def team_threat_profile(enemies: list[str]) -> dict:
    """A categorical threat picture of the whole enemy team."""
    records = [(_champ(e), _combat(e)) for e in enemies]

    # The level thresholds are tuned for a full five-enemy team. A partial
    # comp accumulates less by construction -- three enemies who ALL shield
    # top out at 1.5, which read as "medium" while being the most
    # shield-saturated answer three picks can give. Scaling by 5/n makes the
    # profile describe the KNOWN enemies as a group: "if the team is like
    # what you have named, this is what it is like". A full comp is
    # unchanged (factor 1).
    scale = 5.0 / max(1, len(records))

    phys = magic = true_dmg = 0.0
    basic_dps = burst = extended = crit = on_hit = 0.0
    hard_cc = slows = displace = 0.0
    healing = shielding = 0.0
    durable = 0

    for rec, cp in records:
        cls = rec.get("class", "")
        weight = _DAMAGE_WEIGHT.get(cls, 0.5)
        dmg = rec.get("primaryDamage", "")
        if dmg == "physical":
            phys += weight
        elif dmg == "magic":
            magic += weight

        pattern = cp.get("basicAttackPattern", "")
        if pattern in ("basic-attack-carry", "repeated-attacks"):
            basic_dps += weight
            extended += weight
        if cp.get("critValue") == "high":
            crit += weight
        if cp.get("repeatedOnHitReliance") in ("medium", "high"):
            on_hit += weight
        if cls in ("Assassin", "Mage") and pattern in ("caster", "ability-weaving"):
            burst += weight

        if _has(rec, "cc"):
            hard_cc += 0.7
            slows += 0.4
        if _has(rec, "dash"):
            displace += 0.4
        if _has(rec, "heal") or cp.get("healingReliance") in ("medium", "high"):
            healing += 0.6 if cls in ("Enchanter",) else 0.4
        if _has(rec, "shield"):
            shielding += 0.5
        if cls in ("Tank", "Bruiser", "Fighter"):
            durable += 1

    def lv(score: float) -> str:
        return _level(score * scale)

    return {
        "physicalDamage": lv(phys),
        "magicDamage": lv(magic),
        "trueDamage": lv(true_dmg),
        "basicAttackDps": lv(basic_dps),
        "abilityBurst": lv(burst),
        "extendedFightDps": lv(extended),
        "criticalStrikeThreat": lv(crit),
        "onHitThreat": lv(on_hit),
        "hardCc": lv(hard_cc),
        "slows": lv(slows),
        "displacement": lv(displace),
        "healing": lv(healing),
        "shielding": lv(shielding),
        "durableTargetCount": durable,
        "armorStackingLikelihood": lv(durable * 0.7) if durable else "low",
        "healthStackingLikelihood": lv(durable * 0.9) if durable else "low",
    }


# Tier -> a severity floor. A GOD/S enemy is a bigger problem than a C one even
# before looking at its kit, because it is winning its lane harder.
_TIER_SEVERITY = {"GOD": 0.9, "S": 0.8, "A": 0.6, "B": 0.45, "C": 0.3, "D": 0.2}


def _wr_severity(wr: float | None, tier: str) -> float:
    """Base severity from the enemy's measured meta win rate.

    The tier buckets above were the whole signal, and a bucket is a coarse
    read of the number we actually have: a 55.7% Nilah and a 52.1% champion
    could share a tier and read as identical threats. The measured win rate
    (site.json, the same figure the tier list prints) maps linearly onto the
    old bucket range -- 46% reads like a D-tier threat, 60% past GOD -- so
    the scale the rest of severity was tuned against is unchanged. The tier
    bucket stays as the fallback for champions with no board yet.
    """
    if wr is None:
        return _TIER_SEVERITY.get(tier, 0.4)
    return round(max(0.2, min(0.95, 0.2 + (float(wr) - 46.0) * 0.05)), 3)


_RANGED_CLASSES = {"Mage", "Marksman", "Enchanter"}


def lane_matchup(me: str, my_role: str, enemies: list[str]) -> dict | None:
    """The enemy you actually lane against, with the signals that decide runes.

    The team profile treats the enemies as one aggregate, which is right for
    items and wrong for the rune page: runes are bought for the laning phase,
    and the laning phase is ONE specific opponent hitting you every time you
    step up to a minion. Role-matching finds that opponent; the combat profile
    says what kind of lane they run. Returns None when the opponent cannot be
    identified unambiguously -- saying nothing beats guessing."""
    if not my_role:
        return None
    matches = [e for e in enemies if (_champ(e).get("role") or "") == my_role]
    if len(matches) != 1:
        return None
    enemy = matches[0]
    rec, cp = _champ(enemy), _combat(enemy)
    me_class = _champ(me).get("class") or ""
    ranged_into_melee = (rec.get("class") in _RANGED_CLASSES
                         and me_class not in _RANGED_CLASSES)
    sustained_harass = (
        (cp.get("basicAttackPattern") in ("repeated-attacks", "basic-attack-carry")
         and cp.get("basicAttackFrequency") in ("medium", "high"))
        or rec.get("class") == "Mage")
    burst_all_in = rec.get("class") == "Assassin" or (
        rec.get("class") in ("Bruiser", "Fighter")
        and cp.get("basicAttackPattern") in ("caster", "ability-weaving"))
    return {
        "enemy": enemy,
        "class": rec.get("class") or "?",
        "damage": rec.get("primaryDamage") or "?",
        "tier": rec.get("_tier"),
        "metaWinrate": rec.get("_wr"),
        "rangedIntoMelee": ranged_into_melee,
        "sustainedHarass": sustained_harass,
        "burstAllIn": burst_all_in,
        "hardCc": _has(rec, "cc"),
    }


def priority_threats(enemies: list[str], me: str = "") -> list[dict]:
    """The enemies most worth building against, ranked by severity.

    Severity blends the champion's tier/win-rate signal with how much damage its
    class contributes: a fed-tier carry outranks a support of the same tier.
    """
    out = []
    for name in enemies:
        rec = _champ(name)
        cp = _combat(name)
        cls = rec.get("class", "")
        tier = str(rec.get("_tier") or "")
        base = _wr_severity(rec.get("_wr"), tier)
        contribution = _DAMAGE_WEIGHT.get(cls, 0.5)
        severity = round(min(1.0, base * (0.5 + contribution / 2)), 2)

        threats: list[str] = []
        itemizable: list[str] = []
        non_item: list[str] = []
        pattern = cp.get("basicAttackPattern", "")
        if pattern in ("basic-attack-carry", "repeated-attacks"):
            threats.append("basic_attack_dps")
            itemizable += ["armor" if rec.get("primaryDamage") == "physical" else "magic_resist",
                           "anti_basic_attack"]
            threats.append("extended_fight")
        if cls == "Assassin":
            threats.append("burst")
            itemizable.append("burst_survival")
            non_item.append("hold a defensive summoner or ability for the all-in")
        if _has(rec, "dash") or cls == "Assassin":
            threats.append("target_access")
            non_item.append("keep vision and position so the gap-close is punished")
        if _has(rec, "heal") or cp.get("healingReliance") in ("medium", "high"):
            threats.append("healing")
            itemizable.append("grievous_wounds")
        # Shielding was counted in the TEAM profile and then dropped here, so
        # the model saw "shielding: high" as a bare categorical and never a
        # threat it could answer. Against Karma, Lee Sin, Lulu and Sivir it
        # itemised magic resist and never considered shield reduction, which is
        # the response this list exists to name.
        if _has(rec, "shield"):
            threats.append("shielding")
            itemizable.append("shield_reduction")
        if _has(rec, "cc"):
            threats.append("crowd_control")
            itemizable.append("tenacity")
            non_item.append("bait the key cc before committing")

        damage_contribution = ("high" if contribution >= 0.9
                               else "medium" if contribution >= 0.55 else "low")
        out.append({
            "champion": name,
            "severity": severity,
            # the measured number behind the ranking, so the model can weigh
            # "how fed is this pick right now" instead of trusting a bare score
            "metaWinrate": rec.get("_wr"),
            "damageContribution": damage_contribution,
            "threats": sorted(set(threats)) or ["general_pressure"],
            "itemizableResponses": sorted(set(itemizable)),
            "nonItemResponses": non_item,
        })
    out.sort(key=lambda t: t["severity"], reverse=True)
    return out


def hard_counter_warning(me: str, enemy: str, wrmeta: dict) -> dict | None:
    """A structured hard-counter note: what items can answer, what gameplay must.

    A hard counter is EVIDENCE, not an instruction to dump three slots into one
    enemy, so the structure separates the itemizable part from the part that is
    only answerable in-game.
    """
    hard = (wrmeta.get(me) or {}).get("hardCounters") or []
    if enemy not in hard:
        return None
    rec = _champ(enemy)
    cp = _combat(enemy)
    itemizable, non_item, reasons = [], [], []
    if cp.get("basicAttackPattern") in ("basic-attack-carry", "repeated-attacks"):
        reasons.append("out-sustains you in a prolonged auto-attack fight")
        itemizable.append("armor / anti-basic-attack")
    if rec.get("class") == "Assassin":
        reasons.append("bursts you before you can commit your rotation")
        itemizable.append("one burst-survival item")
        non_item.append("do not face-check; make it engage into your cooldowns")
    if not reasons:
        reasons.append("wins the matchup on kit; itemise partially, do not over-invest")
    return {
        "champion": enemy,
        "severity": "high",
        "reasons": reasons,
        "itemizableThreats": itemizable,
        "nonItemizableThreats": non_item or ["primarily a gameplay problem, not an item problem"],
    }
