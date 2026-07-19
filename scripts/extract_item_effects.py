"""Extract engine-usable numeric effects from item passives (LLM, grounded).

Converts each item's passive text (data/items.json) into the fight engine's
effect vocabulary (procs, penetration, conversions, amps, sustain). Numbers are
grounding-checked against the source text: the model transcribes, never invents.

Output: data/item_engine.json  { slug: {effect: value, ...} }

Run:
    python -m scripts.extract_item_effects
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from collections import Counter
from itertools import combinations
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
ITEMS = ROOT / "data" / "items.json"
OUT = ROOT / "data" / "item_engine.json"

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-v4-flash"
BATCH = 10

# effect -> short doc. All percents are given as plain numbers (12 = 12%).
VOCAB = {
    "spellbladeBaseAdPct": "next auto after ability: bonus physical = X% BASE AD",
    "spellbladeApPct": "...and X% of your AP on that same spellblade hit (Lich Bane's "
                       "'75% base AD + 45% AP'). There was no key for this, so the AP "
                       "half was being lost or hacked into burstProcApPct.",
    "spellbladePctMaxHp": "next auto after ability: bonus = X% target max HP "
                          "(MELEE value if melee/ranged differ)",
    "spellbladePctMaxHpRanged": "the RANGED %-of-HP value when both are listed "
                                "(Divine Sunderer's '10% melee / 7% ranged')",
    "onHitFlatPhys": "every auto: +X flat physical",
    "onHitFlatMagic": "every auto: +X flat magic",
    "onHitPctCurrentHp": "EVERY auto: X% target CURRENT HP (MELEE value if it varies)",
    "onHitPctCurrentHpRanged": "the RANGED %-OF-HP VALUE of onHitPctCurrentHp, ONLY when "
                               "the text lists two HP percentages "
                               "(e.g. '10% Melee / 8.5% Ranged'). It is NOT a damage "
                               "multiplier: 'ranged champions deal 40% of the damage' is "
                               "a scaling of the whole effect, NOT 40% of max HP. If you "
                               "see that phrasing, do not use this key.",
    "onHitPctMaxHp": "EVERY auto: X% target MAX HP (MELEE value if it varies)",
    "onHitPctMaxHpRanged": "the RANGED %-OF-HP VALUE of onHitPctMaxHp. Same warning as "
                           "onHitPctCurrentHpRanged: never use it for 'ranged deal X% of "
                           "the damage'.",
    "everyNthAttack": "N: the effect below fires on every Nth attack, not every auto "
                      "('Every 4th attack...'). Required whenever the text says so.",
    "everyNthBaseAdPct": "that Nth attack deals X% BASE AD as bonus damage",
    "everyNthPctMaxHp": "...plus X% of the target's MAX HP",
    "everyNthRangedMult": "ranged champions deal only X% OF THAT PROC's damage "
                          "('ranged champions deal 40% of the damage' -> 40)",
    "procMaxHpPct": "once per combo/target: X% target max HP damage",
    "firstHit": "one-time flat bonus on first hit vs champion",
    "burstProcFlat": "one-time proc damage, flat",
    "burstProcApPct": "one-time proc damage, X% AP ratio",
    "dotDps": "burn aura/passive: flat damage per second",
    "executePct": "finishes targets below X% HP",
    "giantSlayerPct": "up to X% bonus damage vs high-HP targets",
    "flatPen": "flat armor penetration (lethality)",
    "pctPen": "X% armor penetration",
    "armorShredPct": "X% armor REDUCTION (stacks debuff)",
    "critMult": "sets crit damage multiplier to X (e.g. 2.0)",
    "abilityAmpPct": "abilities deal +X% damage (assume max stacks)",
    "damageAmpPct": "ALL damage dealt +X% (assume max stacks/condition met)",
    "adFromManaPct": "gain AD = X% max mana",
    "apFromManaPct": "gain AP = X% max mana (Archangel's / Seraph's 'Awe')",
    "hpFromManaPct": "gain bonus HP = X% max mana (Winter's Approach 'Awe')",
    "apFromBonusHpPct": "gain AP = X% bonus HP",
    "apAmpPct": "MULTIPLIES your total Ability Power by +X% (Rabadon's 'Overkill'). "
                "This is a multiplier on everything, not flat AP.",
    "mrShredPct": "X% MAGIC RESIST reduction on the target (magic twin of armorShredPct)",
    "mrShredFlat": "flat MAGIC RESIST reduction on the target (Abyssal Mask 'Unmake')",
    "hastePctPassive": "reduces spell cooldowns by X% (Ionian Boots). A percent, "
                       "NOT flat ability haste.",
    "cdRefundPctPerAuto": "each attack cuts remaining ability cooldowns by X% "
                          "(Navori 'Deft Strikes')",
    "cleaveFlat": "every few seconds your next attack deals +X bonus physical",
    "cleavePctBonusHp": "...plus X% of your BONUS HP (Titanic Hydra 'Cleave')",
    "msFlat": "flat move speed from passive (average uptime)",
    "msPct": "X% move speed from passive (average uptime)",
    "adFlatPassive": "flat AD from passive (assume max stacks). NOT for Adaptive.",
    "apFlatPassive": "flat AP from passive (assume max stacks). NOT for Adaptive.",
    "adaptiveAdFlat": "ADAPTIVE passive ('Gain 25 Attack Damage OR 50 Ability Power'): "
                      "put the AD number here and the AP number in adaptiveApFlat. The "
                      "champion receives ONLY ONE; the engine picks. Never use "
                      "adFlatPassive/apFlatPassive for an Adaptive line.",
    "adaptiveApFlat": "ADAPTIVE passive: the AP number (pairs with adaptiveAdFlat).",
    "asPctPassive": "X% ATTACK SPEED from a passive, not the stat line "
                    "(Guinsoo's 32% at 4 stacks, Youmuu's 25%). Assume max stacks.",
    "critDamagePerExcessCrit": "X bonus Critical Damage per 1% crit above 100% "
                               "(Infinity Edge Limit Break)",
    "hasteFlatPassive": "flat ability haste from passive",
    # --- Captured but NOT yet simulated. Transcribing is the expensive part, so
    # record them now; the engine ignores them until it models what they need.
    # Do not mistake their presence for coverage.
    "grievousWoundsPct": "applies X% Grievous Wounds (anti-heal). INERT: no target "
                         "profile models healing yet.",
    "extraBolts": "attacks hit N ADDITIONAL nearby enemies (Runaan's). INERT: the "
                  "sim is single-target.",
    "extraBoltAdPct": "each extra bolt deals X% AD. INERT: see extraBolts.",
    "physVampPct": "X% physical vamp",
    "omnivampPct": "X% omnivamp",
    "lifestealPct": "X% lifesteal",
    "healOnHitFlat": "flat heal per auto",
    "shieldPctMaxHp": "lifeline-style shield = X% max HP (count once)",
    "shieldFlat": "lifeline-style flat shield (count once)",
    "reviveHpPct": "on lethal damage, revive with X% of max Health (Guardian Angel)",
    "hpFlatPassive": "flat max HP from passive stacking (assume max)",
    # --- ALLY / SUPPORT effects: an enchanter's entire value lives here. Without
    # these keys the engine sees Ardent Censer as a plain stat stick.
    "allyHealFlat": "heals an ALLY (or allies) for X per cast/active",
    "allyShieldFlat": "shields an ALLY (or allies) for X",
    "allyOnHitFlatMagic": "buffed ally's ATTACKS deal +X bonus magic damage (Ardent Censer)",
    "allyProcFlat": "ally damage detonates a mark for X bonus damage (Imperial Mandate)",
    "allyAsPct": "grants allies +X% attack speed",
    "allyApFlat": "grants allies +X ABILITY POWER as a stat (Staff of Flowing Water)",
    "allyAdFlat": "grants allies +X attack damage as a stat",
    "allyAmpPct": "allies deal +X% MORE damage (a multiplier, not flat)",
    "allyDrPct": "reduces damage an ally takes by X% (Knight's Vow)",
    "healShieldAmpPct": "YOUR heals and shields are X% stronger",
    "allyMsPct": "grants allies +X% move speed",
}

SYSTEM = (
    "You transcribe Wild Rift ITEM PASSIVES into a fixed numeric vocabulary for a damage "
    "engine. NEVER INVENT: every number must appear in the passive text, or be computed "
    "from numbers in it exactly as these rules direct (a max-stack total like 8+4=12, or "
    "a percent written as a multiplier like 205% -> 2.05). Percents are otherwise "
    "plain numbers (12 means 12%). Use ONLY these keys:\n"
    + "\n".join(f"  {k}: {v}" for k, v in VOCAB.items())
    + "\nRules:\n"
    "- Take the MAX-STACKS / condition-met value when a passive stacks or ramps.\n"
    "- If a value has melee/ranged variants (e.g. '10% Melee / 8.5% Ranged'), put the MELEE "
    "number in the base key AND the RANGED number in its \"...Ranged\" companion key when one "
    "exists. Never drop the ranged value: the engine picks per champion.\n"
    "- Skip slows, CC, vision and gold passives: put a 3-6 word note in \"skip\".\n"
    "- A REVIVE (Guardian Angel) is survivability, not a skip: use reviveHpPct.\n"
    "- DO capture ALLY/SUPPORT effects, including ACTIVES that heal or shield allies "
    "(Redemption, Locket, Mikael's) and buffs your heal/shield grants an ally (Ardent "
    "Censer, Staff of Flowing Water). These are the whole point of a support item — "
    "never skip them. Only skip an active if it grants no heal/shield/buff/damage.\n"
    "- Champion-level scaling values (e.g. '10-180 based on level'): use the level-13 "
    "value if computable from the two endpoints ((lo+hi*12/14) rounded) is NOT allowed — "
    "instead output {\"lvlRange\": [lo, hi]} for that key, e.g. \"firstHit\": {\"lvlRange\": [30, 180]}.\n"
    '- Return ONLY JSON: {"<slug>": {"<effectKey>": number | {"lvlRange":[lo,hi]}, ..., '
    '"skip": "optional note"}, ...} with one entry per given item.'
)


def _numbers_in(text: str) -> set[str]:
    toks = set()
    for m in re.findall(r"\d+(?:\.\d+)?", text):
        toks.add(m)
        try:
            f = float(m)
            if f == int(f):
                toks.add(str(int(f)))
        except ValueError:
            pass
    return toks


def _norm(x: float) -> str:
    return str(int(x)) if float(x) == int(x) else str(x).rstrip("0").rstrip(".")


# Keys whose value is a MULTIPLIER, so "205%" legitimately becomes 2.05. Every
# other key is a plain percent (12 means 12%), and allowing the /100 derivation
# for them let the model quietly divide by 100: Sundered Sky's "160% damage"
# became firstHit 1.6 (1.6 flat damage) and its 125%-base-AD HEAL became
# spellbladeBaseAdPct 1.25. Both grounded, both nonsense.
MULTIPLIER_KEYS = {"critMult"}


def _grounded_num(v: float, allowed: set[str], key: str | None = None) -> bool:
    """Is `v` justified by the passive text?

    Verbatim-only was too strict, and it silently contradicted our own prompt.
    We ASK the model to report max-stack totals and to express crit damage as a
    multiplier, then rejected exactly those answers:
        Bloodthirster  physVampPct 12  = 8 + 4      (text has 8, 4)
        Mortal Reminder pctPen      36  = 30 + 6     (text has 30, 6)
        Infinity Edge  critMult   2.05 = 205 / 100  (text has 205)
    All three were correct and all three were deleted. So accept a value the
    text *derives* by the arithmetic we requested: verbatim, percent->multiplier,
    a sum of listed numbers (stacking), or a listed number times a small integer
    (N stacks). Anything else is still rejected as invented.
    """
    if _norm(v) in allowed:
        return True
    # round(): 2.05 * 100 is 205.00000000000003 in binary float, which stringifies
    # to a value that matches nothing and silently sank Infinity Edge.
    # Restricted to MULTIPLIER_KEYS: this derivation is only legitimate where the
    # key IS a multiplier, and unrestricted it just licensed dividing by 100.
    if key in MULTIPLIER_KEYS and _norm(round(v * 100, 6)) in allowed:
        return True
    nums = sorted({float(x) for x in allowed})
    for r in (2, 3):                                 # 8 + 4, 30 + 6
        for combo in combinations(nums, r):
            if abs(sum(combo) - v) < 1e-6:
                return True
    for a in nums:                                   # 6 x 5 stacks = 30
        for k in range(2, 11):
            if abs(a * k - v) < 1e-6:
                return True
    return False


def _clean_fx(it: dict, fx: dict) -> dict:
    """Keep only vocabulary keys whose numbers the passive text justifies."""
    allowed = _numbers_in(" ".join(it["passives"]))
    clean = {}
    for k, v in fx.items():
        if k == "skip" or k not in VOCAB:
            continue
        if isinstance(v, dict) and "lvlRange" in v:
            if all(_grounded_num(float(x), allowed, k) for x in v["lvlRange"]):
                clean[k] = v
        elif isinstance(v, (int, float)) and _grounded_num(float(v), allowed, k):
            clean[k] = v
    return clean


def extract_batch(key: str, batch: list[dict], samples: int = 3) -> dict:
    """Sample the model several times and UNION the grounded results.

    One pass is not reproducible: on identical input, consecutive runs returned
    Bloodthirster's physVampPct, then nothing; BotRK's omnivampPct, then not.
    That is how Graves' reload vanished earlier. Because every value is
    grounding-checked independently, a union can only add real effects, never
    invent one -- so more samples strictly improves recall. Ties on a key's
    value go to the most frequent answer.
    """
    by_slug = {it["slug"]: it for it in batch}
    votes: dict[str, dict[str, list]] = {}
    for _ in range(samples):
        try:
            raw = call_llm(key, batch)
        except Exception as e:  # noqa: BLE001
            print(f"    ! sample failed: {e}")
            continue
        for slug, fx in raw.items():
            it = by_slug.get(slug)
            if not it or not isinstance(fx, dict):
                continue
            for k, v in _clean_fx(it, fx).items():
                votes.setdefault(slug, {}).setdefault(k, []).append(v)

    out = {}
    for it in batch:
        slug = it["slug"]
        picked = {}
        for k, vals in (votes.get(slug) or {}).items():
            common = Counter(json.dumps(v, sort_keys=True) for v in vals).most_common(1)
            picked[k] = json.loads(common[0][0])
        out[slug] = picked
    return out


def call_llm(key: str, batch: list[dict]) -> dict:
    lines = [f"{it['slug']}: {' '.join(it['passives']) or '(no passive)'}" for it in batch]
    prompt = "ITEMS:\n" + "\n".join(lines)
    body = {"model": MODEL,
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0.1, "max_tokens": 16000, "stream": False}
    headers = {"Authorization": f"Bearer {key}"}
    for attempt in range(5):
        r = requests.post(DEEPSEEK_URL, json=body, headers=headers, timeout=300)
        if r.status_code in (429, 500, 502, 503, 504) and attempt < 4:
            time.sleep(3 * (attempt + 1))
            continue
        if not r.ok:
            raise RuntimeError(f"deepseek {r.status_code}: {r.text[:200]}")
        return json.loads(r.json()["choices"][0]["message"]["content"])
    raise RuntimeError("retries exhausted")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--only", default="", help="comma-separated slugs to re-extract")
    ap.add_argument("--samples", type=int, default=3,
                    help="LLM samples per batch, unioned (1 pass is not reproducible)")
    args = ap.parse_args()
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        raise SystemExit("DEEPSEEK_API_KEY is not set")

    items = json.loads(ITEMS.read_text(encoding="utf-8"))
    cache: dict = {}
    if OUT.exists() and not args.fresh:
        cache = json.loads(OUT.read_text(encoding="utf-8"))
    only = {s.strip() for s in args.only.split(",") if s.strip()}
    if only:  # force re-extraction of these, ignoring the cache
        todo = [it for it in items if it["slug"] in only]
    else:
        todo = [it for it in items if it["slug"] not in cache]
    print(f"{len(items)} items | {len(todo)} to extract")

    by_slug = {it["slug"]: it for it in items}
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        try:
            got = extract_batch(key, batch, samples=args.samples)
        except Exception as e:  # noqa: BLE001
            print(f"  ! batch {i//BATCH}: {e}")
            continue
        for slug, clean in got.items():
            cache[slug] = clean
        OUT.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  batch {i//BATCH + 1}: {min(i+BATCH, len(todo))}/{len(todo)} done")

    n_fx = sum(1 for v in cache.values() if v)
    print(f"\nwrote {OUT.relative_to(ROOT)} ({len(cache)} items, {n_fx} with engine effects)")


if __name__ == "__main__":
    main()
