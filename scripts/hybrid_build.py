"""The hybrid, end to end: the model nominates, the engine decides.

    model  ->  item pool + objective        (what it is good at)
    engine ->  every legal 5-item combination from that pool
    engine ->  every legal rune page under the chosen keystone and tree
    engine ->  hard survival constraint, as a filter
    engine ->  rank on the objective

The division of labour is the one that measured well on 2026-08-19: model pools
produced builds real top-50 players hold, engine pools produced builds nobody
runs. What is new is everything after the pool. The engine used to rank on
fight_score, a scalar that cannot see multi-target damage, support output or
cooldown cadence; it now ranks on an objective over the evaluation vector, and
it chooses the runes too, which nothing has ever measured.

NOT WIRED TO PRODUCTION, deliberately. Everything here is measurable offline
first, which is the order the rest of this work went in and the reason the 14k
durability cut and the AoE weight are trusted.

    python -m scripts.hybrid_build --champion Jinx
    python -m scripts.hybrid_build --champion Darius --objective bruiser
    python -m scripts.hybrid_build --champions Jinx,Darius,Janna --compare
"""
from __future__ import annotations

import argparse
import io
import itertools
import json
import re
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import web.fight_engine as fe  # noqa: E402
from web.advisor.validate import hard_exclusive_violation  # noqa: E402
from web.advisor import supportitem, runemeta  # noqa: E402

LEVEL = 15
LADDER = json.loads(
    (ROOT / "web-next" / "src" / "data" / "ladder_builds.json").read_text("utf-8"))


def nominated_pool(champ: str) -> tuple[list[str], str, str, str]:
    """(item pool, keystone, tree, source) from the model's cached build.

    Read from the KV index the live site fills rather than by calling the
    advisor: the pool and the keystone are what the model is being asked for,
    and a cached answer is the same answer for free. Falls back to the ladder,
    which is what every surface falls back to now.
    """
    import urllib.parse
    import urllib.request
    env = {}
    try:
        for line in (ROOT / "web-next" / ".env.local").read_text("utf-8").splitlines():
            m = re.match(r'([A-Z0-9_]+)="?([^"]*)"?$', line.strip())
            if m:
                env[m.group(1)] = m.group(2)
        key = f"latest:build:{re.sub(r'[^a-z0-9]+', '-', champ.lower()).strip('-')}"
        req = urllib.request.Request(
            f"{env['KV_REST_API_URL']}/get/{urllib.parse.quote(key, safe='')}",
            headers={"Authorization": f"Bearer {env['KV_REST_API_TOKEN']}"})
        raw = json.load(urllib.request.urlopen(req, timeout=20))["result"]
    except Exception:
        raw = None
    if raw:
        data = json.loads(raw)
        pool = [r["item"] for r in (data.get("candidateItemScores") or [])
                if r.get("item") in fe.ITEMS
                and fe.ITEMS[r["item"]].get("category") != "Boots"]
        pool = pool or [s for s in (data.get("items") or []) if s in fe.ITEMS]
        page = data.get("runes") or {}
        ks = page.get("keystone") or ""
        tree = page.get("primaryTree") or ""
        if len(pool) >= 5 and ks and tree:
            return pool, ks, tree, "model"
    rec = LADDER.get(champ) or {}
    pool = [i["slug"] for i in rec.get("items") or []
            if i["slug"] in fe.ITEMS and fe.ITEMS[i["slug"]].get("category") != "Boots"]
    ks = (rec.get("keystones") or [{}])[0].get("name", "")
    tree = ""
    for m in rec.get("minors") or []:
        tree = runemeta.SLOT_OF.get(runemeta.resolve(m["name"]) or "", ("", 0))[0]
        if tree:
            break
    return pool, ks, tree, "ladder"


