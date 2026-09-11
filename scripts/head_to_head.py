"""Our build against the rank-1 player's build, on the same champion.

The benchmark answers "does this build have the right SHAPE". This answers the
blunter question: put the two builds in a fight and see which one wins.

Three readouts, because no single one settles it:

  MIRROR DUEL   Both builds on the same champion, same runes, rotations racing
                on one clock. mutual_duel reports who kills first, by how much,
                and what health the winner keeps. A build that loses the mirror
                by two seconds is not a matter of taste.

  TARGET PANEL  Both builds against the five standardised profiles the engine
                already carries -- adc, mage, fighter, bruiser, tank. A build
                can win the mirror and still be worse into a tank, and that is
                worth seeing rather than averaging away.

  METRIC VECTOR Every number metrics() computes, side by side, so a win can be
                attributed instead of just recorded.

The opponent build is the highest-ranked captured player with a complete
five-item build and enough games. Ours is whichever the engine ranks first from
the same pool, so the comparison is the engine's own opinion against a real
player's, not against a random build.

    python -m scripts.head_to_head --champion Graves
    python -m scripts.head_to_head --champion Darius --advisor   # use the advisor's build
"""
from __future__ import annotations

import argparse
import csv
import io
import itertools
import json
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import web.fight_engine as fe  # noqa: E402
from web.advisor.validate import hard_exclusive_violation  # noqa: E402
from web.advisor import supportitem  # noqa: E402

LEVEL = 15
CAPTURES = ROOT / "data" / "captures_archive"
MIN_GAMES = 15
LADDER = json.loads(
    (ROOT / "web-next" / "src" / "data" / "ladder_builds.json").read_text("utf-8"))


def best_player(champ: str):
    """(rank, name, winrate, games, items) for the highest-ranked complete build."""
    key = re.sub(r"[^a-z0-9]+", "-", champ.lower()).strip("-")
    best = None
    for session in sorted(CAPTURES.glob("*/*")):
        if not session.name.lower().startswith(key + "_"):
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
            items = [i["slug"] for i in (b.get("items") or [])
                     if i.get("slug") in fe.ITEMS
                     and fe.ITEMS[i["slug"]].get("category") != "Boots"]
            if rank not in info or len(items) < 5:
                continue
            name, rate, games = info[rank]
            if games < MIN_GAMES:
                continue
            if best is None or rank < best[0]:
                best = (rank, name, rate, games, items[:5])
    return best


def engine_pick(champ: str, runes: list[str]) -> list[str] | None:
    rec = LADDER.get(champ) or {}
    pool = [i["slug"] for i in rec.get("items") or []
            if i["slug"] in fe.ITEMS and fe.ITEMS[i["slug"]].get("category") != "Boots"]
    role = fe.CHAMP_ROLE.get(champ) or ""
    best = None
    for combo in itertools.combinations(pool, 5):
        b = list(combo)
        if hard_exclusive_violation(b) or not supportitem.build_is_legal(b, role):
            continue
        s = fe.fight_score(fe.metrics(champ, b, runes, LEVEL, fast=True), "standard", champ)
        if best is None or s > best[0]:
            best = (s, b)
    return best[1] if best else None


def advisor_pick(champ: str) -> list[str] | None:
    """The live advisor's build, read from the KV index the site fills."""
    import urllib.parse
    import urllib.request
    env = {}
    for line in (ROOT / "web-next" / ".env.local").read_text(encoding="utf-8").splitlines():
        m = re.match(r'([A-Z0-9_]+)="?([^"]*)"?$', line.strip())
        if m:
            env[m.group(1)] = m.group(2)
    key = f"latest:build:{re.sub(r'[^a-z0-9]+', '-', champ.lower()).strip('-')}"
    try:
        req = urllib.request.Request(
            f"{env['KV_REST_API_URL']}/get/{urllib.parse.quote(key, safe='')}",
            headers={"Authorization": f"Bearer {env['KV_REST_API_TOKEN']}"})
        raw = json.load(urllib.request.urlopen(req, timeout=20))["result"]
    except Exception:
        return None
    if not raw:
        return None
    items = [s for s in (json.loads(raw).get("items") or [])
             if s in fe.ITEMS and fe.ITEMS[s].get("category") != "Boots"]
    return items[:5] or None


