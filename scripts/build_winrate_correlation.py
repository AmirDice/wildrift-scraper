"""Does the engine's opinion of a build predict the player's win rate?

Every validation so far compared the engine against POPULARITY, which the owner
correctly pointed out can be wrong. This compares it against the only outcome
signal the captures carry: the win rate each top-50 player posts on that
champion, over the games the leaderboard counted.

For each champion:
  * join builds.jsonl (rank -> exact items) to extracted.csv (rank -> win rate,
    games), so every row is one real player's real build and real result
  * score that player's exact five with the engine, on the axis the champion is
    judged on
  * Spearman-correlate engine score against win rate

Read the caveats printed at the end before believing any of it. Top-50 win
rates are compressed, the samples are small, and player skill is a much larger
effect than item choice.

    python -m scripts.build_winrate_correlation
"""
from __future__ import annotations

import argparse
import csv
import io
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
MIN_GAMES = 20
DEFAULT = "Ahri,Ashe,Diana,Gwen,Nami,Ekko,Jinx,Riven"


def is_boots(slug):
    return (RAW.get(slug) or {}).get("category") == "Boots"


def metric_key(champ):
    return {"burst": "burst3", "durability": "ehp"}.get(fe.damage_metric(champ), "dps8")


def spearman(pairs):
    n = len(pairs)
    if n < 4:
        return None

    def ranks(vals):
        order = sorted(range(n), key=lambda i: vals[i])
        out = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                out[order[k]] = avg
            i = j + 1
        return out

    ra = ranks([p[0] for p in pairs])
    rb = ranks([p[1] for p in pairs])
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((ra[i] - ma) * (rb[i] - mb) for i in range(n))
    da = sum((ra[i] - ma) ** 2 for i in range(n)) ** 0.5
    db = sum((rb[i] - mb) ** 2 for i in range(n)) ** 0.5
    return num / (da * db) if da and db else None


def sessions_for(champ):
    prefix = champ.split()[0].lower().replace("'", "")[:5]
    return [s for s in sorted(CAPTURES.glob("*/*")) if s.name.lower().startswith(prefix)]


def players(champ):
    """[(rank, name, winrate, games, [slugs])] for every complete captured row."""
    out = []
    for session in sessions_for(champ):
        builds, stats = session / "builds.jsonl", session / "extracted.csv"
        if not builds.exists() or not stats.exists():
            continue
        wr = {}
        with stats.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                try:
                    wr[int(row["rank"])] = (row.get("player_name") or "",
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
            if rank not in wr or len(slugs) < 5:
                continue
            name, rate, games = wr[rank]
            if games < MIN_GAMES:
                continue
            out.append((rank, name, rate, games, slugs[:5]))
    return out


def run(champ):
    rec = LADDER.get(champ) or {}
    runes = [k["name"] for k in (rec.get("keystones") or [])[:1]]
    runes += [m["name"] for m in (rec.get("minors") or [])[:4]]
    key = metric_key(champ)
    rows = []
    for rank, name, rate, games, slugs in players(champ):
        if hard_exclusive_violation(slugs):
            continue
        try:
            score = fe.metrics(champ, slugs, runes, 15, fast=True)[key]
        except Exception:
            continue
        rows.append({"rank": rank, "name": name, "wr": rate, "games": games,
                     "score": score, "items": slugs})
    if len(rows) < 4:
        print(f"\n{champ}: only {len(rows)} usable players, skipped")
        return None

    rows.sort(key=lambda r: -r["score"])
    rho = spearman([(r["score"], r["wr"]) for r in rows])
    best_engine = rows[0]
    by_wr = sorted(rows, key=lambda r: -r["wr"])
    top_half = rows[:max(1, len(rows) // 2)]
    bot_half = rows[max(1, len(rows) // 2):]
    avg_top = sum(r["wr"] for r in top_half) / len(top_half)
    avg_bot = sum(r["wr"] for r in bot_half) / len(bot_half) if bot_half else float("nan")

    print("")
    print("=" * 88)
    print(f"{champ}  |  judged on {key}  |  {len(rows)} players with a complete build "
          f"and {MIN_GAMES}+ games")
    print("=" * 88)
    print(f"  Spearman(engine score, win rate) = "
          f"{('%+.2f' % rho) if rho is not None else 'n/a'}")
    print(f"  players the engine rates HIGHEST: average win rate {avg_top:.1f}%")
    print(f"  players the engine rates LOWEST:  average win rate {avg_bot:.1f}%")
    print(f"  gap: {avg_top - avg_bot:+.1f} points")
    print("")
    print(f"  {'engine rank':>11} {'win rate':>9} {'games':>6}  player / build")
    for i, r in enumerate(rows[:3], 1):
        print(f"  {i:>11} {r['wr']:>8.1f}% {r['games']:>6}  {r['name'][:18]:<18} "
              f"{' + '.join(s.split('-')[0][:8] for s in r['items'])}")
    print("  ...")
    for i, r in enumerate(rows[-2:], len(rows) - 1):
        print(f"  {i:>11} {r['wr']:>8.1f}% {r['games']:>6}  {r['name'][:18]:<18} "
              f"{' + '.join(s.split('-')[0][:8] for s in r['items'])}")
    print("")
    print(f"  highest win rate in the sample: {by_wr[0]['wr']:.1f}% "
          f"({by_wr[0]['games']} games) sits at engine rank "
          f"{rows.index(by_wr[0]) + 1} of {len(rows)}")
    return {"champion": champ, "rho": rho, "n": len(rows),
            "gap": avg_top - avg_bot}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--champions", default=DEFAULT)
    args = ap.parse_args()
    results = []
    for champ in [c.strip() for c in args.champions.split(",") if c.strip()]:
        if champ not in fe.CHAMPS:
            print(f"{champ}: not in roster")
            continue
        r = run(champ)
        if r:
            results.append(r)
    print("")
    print("=" * 88)
    print("SUMMARY -- does a build the engine likes come with a better win rate?")
    print("=" * 88)
    print(f"  {'champion':<10} {'n':>4} {'rho':>7} {'win-rate gap, top vs bottom half':>34}")
    for r in results:
        rho = ("%+.2f" % r["rho"]) if r["rho"] is not None else "n/a"
        print(f"  {r['champion']:<10} {r['n']:>4} {rho:>7} {r['gap']:>+33.1f}")
    rhos = [r["rho"] for r in results if r["rho"] is not None]
    if rhos:
        print(f"\n  mean rho {sum(rhos) / len(rhos):+.2f} over {len(rhos)} champions")
        pos = sum(1 for v in rhos if v > 0.2)
        neg = sum(1 for v in rhos if v < -0.2)
        print(f"  clearly positive (>+0.2): {pos}   clearly negative (<-0.2): {neg}")
    print("")
    print("  CAVEATS, which matter more than the numbers above:")
    print("   * top-50 win rates are compressed into a few points, so there is little")
    print("     variance for a build to explain")
    print("   * player skill is a far larger effect than item choice, and is not")
    print("     controlled for at all here")
    print("   * samples are tens of players per champion, not thousands of games")
    print("   * a build is captured at one moment; the win rate accumulated over many")
    print("     games the player may not have built this way")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
