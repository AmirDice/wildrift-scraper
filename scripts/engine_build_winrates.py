"""Take the builds the ENGINE ranks highest, then look up who actually runs
them and what those players' win rates are.

Not a correlation across all players -- that was measured separately and is
silent. This is the direct question: the engine says these five items are the
strongest; does anyone on the leaderboard hold exactly that five, and how do
they do?

The pool is LADDER-ONLY, because that is the version whose ranking survives
scrutiny: with the engine nominating its own extras, real builds fell to rank
#1366 for Ashe, and with the pool anchored to what top players buy they sit in
the top three almost everywhere.

Every matched player is listed with win rate and games, and each build's average
is shown against the champion's whole-sample average so "high" means something.

    python -m scripts.engine_build_winrates
"""
from __future__ import annotations

import argparse
import csv
import io
import itertools
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import web.fight_engine as fe  # noqa: E402
from web.advisor.validate import hard_exclusive_violation  # noqa: E402

RAW = {i["slug"]: i for i in
       json.loads((ROOT / "data" / "items.json").read_text(encoding="utf-8"))}
LADDER = json.loads(
    (ROOT / "web-next" / "src" / "data" / "ladder_builds.json").read_text(encoding="utf-8"))
CAPTURES = ROOT / "data" / "captures_archive"
MIN_GAMES = 15
TOP_BUILDS = 6
DEFAULT = "Ahri,Ashe,Diana,Gwen,Nami,Ekko,Jinx,Riven"


def is_boots(slug):
    return (RAW.get(slug) or {}).get("category") == "Boots"


def metric_key(champ):
    return {"burst": "burst3", "durability": "ehp"}.get(fe.damage_metric(champ), "dps8")


def captured(champ):
    """[(name, winrate, games, frozenset(slugs))] for complete captured rows."""
    prefix = champ.split()[0].lower().replace("'", "")[:5]
    out = []
    for session in sorted(CAPTURES.glob("*/*")):
        if not session.name.lower().startswith(prefix):
            continue
        builds, stats = session / "builds.jsonl", session / "extracted.csv"
        if not builds.exists() or not stats.exists():
            continue
        info = {}
        with stats.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                try:
                    info[int(row["rank"])] = (row.get("player_name") or "?",
                                              float(row["winrate"]), int(row["games"]))
                except (TypeError, ValueError, KeyError):
                    continue
        for line in builds.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            b = json.loads(line)
            rank = int(b["rank"])
            slugs = [i["slug"] for i in (b.get("items") or [])
                     if i.get("slug") and not is_boots(i["slug"]) and i["slug"] in RAW]
            if rank not in info or len(slugs) < 5:
                continue
            name, rate, games = info[rank]
            if games < MIN_GAMES:
                continue
            out.append((name, rate, games, frozenset(slugs[:5])))
    return out


EXTRAS = 8


def completed_pool():
    return [s for s, i in RAW.items()
            if not is_boots(s) and not set(i.get("categories") or []) & {"Basic", "MidTier"}]


def engine_extras(champ, ladder, runes, key):
    """The items the ENGINE would add to the ladder pool on its own merit.

    Kept optional because it is the known-dangerous half: chosen by single-item
    marginal value, the measurement that inverts for marksmen and bruisers. With
    these in, real builds fell to rank #1366 for Ashe; without them they sit in
    the top three. The flag exists so the two can be compared rather than
    assumed.
    """
    base = ladder[:2] or completed_pool()[:1]
    scored = []
    for slug in completed_pool():
        if slug in ladder:
            continue
        ctx = [s for s in base if s != slug]
        if hard_exclusive_violation(ctx + [slug]):
            continue
        try:
            before = fe.metrics(champ, ctx, runes, 15, fast=True)[key]
            after = fe.metrics(champ, ctx + [slug], runes, 15, fast=True)[key]
        except Exception:
            continue
        scored.append((slug, (after - before) / before if before else 0.0))
    scored.sort(key=lambda r: -r[1])
    return [s for s, _v in scored[:EXTRAS]]


