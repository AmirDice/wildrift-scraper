"""Engine-driven build search: the "absolute best build" loop.

For each champion variant, instead of trusting the LLM's 5-item pick:

  1. The LLM proposes a POOL of ~14 candidate items for the variant (it's good
     at shortlisting synergies; slugs are validated against the item data).
  2. The fight engine exhaustively scores EVERY legal 5-item combination from
     that pool (mutex rules enforced), at the 15-min gold reality + full build,
     with the champion's kit-adjusted offense/defense weights.
  3. The winning combo replaces the build's coreBuild, greedily ordered by
     marginal mid-game value (what you rush actually matters).
  4. CORE items = items appearing in >=60% of the top-20 combos: the picks the
     search says the build cannot do without (2-3, badge-flagged).
  5. One LLM pass writes short reasons for the chosen items.

Runes/boots/enchant/summoners stay from the generated record (searching those
dimensions is a later step). Requires extracted formulas (data/ability_formulas
.json) — champions without them are skipped.

Run (needs DEEPSEEK_API_KEY):
    python -m scripts.search_builds --only "Hecarim"
    python -m scripts.search_builds
"""
from __future__ import annotations

import argparse
import json
import os
import re
from itertools import combinations
from pathlib import Path

from scripts.build_champions_llm import (LLM, SLOT_OF, _champion_block, _extract_json,
                                         _kit_hints)
from web.fight_engine import (FORMULAS, ITEMS, RUNE_ENGINE, RUNE_FX, _build_lists,
                              attack_profile, build_curve, score_items)

ROOT = Path(__file__).resolve().parent.parent
BUILDS = ROOT / "data" / "champion_builds.json"
WEB_OUT = ROOT / "web-next" / "src" / "data" / "builds.json"
RULES = json.loads((ROOT / "data" / "item_rules.json").read_text(encoding="utf-8"))
MUTEX = [set(g) for g in RULES.get("mutexGroups", {}).values()]
RUNES_ALL = json.loads((ROOT / "data" / "runes.json").read_text(encoding="utf-8"))
RUNE_BY_NAME = {r["name"]: r for r in RUNES_ALL}
RUNE_SLOTS = json.loads((ROOT / "data" / "rune_slots.json").read_text(encoding="utf-8"))["trees"]
# Reactive anti-comp items (GA, Maw, anti-heal...) never compete for main-build
# slots — they live in situational swaps only.
SITUATIONAL_ONLY = set((RULES.get("situationalOnly") or {}).get("slugs") or [])
CHAMPS = {c["name"]: c for c in json.loads(
    (ROOT / "data" / "champions_wr.json").read_text(encoding="utf-8"))}

POOL_SIZE = 14
TOP_K = 20
CORE_FREQ = 0.6

# Variant identity constraints. Items fall into three classes:
#   TANK    = pure defensive items (wildriftfire's Defense category)
#   BRUISER = damage + survivability hybrids (Sterak's, Death's Dance, ...)
#   damage  = everything else
# Per variant: (tank_min, tank_max, defensive_min, defensive_max) where
# "defensive" counts tank AND bruiser items. Tuned so damage variants stay full
# damage (one bruiser item of padding allowed, never a tank item), balanced is
# never glass but never tanky, and tanky runs 2-3 tank items — full 4-5 tank is
# reserved for actual Tank-class champions.
IDENTITY_BOUNDS = {
    "oneshot": (0, 0, 0, 1), "burst": (0, 0, 0, 1), "crit": (0, 0, 0, 1),
    "poke": (0, 0, 0, 1), "damage": (0, 0, 0, 1),
    "balanced": (0, 1, 1, 2), "battlemage": (0, 1, 0, 2),
    "tanky": (2, 3, 3, 4), "utility": (0, 2, 0, 3),
}
TANKY_FULL_TANK = (3, 5, 4, 5)  # tanky bounds for Tank-class champions


def is_tank(slug: str) -> bool:
    return (ITEMS.get(slug) or {}).get("category") == "Defense"


