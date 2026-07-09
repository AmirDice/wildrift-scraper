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

from scripts.build_champions_llm import LLM, _extract_json, _kit_hints, _champion_block
from web.fight_engine import (FORMULAS, ITEMS, _build_lists, score_items)

ROOT = Path(__file__).resolve().parent.parent
BUILDS = ROOT / "data" / "champion_builds.json"
WEB_OUT = ROOT / "web-next" / "src" / "data" / "builds.json"
RULES = json.loads((ROOT / "data" / "item_rules.json").read_text(encoding="utf-8"))
MUTEX = [set(g) for g in RULES.get("mutexGroups", {}).values()]
# Reactive anti-comp items (GA, Maw, anti-heal...) never compete for main-build
# slots — they live in situational swaps only.
SITUATIONAL_ONLY = set((RULES.get("situationalOnly") or {}).get("slugs") or [])
CHAMPS = {c["name"]: c for c in json.loads(
    (ROOT / "data" / "champions_wr.json").read_text(encoding="utf-8"))}

POOL_SIZE = 14
TOP_K = 20
CORE_FREQ = 0.6

# Variant identity constraints: (min, max) DEFENSIVE items in the 5-item core.
# The engine optimizes WITHIN the variant's identity — otherwise it discovers
# that EHP is cheap and turns every "balanced" build into full tank. An item is
# "defensive" by its STATS (resists, or a real HP chunk), not the site category:
# bruiser items like Sterak's/Death's Dance are categorized Physical.
DEFENSE_BOUNDS = {
    "oneshot": (0, 1), "burst": (0, 1), "crit": (0, 1), "poke": (0, 1),
    "damage": (0, 1), "balanced": (1, 2), "battlemage": (0, 2),
    "tanky": (3, 5), "utility": (0, 3),
}


def is_defensive(slug: str) -> bool:
    """TRUE defensive items only. Bruiser items that pair HP with damage stats
    (Shojin, Trinity, Sterak's, Black Cleaver) are damage items with padding,
    not defense — they don't consume the variant's defensive slots. Defensive =
    resists, or pure HP with no offensive stat (Warmog's, Heartsteel)."""
    stats = (ITEMS.get(slug) or {}).get("stats") or {}
    if "armor" in stats or "mr" in stats:  # real resists, incl. hybrids like Death's Dance
        return True
    offensive = any(k in stats for k in ("ad", "ap", "attackSpeed", "crit"))
    return "hp" in stats and not offensive  # pure-HP tank items (Warmog's, Heartsteel)

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
        (" ".join(it["passives"])[:160] or "no passive")
        for s, it in ITEMS.items()
        if it["category"] not in ("Boots", "Enchantment") and s not in SITUATIONAL_ONLY)
    flags = "\n".join(f"- {f}" for f in _kit_hints(champ))
    prompt = (f"{_champion_block(champ, champ_class, role)}\n\nKIT FLAGS:\n{flags}\n\n"
              f"VARIANT: {variant}\nCurrent build (keep these in the pool): {current}\n\n"
              f"ITEM POOL:\n{pool_txt}\n\n"
              f"Shortlist exactly {POOL_SIZE} slugs.")
    raw = _extract_json(llm.generate([prompt], 0.3, POOL_SYSTEM))
    def ok(slug: str) -> bool:
        return (slug in ITEMS and ITEMS[slug]["category"] not in ("Boots", "Enchantment")
                and slug not in SITUATIONAL_ONLY)

    out: list[str] = []
    for s in raw.get("pool") or []:
        slug = ITEM_CANON.get(_canon(str(s)))
        if slug and ok(slug) and slug not in out:
            out.append(slug)
    for s in current:  # never drop what the generator picked (unless situational-only)
        if ok(s) and s not in out:
            out.append(s)
    return out[:POOL_SIZE + 3]


def greedy_order(name: str, combo: list[str], boots: str | None,
                 runes: list[str], variant: str, role: str) -> list[str]:
    """Order the winning combo by marginal mid-game value: best rush first."""
    remaining, ordered = list(combo), []
    while remaining:
        best, best_s = remaining[0], float("-inf")
        for cand in remaining:
            trial = ordered + [cand] + ([boots] if boots else [])
            s = score_items(name, trial, runes, variant, role)["scoreMid"]
            if s > best_s:
                best, best_s = cand, s
        ordered.append(best)
        remaining.remove(best)
    return ordered


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

    lo, hi = DEFENSE_BOUNDS.get(variant, (0, 3))
    scored: list[tuple[float, tuple[str, ...]]] = []
    for combo in combinations(pool, 5):
        if not legal(combo):
            continue
        n_def = sum(1 for s in combo if is_defensive(s))
        if not (lo <= n_def <= hi):
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
    ordered = greedy_order(name, list(best_combo), boots, runes, variant, role)
    baseline = score_items(name, current_items, runes, variant, role)["score"]
    return {"ordered": ordered, "core": core, "score": best_score,
            "baseline": baseline, "combos": len(scored), "pool": len(pool),
            "poolSlugs": pool}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
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
            items, runes = _build_lists(bd)
            bd["engine"] = score_items(name, items, runes, variant, rec.get("role", ""))
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