def show(champ: str, ours: list[str], theirs: list[str], runes: list[str],
         label_them: str) -> None:
    bar = "=" * 86
    print(bar)
    print(f"{champ}   OURS vs {label_them}")
    print(bar)
    print(f"  ours   {', '.join(ours)}")
    print(f"  theirs {', '.join(theirs)}")
    shared = sorted(set(ours) & set(theirs))
    print(f"  shared {len(shared)}/5: {', '.join(shared) or 'none'}")

    # ---- metric vector ----------------------------------------------------
    a = fe.metrics(champ, ours, runes, LEVEL, fast=False)
    b = fe.metrics(champ, theirs, runes, LEVEL, fast=False)
    print(f"\n  {'metric':14} {'ours':>10} {'theirs':>10} {'diff':>9}")
    for k in ("dps8", "burst3", "aoe8", "ehp", "sustain", "support",
              "ad", "ap", "crit", "attackSpeed", "haste", "hp", "armor", "mr"):
        if k not in a:
            continue
        va, vb = float(a[k]), float(b[k])
        if va == 0 and vb == 0:
            continue
        pct = (va / vb - 1) * 100 if vb else float("inf")
        print(f"  {k:14} {va:10.0f} {vb:10.0f} {pct:+8.1f}%")
    sa = fe.fight_score(a, "standard", champ)
    sb = fe.fight_score(b, "standard", champ)
    print(f"  {'fight_score':14} {sa:10.1f} {sb:10.1f} {sa - sb:+8.1f}")
    print(f"  {'gold':14} {sum(fe.ITEMS[s]['cost'] for s in ours):10} "
          f"{sum(fe.ITEMS[s]['cost'] for s in theirs):10}")

    # ---- the five standardised targets ------------------------------------
    #
    # ttk AND damage at fixed times. ttk alone saturated: every Graves build
    # killed four of the five targets at exactly 2.25s, the first tick of the
    # solve, so the panel reported four ties and could not separate the builds
    # at all. Damage AT a time discriminates where time TO a threshold cannot.
    vec_a = fe.evaluation_vector(champ, ours, runes, LEVEL)
    vec_b = fe.evaluation_vector(champ, theirs, runes, LEVEL)
    print()
    # THE SAMPLES ARE A COARSE READ OF A STEPWISE CURVE, and ttk is the
    # authority where they disagree.
    #
    # On Graves our build deals more into the tank at t2, t4 AND t8, and still
    # kills it a second later. That looked like a bug and is not. Damage does
    # not accumulate smoothly: it steps each time an ability comes off
    # cooldown. Against the tank, both builds need 4800 damage, and
    #
    #     ours    t5.0 4049   t5.5 4049   t6.0 4049   t6.5 5930  -> ttk 6.5
    #     theirs  t5.0 3924   t5.5 5206   t6.0 5206   t6.5 5719  -> ttk 5.5
    #
    # Their next cast lands a full second sooner, and that cast is the one that
    # crosses the threshold. It is Essence Reaver's ability haste -- 30 against
    # our 10 -- which is exactly why the rank-1 player buys it over Infinity
    # Edge. A higher damage RATE loses to a better CADENCE once the target
    # takes more than about five seconds to kill.
    #
    # So the fixed-time samples separate builds that ttk ties, and ttk settles
    # builds the samples mislead about. Both columns are here for that reason.
    print("  EACH STANDARD TARGET: damage by t=2s / 4s / 8s, and time to kill")
    print(f"  {'target':9} {'ours t2':>8} {'them t2':>8} {'ours t4':>8} {'them t4':>8} "
          f"{'ours t8':>8} {'them t8':>8} {'ours ttk':>9} {'them ttk':>9} {'faster':>8}")
    for name in fe.target_profiles(LEVEL):
        pa, pb = vec_a["perTarget"][name], vec_b["perTarget"][name]
        ta, tb = pa["ttk"], pb["ttk"]
        if ta is None and tb is None:
            win = "neither"
        elif tb is None:
            win = "ours"
        elif ta is None:
            win = "theirs"
        elif ta != tb:
            win = "ours" if ta < tb else "theirs"
        else:
            # Same tick: fall back to who dealt more by then, which is the
            # comparison ttk was too coarse to make.
            win = ("ours" if pa["t2"] > pb["t2"]
                   else "theirs" if pb["t2"] > pa["t2"] else "tie")
            win += "*"
        print(f"  {name:9} {pa['t2']:>8} {pb['t2']:>8} {pa['t4']:>8} {pb['t4']:>8} "
              f"{pa['t8']:>8} {pb['t8']:>8} {str(ta):>9} {str(tb):>9} {win:>8}")
    print("    * ttk tied on the tick; decided on damage dealt by 2s")

    print()
    print(f"  {'vector':20} {'ours':>10} {'theirs':>10}")
    for k in ("physicalEhp", "magicEhp", "timeToDie", "damageBeforeDeath",
              "supportOutput", "ccSeconds", "goldEfficiency"):
        print(f"  {k:20} {str(vec_a.get(k)):>10} {str(vec_b.get(k)):>10}")

    # ---- the mirror -------------------------------------------------------
    md = fe.mutual_duel(champ, ours, runes, champ, theirs, runes, LEVEL)
    print(f"\n  MIRROR DUEL (same champion, same runes, both rotations on one clock)")
    if not md:
        print("    could not resolve both sides")
        return
    verdict = {"you": "OURS wins", "them": f"{label_them} wins",
               "trade": "trade: both kills land in the same 0.25s tick",
               "stalemate": "stalemate: neither rotation reaches a kill"}[md["verdict"]]
    print(f"    {verdict}")
    if md["margin"] is not None:
        print(f"    margin {md['margin']}s   "
              f"our ttk {md['you']['ttk']}s vs their ttk {md['them']['ttk']}s")
    if md["survivorHp"] is not None:
        print(f"    winner keeps {md['survivorHp'] * 100:.1f}% health")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--champion", required=True)
    ap.add_argument("--advisor", action="store_true",
                    help="use the live advisor's build as ours, not the engine's pick")
    args = ap.parse_args()
    champ = args.champion
    if champ not in fe.CHAMPS:
        print(f"{champ}: not in roster")
        return 1
    rec = LADDER.get(champ) or {}
    runes = [k["name"] for k in (rec.get("keystones") or [])[:1]]
    runes += [m["name"] for m in (rec.get("minors") or [])[:4]]
    top = best_player(champ)
    if not top:
        print(f"{champ}: no captured player with a complete build")
        return 1
    rank, name, rate, games, theirs = top
    ours = advisor_pick(champ) if args.advisor else engine_pick(champ, runes)
    if not ours or len(ours) < 5:
        print(f"{champ}: no build on our side "
              f"({'advisor index empty' if args.advisor else 'pool too thin'})")
        return 1
    show(champ, ours, theirs, runes,
         f"RANK {rank} ({name[:20]}, {rate:.1f}% over {games} games)")
    print(f"\n  ours = {'the live advisor' if args.advisor else 'the engine ranking'}"
          f"   runes (both sides) = {', '.join(runes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