def is_defensive(slug: str) -> bool:
    """Tank items plus bruiser survivability hybrids. Pure damage items with a
    token HP line (Trinity) still count if they carry resists; pure-HP+damage
    bruiser items (Sterak's) count; HP-with-offense engines (Shojin) don't."""
    if is_tank(slug):
        return True
    stats = (ITEMS.get(slug) or {}).get("stats") or {}
    if "armor" in stats or "mr" in stats:  # resist hybrids like Death's Dance
        return True
    offensive = any(k in stats for k in ("ad", "ap", "attackSpeed", "crit"))
    return "hp" in stats and not offensive  # pure-HP items (Sterak's-style)

POOL_SYSTEM = (
    "You are a Wild Rift theorycrafter. Given a champion and ONE build variant, "
    "shortlist the candidate items a search engine should consider. Include every "
    "item a strong player might argue for: the obvious core, the synergy picks "
    "(read the kit flags!), and 2-3 defensive/hybrid options even for damage "
    "variants. Use ONLY slugs from the provided pool. No boots, no enchants. "
    'Return ONLY JSON: {"pool": ["slug", ...]} with exactly the requested count.'
)

REASON_SYSTEM = (
    "You write terse Wild Rift item justifications. For each item in each variant "
    "of the given champion build, write a reason under 13 words grounded in the "
    "champion's kit. Return ONLY JSON: "
    '{"<variant>": {"<slug>": "reason", ...}, ...}'
)


