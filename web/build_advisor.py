"""LLM-first build advisor: ONE prompt in, a validated build out.

The pivot (2026-07-17): the rule-based simulation engine is months from
"perfect", so for launch the LLM is the reasoning engine and our data is its
only knowledge. The engine is NOT discarded -- it grades the LLM's answer
(engineScore) so every recommendation ships with an independent sanity check.

    user: champion + role + enemy team (+ ally team)
      -> assemble ONE prompt from our structured data:
         champion record (measured scaling, archetype, abilities, mana),
         full item pool, boots (+tier-3 upgrades), rune pool with slots,
         matchups for THESE enemies, live meta stats
      -> DeepSeek, temperature 0.1, JSON only
      -> validate slugs / rune slots / mutex, one repair round
      -> engine cross-score when formulas exist

Run:
    python -m web.build_advisor --champion Graves --role Jungle \
        --enemies "Malphite,Ahri,Ashe,Leona,Master Yi"
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-v4-flash"
TEMPERATURE = 0.1          # near-deterministic: same inputs -> same build


def _load(name: str, default=None):
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


ITEMS = {i["slug"]: i for i in _load("items.json", [])}
RUNES = _load("wrmeta_runes.json", [])
RUNE_SLOTS = (_load("rune_slots.json", {}) or {}).get("trees", {})
ARCHETYPES = _load("champion_archetypes.json", {})
COUNTERS = _load("counters.json", {})
WRMETA = _load("wrmeta_champions.json", {})
ITEM_RULES = _load("item_rules.json", {})
_champs_raw = _load("champions_wr.json", [])
CHAMPS = {c["name"]: c for c in (_champs_raw.values() if isinstance(_champs_raw, dict)
                                 else _champs_raw)}
# class/role live in the builds file, not the raw champion scrape; fold them in
# so the champion block and enemy block can state them.
_BUILDS = _load("../web-next/src/data/builds.json", {}) or _load("champion_builds.json", {})
for _n, _rec in (_BUILDS or {}).items():
    if _n in CHAMPS:
        CHAMPS[_n].setdefault("class", _rec.get("class", ""))
        CHAMPS[_n].setdefault("role", _rec.get("role", ""))

# canonical slug lookup, forgiving about case/punctuation
def _canon(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())

ITEM_CANON = {_canon(s): s for s in ITEMS} | {_canon(i["name"]): s
                                             for s, i in ITEMS.items()}


def _resolve_item(s: str) -> str | None:
    """Slug from a model-written name, tolerant of the variants it reaches for:
    exact, then trailing-s (Dominik's Regard vs Regards), then unique substring.
    The model has seen wr-meta's plural spellings, so a strict match rejected
    legitimate picks and the repair round would repeat the same near-miss."""
    c = _canon(s)
    if c in ITEM_CANON:
        return ITEM_CANON[c]
    for cand in (c.rstrip("s"), c + "s"):
        if cand in ITEM_CANON:
            return ITEM_CANON[cand]
    hits = [slug for cc, slug in ITEM_CANON.items()
            if c and (c in cc or cc in c)]
    return hits[0] if len(set(hits)) == 1 else None
RUNE_NAMES = {r["name"] for r in RUNES}
RUNE_CANON = {_canon(n): n for n in RUNE_NAMES}


# --------------------------------------------------------------------------
# context assembly: the model knows NOTHING except what we send
# --------------------------------------------------------------------------

def _champion_block(name: str) -> str:
    c = CHAMPS.get(name)
    if not c:
        raise ValueError(f"unknown champion {name!r}")
    lines = [f"CHAMPION: {name}",
             f"class={c.get('class','?')} primaryDamage={c.get('primaryDamage','?')} "
             f"scalesWith={c.get('scalesWith')} mechanics={c.get('mechanics')}"]
    arch = ARCHETYPES.get(name)
    if arch:
        lines.append(f"archetype={arch['archetype']} ({arch.get('reason','')})")
    # MEASURED scaling: what each stat is actually worth to this kit, from the
    # simulation probe. This is the blueprint's "scaling" block, but measured
    # rather than hand-authored.
    try:
        from web.fight_engine import stat_weights
        w = stat_weights(name)
        lines.append("measuredScaling=" + json.dumps(
            {k: round(w[k], 2) for k in
             ("ad", "ap", "attackSpeed", "crit", "abilityHaste",
              "physicalPen", "magicPen", "mana", "hp")}, ensure_ascii=False))
    except Exception:  # noqa: BLE001 -- champions without formulas still work
        pass
    wm = WRMETA.get(name) or {}
    for a in c.get("abilities", []):
        mana = next((x.get("manaCosts") for x in wm.get("abilities", [])
                     if x.get("slot") == a.get("slot")), None)
        lines.append(f"[{a['slot']}] {a['name']}"
                     + (f" (mana {mana})" if mana else "")
                     + f": {(a.get('text') or '')[:220]}")
    if wm.get("skillPriority"):
        lines.append(f"skillPriority={wm['skillPriority']}")
    return "\n".join(lines)


def _enemy_block(enemies: list[str], me: str) -> str:
    if not enemies:
        return "ENEMY TEAM: unknown"
    out = ["ENEMY TEAM (their damage type + threat profile):"]
    for e in enemies:
        c = CHAMPS.get(e) or {}
        out.append(f"  {e}: class={c.get('class','?')} "
                   f"damage={c.get('primaryDamage','?')} "
                   f"mechanics={c.get('mechanics') or []}")
    mine = COUNTERS.get(_canon(me).replace(" ", "-"), {}) or COUNTERS.get(
        me.lower().replace(" ", "-"), {})
    hard = (WRMETA.get(me) or {}).get("hardCounters") or []
    bad = [e for e in enemies if e in hard]
    if bad:
        out.append(f"  WARNING: {', '.join(bad)} hard-counter {me}: itemize for it.")
    if mine.get("strong"):
        good = [e for e in enemies if e.lower().replace(' ', '-') in mine["strong"]]
        if good:
            out.append(f"  {me} is strong into: {', '.join(good)}")
    return "\n".join(out)


def _item_pool() -> str:
    rows = []
    for s, it in sorted(ITEMS.items(), key=lambda kv: (kv[1]["category"], kv[0])):
        if it["category"] == "Boots":
            continue
        stats = ",".join(f"{k}:{v['value']}{'%' if v['percent'] else ''}"
                         for k, v in it["stats"].items())
        pas = " | ".join(p[:110] for p in it["passives"][:3])
        rows.append(f"{s} [{it['category']}] {it['cost']}g {stats} :: {pas}")
    return "\n".join(rows)


def _boots_pool() -> str:
    rows = []
    for s, it in ITEMS.items():
        if it.get("bootsTier") == 2:
            t3 = it.get("upgradesTo")
            t3i = ITEMS.get(t3) or {}
            stats3 = ",".join(f"{k}:{v['value']}" for k, v in (t3i.get("stats") or {}).items())
            rows.append(f"{s} ({it['cost']}g) -> upgrades at 10:00 to {t3} ({stats3})")
    return ("BOOTS (pick ONE tier-2; it upgrades to the listed tier-3 for ~1000g "
            "after 10:00 -- usually after your 2nd item):\n" + "\n".join(rows))


def _slot_of() -> dict[str, tuple[str, int]]:
    """name -> (tree, slot). rune_slots.json keys slots as {"1":[...],...}."""
    out = {}
    for tree, slots in RUNE_SLOTS.items():
        for idx, names in slots.items():
            for n in names:
                out[n] = (tree, int(idx))
    return out


def _rune_pool() -> str:
    slot_of = _slot_of()
    rows = []
    for r in RUNES:
        tree, idx = slot_of.get(r["name"], (r.get("tree", "?"), "?"))
        rows.append(f"{r['name']} [{r['type']} | {tree} slot {idx}]: "
                    f"{(r.get('text') or '')[:130]}")
    return ("RUNES (page = 1 keystone + 3 minors from ONE tree, one per slot, "
            "+ 1 flex from any tree):\n" + "\n".join(rows))


def _rules_block() -> str:
    """Hard build-legality rules the model must respect (also enforced in validate)."""
    mg = ITEM_RULES.get("mutexGroups") or {}
    so = (ITEM_RULES.get("situationalOnly") or {}).get("slugs", [])
    lines = ["BUILD RULES (hard legality -- follow exactly):",
             "- The 5 items are all NON-boots items. Choose boots separately from the boots "
             "list; never put a boot in the 5 items.",
             "- Build AT MOST ONE item from each mutually-exclusive group:"]
    for name, members in mg.items():
        lines.append(f"    {name}: {', '.join(members)}")
    if so:
        lines.append("- SITUATIONAL-ONLY (reactive vs the enemy comp): never in the main 5; "
                     "only offer these as situational swaps: " + ", ".join(so))
    return "\n".join(lines)


def _meta_block(name: str) -> str:
    """Live meta the model cannot know: tier + win rate from our site data.

    The EU win rate is centred so 50 = the average champion (each champion's
    top-50 mains sit high on absolute numbers), which we tell the model so it
    reads the figure correctly.
    """
    p = DATA / "../web-next/src/data/site.json"
    if not p.exists():
        return ""
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        champs = d.get("champions") if isinstance(d, dict) else d
        for c in champs or []:
            if c.get("name") != name:
                continue
            keep: dict = {}
            if c.get("tier") is not None:
                keep["tier"] = c["tier"]
            if c.get("wr") is not None:
                keep["euWinRateRelative"] = c["wr"]
            if c.get("maxWr") is not None:
                keep["bestPlayerCeiling"] = c["maxWr"]
            if keep:
                return (f"CURRENT META for {name} (EU top-50 players; win rate is centred "
                        f"so 50 = average champion): {json.dumps(keep)}")
    except Exception:  # noqa: BLE001
        return ""
    return ""


SYSTEM = (
    "You are a Challenger Wild Rift coach. Build the highest-winrate loadout for the "
    "given champion, role and enemy team.\n"
    "KNOWLEDGE RULES -- two tiers:\n"
    "- GAME SENSE: use your full knowledge of this champion's mechanics, playstyle and "
    "known synergies or anti-synergies (e.g. attack-speed runes are wasted on a "
    "reload/magazine kit like Graves; energy champions ignore mana). Where your "
    "knowledge and the measuredScaling data agree, trust the conclusion strongly.\n"
    "- FACTS: item, boot and rune NAMES, stats, prices and effects come ONLY from the "
    "provided pools -- the data given IS the current patch, and your training data "
    "about items or patches is stale. Never invent or rename anything.\n"
    "Method, in order: 1) analyze the champion's kit, measured scaling and archetype; "
    "2) analyze the enemy team's damage mix and threats; 3) SCORE the item pool: pick "
    "the ~12 most relevant items and give each a 0-100 score with a short reason; "
    "4) choose the best FIVE items from your scored list, maximizing synergy, "
    "respecting the champion's scaling (do not give AD items to an AP kit), and "
    "optimizing PURCHASE ORDER for the power curve (strongest early spike first); "
    "5) pick tier-2 boots and note the tier-3 it becomes; 6) build a LEGAL rune page "
    "(1 keystone + 3 minors from one tree, one per slot, + 1 flex) -- cross-check the "
    "keystone against measuredScaling and the kit: a keystone scaling a stat the kit "
    "cannot use is a wasted keystone; 7) only after deciding, explain.\n"
    "Return ONLY JSON:\n"
    '{"itemScores":[{"item":"<slug>","score":0-100,"reason":"..."}],'
    '"items":["<slug>", 5 in PURCHASE ORDER],'
    '"boots":"<tier-2 slug>","bootsUpgrade":"<tier-3 slug>",'
    '"runes":{"keystone":"<name>","primaryTree":"<tree>","minors":["<name>","<name>","<name>"],'
    '"flex":"<name>"},'
    '"situational":[{"item":"<slug>","when":"...","replaces":"<slug>"}],'
    '"why":["3-5 short bullets"]}'
)


def _call(key: str, prompt: str) -> dict:
    body = {"model": MODEL,
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": TEMPERATURE, "max_tokens": 8000, "stream": False}
    for attempt in range(4):
        r = requests.post(DEEPSEEK_URL, json=body,
                          headers={"Authorization": f"Bearer {key}"}, timeout=240)
        if r.status_code in (429, 500, 502, 503, 504) and attempt < 3:
            time.sleep(3 * (attempt + 1))
            continue
        if not r.ok:
            raise RuntimeError(f"deepseek {r.status_code}: {r.text[:200]}")
        return json.loads(r.json()["choices"][0]["message"]["content"])
    raise RuntimeError("retries exhausted")


# --------------------------------------------------------------------------
# validation: the LLM reasons, but it does not get to invent
# --------------------------------------------------------------------------

def _mutex_violation(slugs: list[str]) -> str | None:
    # rules live under "mutexGroups" (a name -> [slugs] map); build at most one
    # from each group. (The old "mutex" key never existed, so this was a no-op.)
    groups = ITEM_RULES.get("mutexGroups") or {}
    for name, members in groups.items():
        hit = [s for s in slugs if s in members]
        if len(hit) > 1:
            return f"mutex ({name}): {hit} cannot coexist -- keep only one"
    return None


# reactive items that must never sit in the main 5 (only as situational swaps)
SITUATIONAL_ONLY = set((ITEM_RULES.get("situationalOnly") or {}).get("slugs", []))


def validate(res: dict) -> list[str]:
    errs = []
    items = [_resolve_item(s) for s in (res.get("items") or [])]
    if len(items) != 5 or None in items or len(set(items)) != 5:
        errs.append(f"items must be 5 unique known slugs, got {res.get('items')}")
    else:
        res["items"] = items
        # boots are chosen separately -- they must never occupy an item slot
        boots_in_items = [s for s in items if ITEMS[s].get("category") == "Boots"]
        if boots_in_items:
            errs.append(f"the 5 items must all be NON-boots items; {boots_in_items} are boots "
                        f"-- put boots in the 'boots' field only")
        situ = [s for s in items if s in SITUATIONAL_ONLY]
        if situ:
            errs.append(f"situational-only items {situ} cannot be in the main 5 "
                        f"-- move them to 'situational' swaps instead")
        m = _mutex_violation(items)
        if m:
            errs.append(m)
    boots = _resolve_item(res.get("boots", ""))
    if not boots or ITEMS[boots].get("bootsTier") != 2:
        errs.append(f"boots must be a tier-2 boots slug, got {res.get('boots')}")
    else:
        res["boots"] = boots
        res["bootsUpgrade"] = ITEMS[boots].get("upgradesTo")
    r = res.get("runes") or {}
    ks = RUNE_CANON.get(_canon(r.get("keystone", "")))
    minors = [RUNE_CANON.get(_canon(x)) for x in (r.get("minors") or [])]
    flex = RUNE_CANON.get(_canon(r.get("flex", "")))
    if not ks or None in minors or len(minors) != 3 or not flex:
        errs.append(f"runes must use known names, got {r}")
    else:
        r["keystone"], r["minors"], r["flex"] = ks, minors, flex
        tree = r.get("primaryTree", "")
        slots = RUNE_SLOTS.get(tree) or {}
        slot_of = {n: int(i) for i, names in slots.items() for n in names}
        got = sorted(slot_of.get(m, 0) for m in minors)
        if slots and got != [1, 2, 3]:
            errs.append(f"minors must be one from EACH of the 3 {tree} slots "
                        f"(got slots {got}); slot map: {slots}")
    return errs


# Playstyle steers the build without changing the pipeline: the blueprint's
# "early/mid/late variants" and the old variant tabs, expressed as one line the
# LLM optimizes toward. "standard" = the best all-around build.
PLAYSTYLES = {
    "standard": "the BEST all-around build for a typical game -- adapt to the kit, "
                "do not force a split.",
    "damage": "maximum raw damage output for this kit (glass cannon): offense over "
              "defense, the highest-damage 5 items the kit can actually use.",
    "crit": "a CRIT build: 4+ of the 5 items must grant Critical Rate; no lethality.",
    "dps": "sustained damage-per-second for extended fights, built the way THIS kit "
           "sustains damage -- attack speed and on-hit only if the kit actually "
           "converts them (not on reload/magazine or caster kits).",
    "burst": "maximum BURST to delete a priority target quickly.",
    "oneshot": "full one-shot assassin build to instantly kill a squishy.",
    "splitpush": "a 1v1 duelist / SPLIT-PUSH build: win side-lane duels and shove/take "
                 "towers fast (dueling sustain and tower/structure damage where the kit allows).",
    "kiting": "a KITING build: attack-move and keep dealing damage while staying mobile "
              "and hard to catch; survivability that keeps you attacking, not raw tank.",
    "vamp": "a LIFESTEAL / omnivamp sustain build that heals through fights while dealing damage.",
    "antitank": "ANTI-TANK: %max-HP and armor/magic penetration to melt the frontline.",
    "tanky": "a bruiser/tank build that survives while staying a threat.",
    "onhit": "ON-HIT build stacking attack speed and on-hit effects.",
    "poke": "long-range POKE and burst from safety.",
    "utility": "protect/utility support build; ally value over personal damage.",
}

# A second, orthogonal axis: HOW to optimize, independent of the playstyle.
OBJECTIVES = {
    "balanced": "",  # default: no extra bias
    "maxstats": "OPTIMIZE FOR STAT EFFICIENCY: favor the items whose raw stats this kit "
                "uses most per gold; prefer stat-dense items over flashy actives when the "
                "value is close.",
    "maxsynergy": "OPTIMIZE FOR SYNERGY: favor items and runes that combo with the kit's "
                  "mechanics and with each other (spellblade on weavers, on-hit on on-hit "
                  "casters, actives that chain into the kit), even at some raw-stat cost.",
}


def advise(champion: str, role: str, enemies: list[str],
           allies: list[str] | None = None, playstyle: str = "standard",
           objective: str = "balanced") -> dict:
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        raise SystemExit("DEEPSEEK_API_KEY is not set")
    style = PLAYSTYLES.get(playstyle, PLAYSTYLES["standard"])
    obj = OBJECTIVES.get(objective, "")
    # "standard" is defined as the best build on paper, irrespective of enemies,
    # so it deliberately ignores the enemy team even when one is supplied.
    if playstyle == "standard":
        enemies = []
    prompt = "\n\n".join(x for x in [
        _champion_block(champion),
        f"ROLE: {role}",
        f"PLAYSTYLE (build toward this): {style}",
        f"OPTIMIZE FOR: {obj}" if obj else "",
        _enemy_block(enemies or [], champion),
        f"ALLY TEAM: {', '.join(allies)}" if allies else "",
        _meta_block(champion),
        _rules_block(),
        _boots_pool(),
        _rune_pool(),
        "ITEM POOL:\n" + _item_pool(),
    ] if x)

    res = _call(key, prompt)
    errs = validate(res)
    if errs:  # one repair round: tell it exactly what was wrong
        res = _call(key, prompt + "\n\nYour previous answer had ERRORS, fix them "
                    "and return the corrected JSON only:\n- " + "\n- ".join(errs))
        errs = validate(res)
        if errs:
            res["validationErrors"] = errs

    # engine cross-check: grade the LLM's homework where the sim can
    try:
        from scripts.search_builds import score_items  # noqa: PLC0415
        page = [res["runes"]["keystone"], *res["runes"]["minors"], res["runes"]["flex"]]
        s = score_items(champion, res["items"] + [res.get("bootsUpgrade") or res["boots"]],
                        page, "standard", role, fast=True)
        res["engineScore"] = round(s["score"], 1)
    except Exception:  # noqa: BLE001 -- no formulas for this champion yet
        res["engineScore"] = None
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--champion", required=True)
    ap.add_argument("--role", default="")
    ap.add_argument("--enemies", default="")
    ap.add_argument("--allies", default="")
    ap.add_argument("--playstyle", default="standard")
    ap.add_argument("--objective", default="balanced")
    args = ap.parse_args()
    res = advise(args.champion, args.role,
                 [e.strip() for e in args.enemies.split(",") if e.strip()],
                 [a.strip() for a in args.allies.split(",") if a.strip()],
                 playstyle=args.playstyle, objective=args.objective)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