def run(champ: str, objective: str = "", survival: float = 0.0,
        compare: bool = False) -> dict:
    pool, keystone, tree, source = nominated_pool(champ)
    if len(pool) < 5:
        print(f"{champ}: pool too thin ({len(pool)})")
        return {}
    objective = objective or fe.default_objective(champ)
    role = fe.CHAMP_ROLE.get(champ) or ""

    # ---- items: every legal combination from the nominated pool ------------
    combos = [list(c) for c in itertools.combinations(pool, 5)
              if not hard_exclusive_violation(list(c))
              and supportitem.build_is_legal(list(c), role)]
    if not combos:
        print(f"{champ}: no legal combination in the pool")
        return {}

    # A starting rune page, so items are compared while wearing something
    # plausible rather than nothing. The page is re-chosen for the winner.
    seed_page = [keystone] + [m["name"] for m in (LADDER.get(champ) or {}).get("minors") or []][:3]

    t0 = time.time()
    scored = []
    for b in combos:
        vec = fe.evaluation_vector(champ, b, seed_page, LEVEL, fast=True)
        # THE SURVIVAL CONSTRAINT IS A FILTER, not a penalty. A weighted sum
        # can always buy its way past a soft constraint with enough damage,
        # which is how the old linear durability term let an optimiser trade
        # survival away entirely.
        if survival and vec.get("timeToDie", 0) < survival:
            continue
        scored.append((fe.objective_score(vec, objective), b))
    if not scored:
        print(f"{champ}: nothing survives {survival}s; constraint is unsatisfiable")
        return {}
    scored.sort(key=lambda r: -r[0])
    items_time = time.time() - t0

    # ---- runes: every legal page under the model's keystone and tree -------
    best_items = scored[0][1]
    t1 = time.time()
    page = fe.best_rune_page(champ, best_items, objective, tree, keystone, LEVEL) \
        if tree else {}
    runes_time = time.time() - t1

    print("=" * 84)
    print(f"{champ}   objective {objective}   pool from the {source}")
    print("=" * 84)
    print(f"  pool ({len(pool)}): {', '.join(pool)}")
    print(f"  {len(combos)} legal combinations, {len(scored)} past the constraint "
          f"({items_time:.1f}s)")
    print(f"\n  ITEMS   {', '.join(best_items)}")
    print(f"          score {scored[0][0]}   runner-up {scored[1][0] if len(scored) > 1 else '-'}"
          f"   worst {scored[-1][0]}")
    if page:
        print(f"\n  RUNES   {page['keystone']} | {', '.join(page['minors'])} "
              f"| flex {page['flex']}")
        print(f"          {page['consideredPages']} legal pages in {tree} ({runes_time:.1f}s), "
              f"score {page['score']}, spread {page['spread']}")
    else:
        print(f"\n  RUNES   skipped: no primary tree could be determined")

    if compare:
        held = _captured(champ)
        exact = frozenset(best_items) in held
        print(f"\n  held by a captured top-50 player: {'YES' if exact else 'no'}"
              f"   ({len(held)} distinct captured builds)")
    return {"champion": champ, "objective": objective, "items": best_items,
            "runes": page.get("page"), "score": scored[0][0], "source": source}


def _captured(champ: str) -> set:
    import csv
    key = re.sub(r"[^a-z0-9]+", "-", champ.lower()).strip("-")
    out = set()
    for session in sorted((ROOT / "data" / "captures_archive").glob("*/*")):
        if not session.name.lower().startswith(key + "_"):
            continue
        builds, stats = session / "builds.jsonl", session / "extracted.csv"
        if not builds.exists() or not stats.exists():
            continue
        ok = set()
        with stats.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                try:
                    if int(row["games"]) >= 15:
                        ok.add(int(row["rank"]))
                except (TypeError, ValueError, KeyError):
                    continue
        for line in builds.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            b = json.loads(line)
            if int(b["rank"]) not in ok:
                continue
            slugs = [i["slug"] for i in (b.get("items") or [])
                     if i.get("slug") in fe.ITEMS
                     and fe.ITEMS[i["slug"]].get("category") != "Boots"]
            if len(slugs) >= 5:
                out.add(frozenset(slugs[:5]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--champion", default="")
    ap.add_argument("--champions", default="")
    ap.add_argument("--objective", default="",
                    help="override; defaults to the champion's class objective")
    ap.add_argument("--survival", type=float, default=0.0,
                    help="seconds the build must survive under FOCUS_DPS")
    ap.add_argument("--compare", action="store_true",
                    help="say whether a captured top-50 player holds the result")
    args = ap.parse_args()
    names = [c.strip() for c in (args.champions or args.champion).split(",") if c.strip()]
    if not names:
        print("name a champion with --champion or --champions")
        return 2
    for champ in names:
        if champ not in fe.CHAMPS:
            print(f"{champ}: not in roster")
            continue
        run(champ, args.objective, args.survival, args.compare)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