def llm_nominations(champ):
    """The items the MODEL puts forward, read from its own candidateItemScores.

    The engine's nominations were the broken half of the hybrid: chosen by
    single-item marginal value, they replaced the top of the table with builds
    no top-50 player runs (3 holders across 60 builds, against 45 for a
    ladder-anchored pool). The model picks candidates from kit reasoning
    instead, which is the half it is actually good at, so this asks it to
    nominate and lets the engine rank.
    """
    import os
    import re
    import subprocess
    env = dict(os.environ)
    try:
        text = (ROOT / "web-next" / ".env.local").read_text(encoding="utf-8")
        for key in ("GEMINI_API_KEY", "ADVISOR_MODEL", "ADVISOR_MODEL_PREMIUM"):
            m = re.search(rf'{key}="?([^"\n]+)"?', text)
            if m:
                env[key] = m.group(1)
    except Exception:
        pass
    role = fe.CHAMP_ROLE.get(champ) or "Mid"
    proc = subprocess.run(
        [sys.executable, "-m", "web.build_advisor", "--champion", champ, "--role", role],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=400, cwd=str(ROOT), env=env)
    if proc.returncode:
        return [], role, None
    try:
        data = json.loads(proc.stdout)
    except Exception:
        return [], role, None
    slugs = [row["item"] for row in (data.get("candidateItemScores") or [])
             if row.get("item") in RAW and not is_boots(row["item"])]
    return slugs, role, data.get("items")