def _canon(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


ITEM_CANON = {_canon(s): s for s in ITEMS}
ITEM_CANON.update({_canon(it["name"]): s for s, it in ITEMS.items()})


def legal(combo: tuple[str, ...]) -> bool:
    s = set(combo)
    return all(len(s & g) <= 1 for g in MUTEX)


def propose_pool(llm: LLM, champ: dict, champ_class: str, role: str,
                 variant: str, current: list[str]) -> list[str]:
    """LLM shortlist, seeded with the current build's items, validated."""
    pool_txt = "\n".join(
        f"  {s} | {it['name']} | {it['cost']}g | " +
        (" ".join(it["passives"])[:650] or "no passive")
        for s, it in ITEMS.items()
        if it["category"] not in ("Boots", "Enchantment") and s not in SITUATIONAL_ONLY)
    flags = "\n".join(f"- {f}" for f in _kit_hints(champ))
    prof = attack_profile(champ["name"], current)
    style_line = (f"ATTACK STYLE (engine-measured): {prof['style']} — "
                  f"build around {prof['buildHint']}.")
    prompt = (f"{_champion_block(champ, champ_class, role)}\n\nKIT FLAGS:\n{flags}\n\n"
              f"{style_line}\n\n"
              f"VARIANT: {variant}\nCurrent build (keep these in the pool): {current}\n\n"
              f"ITEM POOL:\n{pool_txt}\n\n"
              f"Shortlist exactly {POOL_SIZE} slugs.")
    raw = _extract_json(llm.generate([prompt], 0.3, POOL_SYSTEM))
    no_resource = any(m.get("kind") == "noResource"
                      for m in FORMULAS.get(champ["name"], {}).get("mechanics") or [])

    def ok(slug: str) -> bool:
        if slug not in ITEMS or ITEMS[slug]["category"] in ("Boots", "Enchantment"):
            return False
        if slug in SITUATIONAL_ONLY:
            return False
        if no_resource and "mana" in (ITEMS[slug].get("stats") or {}):
            return False  # mana items are dead stats on energy/rage kits
        return True

    out: list[str] = []
    for s in raw.get("pool") or []:
        slug = ITEM_CANON.get(_canon(str(s)))
        if slug and ok(slug) and slug not in out:
            out.append(slug)
    for s in current:  # never drop what the generator picked (unless situational-only)
        if ok(s) and s not in out:
            out.append(s)
    return out[:POOL_SIZE + 3]


EARLY_LEVEL = 11  # ordering basis: value while the game is still early-mid


def greedy_order(name: str, combo: list[str], boots: str | None,
                 runes: list[str], variant: str, role: str,
                 core: set[str] | None = None) -> list[str]:
    """Build order = early-game importance. CORE items always come first (in
    their own greedy order), then the rest — each step picks the item whose
    prefix scores highest at an early-mid level, so the rush is the item that
    actually carries the 10-minute game, not the late-game capstone."""
    def _greedy(pool: list[str], ordered: list[str]) -> list[str]:
        out = list(ordered)
        remaining = list(pool)
        while remaining:
            best, best_s = remaining[0], float("-inf")
            for cand in remaining:
                trial = out + [cand] + ([boots] if boots else [])
                s = score_items(name, trial, runes, variant, role,
                                fast=True, level=EARLY_LEVEL)["score"]
                if s > best_s:
                    best, best_s = cand, s
            out.append(best)
            remaining.remove(best)
        return out

    core = core or set()
    core_items = [s for s in combo if s in core]
    rest = [s for s in combo if s not in core]
    ordered = _greedy(core_items, [])
    return _greedy(rest, ordered)


def _rune_modeled(rune_name: str) -> bool:
    """Only runes with numeric engine models can be differentiated by search."""
    return bool(RUNE_FX.get("keystones", {}).get(rune_name)
                or RUNE_FX.get("minors", {}).get(rune_name)
                or RUNE_ENGINE.get(rune_name))


def _page_names(bd: dict) -> tuple[str | None, list[str], str | None, str]:
    r = bd.get("runes") or {}
    ks = (r.get("keystone") or {}).get("name")
    minors = [m["name"] for m in r.get("treeMinors") or []]
    flex = (r.get("flexMinor") or {}).get("name")
    return ks, minors, flex, r.get("primaryTree", "")


def search_runes(name: str, items: list[str], variant: str, role: str,
                 bd: dict) -> dict | None:
    """Exhaustive slot-legal rune-page search over engine-modeled runes.

    Enumerates keystone x tree x (one minor per slot) x flex on the FINAL item
    set, using the fast score path. Only replaces the current page when the
    winner beats it — unmodeled runes all score identically, so the current
    (LLM-judged) page stays unless the math finds something strictly better."""
    cur_ks, cur_minors, cur_flex, _ = _page_names(bd)
    cur_page = ([cur_ks] if cur_ks else []) + cur_minors + ([cur_flex] if cur_flex else [])
    cur_score = score_items(name, items, cur_page, variant, role, fast=True)["score"]
    # Only replace a legal page when the winner is MEANINGFULLY better — sub-point
    # margins are model noise, and the LLM's page carries judgment the engine
    # can't score (unmodeled utility runes). Illegal pages are always replaced.
    if sorted(SLOT_OF.get(n, 0) for n in cur_minors) != [1, 2, 3]:
        cur_score = float("-inf")
    else:
        cur_score += 1.5  # epsilon: the incumbent wins ties

    keystones = sorted({r["name"] for r in RUNES_ALL if r["type"] == "Keystone"
                        and (_rune_modeled(r["name"]) or r["name"] == cur_ks)})
    flex_pool = sorted({r["name"] for r in RUNES_ALL if r["type"] == "Minor"
                        and (_rune_modeled(r["name"]) or r["name"] == cur_flex)})

    best = (cur_score, None)
    pages = 0
    for tree, slots in RUNE_SLOTS.items():
        pools = []
        for s in ("1", "2", "3"):
            names = slots.get(s, [])
            modeled = [n for n in names if _rune_modeled(n)]
            keep_cur = [n for n in names if n in cur_minors]
            pool = sorted(set(modeled + keep_cur)) or names[:1]
            pools.append(pool)
        for a in pools[0]:
            for b2 in pools[1]:
                for c in pools[2]:
                    trio = (a, b2, c)
                    for ks in keystones:
                        for fx in flex_pool:
                            if fx in trio:
                                continue
                            pages += 1
                            page = [ks, a, b2, c, fx]
                            s = score_items(name, items, page, variant, role, fast=True)["score"]
                            if s > best[0]:
                                best = (s, {"keystone": ks, "tree": tree,
                                            "minors": list(trio), "flex": fx})
    if not best[1]:
        return {"pages": pages, "kept": True, "score": cur_score}
    return {"pages": pages, "kept": False, "score": best[0], "prev": cur_score,
            **best[1]}


def _rune_entry(rune_name: str, reason: str = "") -> dict:
    r = RUNE_BY_NAME[rune_name]
    return {"name": r["name"], "slug": r["slug"], "tree": r.get("tree", ""),
            "icon": r["icon"], "reason": reason}


def apply_rune_page(bd: dict, res: dict) -> None:
    old = bd.get("runes") or {}
    old_reason = {}
    for m in old.get("treeMinors") or []:
        old_reason[m["name"]] = m.get("reason", "")
    if old.get("flexMinor"):
        old_reason[old["flexMinor"]["name"]] = old["flexMinor"].get("reason", "")
    if old.get("keystone"):
        old_reason[old["keystone"]["name"]] = old["keystone"].get("reason", "")
    ksr = _rune_entry(res["keystone"], old_reason.get(res["keystone"], ""))
    bd["runes"] = {
        "keystone": {"name": ksr["name"], "slug": ksr["slug"], "icon": ksr["icon"],
                     "reason": ksr["reason"]},
        "primaryTree": res["tree"],
        "treeMinors": [_rune_entry(n, old_reason.get(n, "")) for n in res["minors"]],
        "flexMinor": _rune_entry(res["flex"], old_reason.get(res["flex"], "")),
    }


def search_variant(name: str, rec: dict, variant: str, bd: dict, llm: LLM) -> dict | None:
    role = rec.get("role", "")
    champ = CHAMPS.get(name)
    if not champ:
        return None
    current_items, runes = _build_lists(bd)
    boots = bd.get("boots", {}).get("slug") if bd.get("boots") else None
    current_core = [s for s in current_items if s != boots]

    pool = propose_pool(llm, champ, rec.get("class", "?"), role, variant, current_core)
    if len(pool) < 6:
        return None

    bounds = IDENTITY_BOUNDS.get(variant, (0, 2, 0, 3))
    if variant == "tanky" and rec.get("class") == "Tank":
        bounds = TANKY_FULL_TANK  # only true tanks may go full tank
    t_lo, t_hi, d_lo, d_hi = bounds
    if sum(1 for s in pool if is_tank(s)) < t_lo:
        t_lo = 0  # pool can't supply the tank minimum
    if sum(1 for s in pool if is_defensive(s)) < d_lo:
        d_lo = 0  # pool can't supply the defensive minimum (e.g. mage pools)
    scored: list[tuple[float, tuple[str, ...]]] = []
    for combo in combinations(pool, 5):
        if not legal(combo):
            continue
        n_tank = sum(1 for s in combo if is_tank(s))
        n_def = sum(1 for s in combo if is_defensive(s))
        if not (t_lo <= n_tank <= t_hi and d_lo <= n_def <= d_hi):
            continue
        items = list(combo) + ([boots] if boots else [])
        s = score_items(name, items, runes, variant, role)["score"]
        scored.append((s, combo))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)

    top = scored[:TOP_K]
    freq: dict[str, int] = {}
    for _s, combo in top:
        for slug in combo:
            freq[slug] = freq.get(slug, 0) + 1
    core = {s for s, n in sorted(freq.items(), key=lambda kv: -kv[1])[:3]
            if n / len(top) >= CORE_FREQ}

    best_score, best_combo = scored[0]
    ordered = greedy_order(name, list(best_combo), boots, runes, variant, role, core)
    baseline = score_items(name, current_items, runes, variant, role)["score"]
    return {"ordered": ordered, "core": core, "score": best_score,
            "baseline": baseline, "combos": len(scored), "pool": len(pool),
            "poolSlugs": pool}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--optimize-runes", action="store_true",
                    help="let the engine REPLACE legal rune pages it out-scores. "
                         "Off by default: with only ~20/53 runes numerically modeled, "
                         "engine rune optimization herds every page into the modeled "
                         "subset. Slot-legality fixes always run.")
    args = ap.parse_args()
    if not os.environ.get("DEEPSEEK_API_KEY"):
        raise SystemExit("DEEPSEEK_API_KEY is not set")
    llm = LLM("deepseek", "deepseek-v4-flash")

    builds = json.loads(BUILDS.read_text(encoding="utf-8"))
    only = {n.strip() for n in args.only.split(",") if n.strip()}
    names = [n for n in builds if (not only or n in only) and n in FORMULAS]
    print(f"{len(names)} champions to search")

    for name in names:
        rec = builds[name]
        new_reasons_needed: dict[str, list[str]] = {}
        for variant, bd in (rec.get("builds") or {}).items():
            try:
                res = search_variant(name, rec, variant, bd, llm)
            except Exception as e:  # noqa: BLE001
                print(f"  ! {name}/{variant}: {e}")
                continue
            if not res:
                print(f"  ! {name}/{variant}: no legal combos in pool — skipped")
                continue
            old_by_slug = {i["slug"]: i for i in bd["coreBuild"]}
            bd["coreBuild"] = [{
                "slug": s, "name": ITEMS[s]["name"], "cost": ITEMS[s]["cost"],
                "icon": ITEMS[s]["icon"],
                "reason": old_by_slug.get(s, {}).get("reason", ""),
                **({"core": True} if s in res["core"] else {}),
            } for s in res["ordered"]]
            bd["searched"] = {"combos": res["combos"], "poolSize": res["pool"],
                              "pool": res["poolSlugs"],
                              "engineScore": res["score"], "llmBaseline": res["baseline"]}

            # rune-page search on the final items (slot-legal by construction)
            items, _ = _build_lists(bd)
            try:
                rres = search_runes(name, items, variant, rec.get("role", ""), bd)
            except Exception as e:  # noqa: BLE001
                print(f"    ! rune search failed for {variant}: {e}")
                rres = None
            # By default the engine only FIXES slot-illegal pages; replacing a
            # legal LLM page requires --optimize-runes (and is never allowed for
            # enchanter/utility builds, whose ally value the engine can't see).
            protected = (rec.get("class") == "Enchanter" or variant == "utility"
                         or not args.optimize_runes)
            was_illegal = rres and rres.get("prev") == float("-inf")
            if rres and not rres.get("kept") and (not protected or was_illegal):
                apply_rune_page(bd, rres)
                prev_s = "illegal page" if was_illegal else f"{rres.get('prev'):g}"
                print(f"    runes {variant}: {rres['pages']} pages -> "
                      f"{rres['keystone']} | {rres['tree']} (was {prev_s}, now {rres['score']:g})")
                bd["searched"]["runes"] = {"pages": rres["pages"], "score": rres["score"]}
            items, runes = _build_lists(bd)
            bd["engine"] = score_items(name, items, runes, variant, rec.get("role", ""))
            bd["engine"]["curve"] = build_curve(name, items, runes, variant, rec.get("role", ""))
            new_reasons_needed[variant] = [s for s in res["ordered"]
                                           if not old_by_slug.get(s, {}).get("reason")]
            delta = res["score"] - res["baseline"]
            print(f"  {name}/{variant}: {res['combos']} combos from pool {res['pool']} "
                  f"-> score {res['score']:g} (LLM build was {res['baseline']:g}, "
                  f"{'+' if delta >= 0 else ''}{delta:.1f})")

        # one reasons pass per champion for items that changed
        want = {v: slugs for v, slugs in new_reasons_needed.items() if slugs}
        if want:
            listing = json.dumps({v: [f"{s} ({ITEMS[s]['name']})" for s in slugs]
                                  for v, slugs in want.items()})
            try:
                reasons = _extract_json(llm.generate(
                    [f"CHAMPION: {name}\nItems per variant needing reasons: {listing}\n"
                     f"Return the JSON now."], 0.2, REASON_SYSTEM))
                for v, slugs in want.items():
                    per = reasons.get(v) or {}
                    by_slug = {i["slug"]: i for i in rec["builds"][v]["coreBuild"]}
                    for s in slugs:
                        txt = per.get(s) or per.get(ITEMS[s]["name"]) or ""
                        if s in by_slug and txt:
                            by_slug[s]["reason"] = str(txt)[:120]
            except Exception as e:  # noqa: BLE001
                print(f"    reasons pass failed ({e}) — keeping blank reasons")

        payload = json.dumps(builds, ensure_ascii=False, indent=2)
        BUILDS.write_text(payload, encoding="utf-8")
        WEB_OUT.write_text(payload, encoding="utf-8")

    print("\nsearch complete")


if __name__ == "__main__":
    main()
