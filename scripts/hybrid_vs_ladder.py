"""Hybrid build against the leaderboard, for champions the top 50 agree on.

Picking champions with HIGH BUILD CONSENSUS is the point. Where the top fifty
players scatter across a dozen builds there is no single answer to be close to,
and "the engine disagrees" means nothing. Where 92% of them build the same five
items, the leaderboard is a real answer and the distance to it is a real number.

Emits JSON for the comparison page. Nothing here is wired to production.

    python -m scripts.hybrid_vs_ladder --champions Samira,Ezreal,Amumu,Ryze --out out.json
"""
from __future__ import annotations

import argparse
import collections
import csv
import glob
import itertools
import json
import re
import sys
from pathlib import Path

# reconfigure, not a new TextIOWrapper: scripts/hybrid_build.py wraps stdout
# too, and the second wrapper closes the first one's buffer on collection.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import web.fight_engine as fe  # noqa: E402
from web.advisor.validate import hard_exclusive_violation  # noqa: E402
from web.advisor import supportitem  # noqa: E402

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("hb", ROOT / "scripts" / "hybrid_build.py")
hb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hb)

LEVEL = 15
MIN_GAMES = 15


def item_name(slug: str) -> str:
    return (fe.ITEMS.get(slug) or {}).get("name") or slug


def captured_rows(champ: str) -> list[dict]:
    """Every captured top-50 player with a complete build, newest session wins."""
    key = re.sub(r"[^a-z0-9]+", "-", champ.lower()).strip("-")
    out = []
    for sess in sorted(glob.glob(str(ROOT / "data" / "captures_archive" / "*" / f"{key}_*"))):
        info = {}
        try:
            for r in csv.DictReader(open(f"{sess}/extracted.csv", encoding="utf-8")):
                if int(r["games"]) >= MIN_GAMES:
                    info[int(r["rank"])] = (r.get("player_name") or "?",
                                            float(r["winrate"]), int(r["games"]))
        except (OSError, KeyError, ValueError):
            continue
        try:
            lines = open(f"{sess}/builds.jsonl", encoding="utf-8").read().splitlines()
        except OSError:
            continue
        for ln in lines:
            if not ln.strip():
                continue
            b = json.loads(ln)
            rank = int(b["rank"])
            if rank not in info:
                continue
            slugs = [i["slug"] for i in (b.get("items") or [])
                     if i.get("slug") in fe.ITEMS
                     and fe.ITEMS[i["slug"]].get("category") != "Boots"]
            if len(slugs) < 5:
                continue
            name, rate, games = info[rank]
            out.append({"rank": rank, "player": name, "winrate": rate, "games": games,
                        "items": slugs[:5], "runes": (b.get("runes") or [])[:5]})
    return out


def consensus(rows: list[dict]) -> dict:
    """The leaderboard's own answer: modal items, modal page, and how agreed."""
    items = collections.Counter()
    pages = collections.Counter()
    for r in rows:
        for s in r["items"]:
            items[s] += 1
        if len(r["runes"]) >= 4:
            pages[tuple(r["runes"])] += 1
    n = max(1, len(rows))
    top5 = items.most_common(5)
    page, page_n = (pages.most_common(1) or [((), 0)])[0]
    return {
        "items": [s for s, _c in top5],
        "itemPicks": {s: c for s, c in top5},
        "itemConsensusPct": round(100 * sum(c for _s, c in top5) / (5 * n), 1),
        "runes": list(page),
        "runePagePct": round(100 * page_n / n, 1),
        "players": len(rows),
    }


def run(champ: str) -> dict:
    rows = captured_rows(champ)
    if not rows:
        return {}
    lad = consensus(rows)

    pool, keystone, tree, source = hb.nominated_pool(champ)
    objective = fe.default_objective(champ)
    role = fe.CHAMP_ROLE.get(champ) or ""
    combos = [list(c) for c in itertools.combinations(pool, 5)
              if not hard_exclusive_violation(list(c))
              and supportitem.build_is_legal(list(c), role)]
    seed = [keystone] + lad["runes"][1:4]
    best, best_score = None, -1.0
    for b in combos:
        s = fe.objective_score(
            fe.evaluation_vector(champ, b, seed, LEVEL, fast=True), objective)
        if s > best_score:
            best, best_score = b, s
    page = fe.best_rune_page(champ, best, objective, tree, keystone, LEVEL) if tree else {}

    shared = sorted(set(best) & set(lad["items"]))
    lad_runes = lad["runes"]
    our_runes = page.get("page") or []
    shared_runes = sorted(set(our_runes) & set(lad_runes))

    # Both builds through the same measurements, so "different" can be priced.
    vec_ours = fe.evaluation_vector(champ, best, our_runes or seed, LEVEL)
    vec_lad = fe.evaluation_vector(champ, lad["items"], lad_runes or seed, LEVEL)
    return {
        "champion": champ,
        "class": fe.CHAMP_CLASS.get(champ, ""),
        "role": role,
        "objective": objective,
        "poolSource": source,
        "poolSize": len(pool),
        "combinations": len(combos),
        "ladder": {**lad, "itemNames": [item_name(s) for s in lad["items"]]},
        "hybrid": {
            "items": best, "itemNames": [item_name(s) for s in best],
            "runes": our_runes, "score": round(best_score, 1),
            "pagesConsidered": page.get("consideredPages", 0),
            "tree": tree,
        },
        "overlap": {
            "items": shared, "itemNames": [item_name(s) for s in shared],
            "itemCount": len(shared),
            "runes": shared_runes, "runeCount": len(shared_runes),
        },
        "vectors": {"hybrid": vec_ours, "ladder": vec_lad},
        "objectiveScores": {
            "hybrid": fe.objective_score(vec_ours, objective),
            "ladder": fe.objective_score(vec_lad, objective),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--champions", required=True)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    out = []
    for champ in [c.strip() for c in args.champions.split(",") if c.strip()]:
        if champ not in fe.CHAMPS:
            print(f"{champ}: not in roster")
            continue
        r = run(champ)
        if not r:
            print(f"{champ}: no captured players")
            continue
        out.append(r)
        print(f"{champ:14} items {r['overlap']['itemCount']}/5 shared, "
              f"runes {r['overlap']['runeCount']}/5, "
              f"objective {r['objectiveScores']['hybrid']} vs "
              f"{r['objectiveScores']['ladder']} (ladder)")
    if args.out:
        Path(args.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