def run(champ, with_extras=False, llm_pool=False):
    rec = LADDER.get(champ) or {}
    pool = [i["slug"] for i in rec.get("items") or []
            if i["slug"] in RAW and not is_boots(i["slug"])]
    if len(pool) < 5:
        print(f"\n{champ}: ladder pool too thin ({len(pool)})")
        return None
    runes = [k["name"] for k in (rec.get("keystones") or [])[:1]]
    runes += [m["name"] for m in (rec.get("minors") or [])[:4]]
    key = metric_key(champ)
    extras = []
    llm_pick = None
    added_by = ""
    if with_extras:
        extras = engine_extras(champ, pool, runes, key)
        pool = pool + extras
        added_by = "engine-added"
    elif llm_pool:
        nominated, role, llm_pick = llm_nominations(champ)
        extras = [s for s in nominated if s not in pool]
        pool = pool + extras
        added_by = "model-added"
        print("")
        print(f"[{champ}] the model nominated {len(nominated)} items as {role}; "
              f"{len(extras)} of them were outside the ladder pool")

    scored = []
    for combo in itertools.combinations(pool, 5):
        build = list(combo)
        if hard_exclusive_violation(build):
            continue
        scored.append((frozenset(build), build,
                       fe.metrics(champ, build, runes, 15, fast=True)[key]))
    scored.sort(key=lambda r: -r[2])

    people = captured(champ)
    sample_avg = sum(p[1] for p in people) / len(people) if people else 0.0

    print("")
    print("=" * 90)
    src = (f"{len(pool) - len(extras)} ladder + {len(extras)} {added_by}"
           if extras else "ladder only")
    print(f"{champ}  |  {key}  |  {len(scored)} legal builds ({src})  |  "
          f"{len(people)} captured players ({MIN_GAMES}+ games)")
    print(f"whole-sample average win rate: {sample_avg:.1f}%")
    print("=" * 90)

    any_hit = False
    for i, (key_set, build, score) in enumerate(scored[:TOP_BUILDS], 1):
        runners = [p for p in people if p[3] == key_set]
        label = " + ".join(s.split("-")[0][:11] for s in build)
        print(f"\n  ENGINE #{i}  {key}={score:.0f}")
        print(f"    {label}")
        if not runners:
            print("    no captured player runs this exact five")
            continue
        any_hit = True
        avg = sum(r[1] for r in runners) / len(runners)
        tot = sum(r[2] for r in runners)
        for name, rate, games, _s in sorted(runners, key=lambda r: -r[1]):
            print(f"      {rate:>6.1f}%  {games:>4} games   {name[:26]}")
        print(f"    -> {len(runners)} player(s), average {avg:.1f}% "
              f"({avg - sample_avg:+.1f} vs sample), {tot} games total")
    if not any_hit:
        print("\n  none of the engine's top builds is held by a captured player")
    if llm_pick:
        picked = frozenset(x for x in llm_pick if x in RAW and not is_boots(x))
        at = next((i for i, (ks, _b, _v) in enumerate(scored, 1) if ks == picked), None)
        where = ("#" + str(at)) if at else "outside this pool"
        print("")
        print(f"  the model's OWN five ranks {where} of {len(scored)} on {key}:")
        print(f"    {', '.join(llm_pick)}")
        runners = [p for p in people if p[3] == picked]
        if runners:
            avg = sum(r[1] for r in runners) / len(runners)
            print(f"    held by {len(runners)} captured player(s), average {avg:.1f}% "
                  f"({avg - sample_avg:+.1f} vs sample)")
        else:
            print("    no captured player runs the model's exact five")
    return {"champion": champ, "sample_avg": sample_avg, "scored": scored,
            "people": people}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--champions", default=DEFAULT)
    ap.add_argument("--extras", action="store_true",
                    help="widen the pool with 8 engine-nominated items")
    ap.add_argument("--llm-pool", action="store_true",
                    help="widen the pool with the MODEL's nominations instead")
    args = ap.parse_args()
    summary = []
    for champ in [c.strip() for c in args.champions.split(",") if c.strip()]:
        if champ not in fe.CHAMPS:
            print(f"{champ}: not in roster")
            continue
        res = run(champ, with_extras=args.extras, llm_pool=args.llm_pool)
        if not res:
            continue
        # One line per champion: how the players on the engine's top builds did
        # against everyone else captured on that champion.
        top_sets = [s for s, _b, _v in res["scored"][:TOP_BUILDS]]
        on_top = [p for p in res["people"] if p[3] in top_sets]
        others = [p for p in res["people"] if p[3] not in top_sets]
        if on_top and others:
            a = sum(p[1] for p in on_top) / len(on_top)
            b = sum(p[1] for p in others) / len(others)
            summary.append((champ, len(on_top), a, len(others), b))
    if summary:
        print("")
        print("=" * 90)
        print(f"SUMMARY -- players holding one of the engine's top {TOP_BUILDS} builds "
              f"vs everyone else")
        print("=" * 90)
        print(f"  {'champion':<12} {'n on top':>9} {'their avg':>10} "
              f"{'n others':>9} {'others avg':>11} {'diff':>7}")
        ordered = sorted(summary, key=lambda r: -(r[2] - r[4]))
        for champ, na, a, nb, b in ordered[:12]:
            print(f"  {champ:<12} {na:>9} {a:>9.1f}% {nb:>9} {b:>10.1f}% {a - b:>+6.1f}")
        print(f"  {'...':<12}")
        for champ, na, a, nb, b in ordered[-12:]:
            print(f"  {champ:<12} {na:>9} {a:>9.1f}% {nb:>9} {b:>10.1f}% {a - b:>+6.1f}")

        # POOLED. The only sample big enough to carry a conclusion: a
        # per-champion diff rests on one or two people and swings double digits
        # on noise, which is exactly how the eight-champion run misled us.
        n_on = sum(x[1] for x in summary)
        n_ot = sum(x[3] for x in summary)
        wavg_on = sum(x[1] * x[2] for x in summary) / n_on if n_on else 0.0
        wavg_ot = sum(x[3] * x[4] for x in summary) / n_ot if n_ot else 0.0
        print("")
        print("=" * 90)
        print("POOLED ACROSS EVERY CHAMPION")
        print("=" * 90)
        print(f"  players holding one of the engine's top {TOP_BUILDS} builds: {n_on}")
        print(f"    average win rate: {wavg_on:.2f}%")
        print(f"  every other captured player: {n_ot}")
        print(f"    average win rate: {wavg_ot:.2f}%")
        print(f"  DIFFERENCE: {wavg_on - wavg_ot:+.2f} points")

        diffs = [a - b for _c, _na, a, _nb, b in summary]
        pos = sum(1 for d in diffs if d > 2)
        neg = sum(1 for d in diffs if d < -2)
        print("")
        print(f"  engine builds better by >2 points on {pos} champions, "
              f"worse by >2 on {neg}, within 2 points on {len(diffs) - pos - neg}")
        print(f"  unweighted mean of per-champion diffs: "
              f"{sum(diffs) / len(diffs):+.2f} over {len(diffs)} champions")

        by_class = {}
        for champ, na, a, nb, b in summary:
            by_class.setdefault(fe.CHAMP_CLASS.get(champ, "?"), []).append((na, a, nb, b))
        print("")
        print("  BY CLASS, pooling players rather than averaging champions:")
        print(f"    {'class':<11} {'champs':>6} {'n on top':>9} {'on top':>9} "
              f"{'others':>9} {'diff':>7}")
        for cls, rws in sorted(by_class.items()):
            na = sum(r[0] for r in rws)
            nb = sum(r[2] for r in rws)
            if not na or not nb:
                continue
            aa = sum(r[0] * r[1] for r in rws) / na
            bb = sum(r[2] * r[3] for r in rws) / nb
            print(f"    {cls:<11} {len(rws):>6} {na:>9} {aa:>8.2f}% "
                  f"{bb:>8.2f}% {aa - bb:>+6.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
