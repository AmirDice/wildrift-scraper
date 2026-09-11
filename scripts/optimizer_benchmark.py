"""Adversarial benchmark for the build optimizer: 16 champions, 3 scenarios each.

The champions are chosen to stress DIFFERENT parts of the scoring system rather
than to be strong. Four of them (Darius, Riven, Malphite, Dr. Mundo) probe four
different relationships between durability and combat value, which is where the
2026-09-11 changes landed; four more (Graves, Vayne, Master Yi, Evelynn) probe
the opposite end, so a defensive term that has grown too strong shows up as
carries drifting tanky.

Three scenarios per champion, because one build per champion hides too much:

  A  pure objective      the stated goal alone, ranked on the variant for it
  B  against a comp      the same champion versus a named enemy five, through
                         score_vs_comp
  C  constrained         maximise damage SUBJECT TO surviving the reference
                         fight. The constraint is the point: if A and C never
                         differ, the constraint is not binding on anything

Each test reports a structural PASS/FAIL against data/optimizer_benchmark.json
AND, separately, what real top-50 players do. Both are needed. A structural
check can pass on a build no human would run, and human agreement alone cannot
say whether a constraint did any work.

    python -m scripts.optimizer_benchmark
    python -m scripts.optimizer_benchmark --champions Darius,Malphite --verbose
    python -m scripts.optimizer_benchmark --json out.json    # for regression diffs
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
SPEC = json.loads((ROOT / "data" / "optimizer_benchmark.json").read_text("utf-8"))
# Scenario C constrains on each champion's own floor; see the spec.
CAPTURES = ROOT / "data" / "captures_archive"
MIN_GAMES = 15

DAMAGE_STATS = {"ad", "ap", "crit", "attackSpeed", "physicalPen", "magicPen",
                "physicalPenFlat", "magicPenFlat", "lethality"}
DEFENSIVE_STATS = {"armor", "mr", "hp"}


def item_stats(slug: str) -> dict:
    return (fe.ITEMS.get(slug) or {}).get("stats") or {}


def stat_gold(slug: str) -> tuple[float, float]:
    """(offensive gold, defensive gold) in this item's printed stat line.

    BY GOLD SHARE, not by whether a stat is present at all. Presence classified
    Trinity Force as a defensive item because it carries health, and then a
    Darius build of Trinity, Stridebreaker, Sterak's, Death's Dance and Force of
    Nature scored as five defensive items -- which says nothing, since almost
    every bruiser item in the game carries some health. fe.STAT_GOLD already
    prices each stat, so the split can be measured instead of asserted.
    """
    off = dfn = 0.0
    for k, v in item_stats(slug).items():
        value = v.get("value", 0) if isinstance(v, dict) else v
        gold = fe.STAT_GOLD.get(k, 0.0) * float(value or 0)
        if k in DAMAGE_STATS:
            off += gold
        elif k in DEFENSIVE_STATS:
            dfn += gold
    return off, dfn


def classify(build: list[str]) -> dict:
    dmg = dfn = pure = 0
    for s in build:
        off, dv = stat_gold(s)
        if off >= dv:
            dmg += 1
        else:
            dfn += 1
            if off == 0:
                pure += 1
    return {"damageItems": dmg, "defensiveItems": dfn, "pureTankItems": pure}


def survival_seconds(m: dict) -> float:
    """Seconds alive under FOCUS_DPS, the same model delivered_share uses."""
    return (m["ehp"] + 0.5 * m["sustain"]) / fe.FOCUS_DPS


def captured(champ: str) -> list[tuple[float, int, frozenset]]:
    """Captured top-50 builds for this champion.

    Not scripts.engine_build_winrates.captured: that derives its session prefix
    with champ.split()[0][:5], so "Dr. Mundo" looks for "dr." and the session
    directory is "dr-mundo_*". Mundo reported zero captured builds because of
    it, on a champion whose whole purpose in this benchmark is the durability
    curve. Normalising punctuation to a hyphen matches both.
    """
    key = re.sub(r"[^a-z0-9]+", "-", champ.lower()).strip("-")
    out = []
    for session in sorted(CAPTURES.glob("*/*")):
        name = session.name.lower()
        if not name.startswith(key + "_"):
            continue
        builds, stats = session / "builds.jsonl", session / "extracted.csv"
        if not builds.exists() or not stats.exists():
            continue
        info = {}
        with stats.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                try:
                    info[int(row["rank"])] = (float(row["winrate"]), int(row["games"]))
                except (TypeError, ValueError, KeyError):
                    continue
        for line in builds.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            b = json.loads(line)
            rank = int(b["rank"])
            slugs = [i["slug"] for i in (b.get("items") or [])
                     if i.get("slug") in fe.ITEMS
                     and (fe.ITEMS[i["slug"]].get("category") != "Boots")]
            if rank not in info or len(slugs) < 5:
                continue
            rate, games = info[rank]
            if games >= MIN_GAMES:
                out.append((rate, games, frozenset(slugs[:5])))
    return out


def legal_builds(champ: str) -> tuple[list[list[str]], list[str]]:
    rec = fe.LADDER_BUILDS.get(champ) if hasattr(fe, "LADDER_BUILDS") else None
    ladder = json.loads(
        (ROOT / "web-next" / "src" / "data" / "ladder_builds.json").read_text("utf-8"))
    rec = ladder.get(champ) or {}
    pool = [i["slug"] for i in rec.get("items") or []
            if i["slug"] in fe.ITEMS
            and (fe.ITEMS[i["slug"]].get("category") != "Boots")]
    runes = [k["name"] for k in (rec.get("keystones") or [])[:1]]
    runes += [m["name"] for m in (rec.get("minors") or [])[:4]]
    role = fe.CHAMP_ROLE.get(champ) or ""
    out = []
    for combo in itertools.combinations(pool, 5):
        b = list(combo)
        if hard_exclusive_violation(b) or not supportitem.build_is_legal(b, role):
            continue
        out.append(b)
    return out, runes


def enemy_carry(comp: list[str]) -> tuple[dict, float, float]:
    """The comp's carry as a target, plus its physical/magic damage split."""
    phys = magic = 0
    carry = None
    for name in comp:
        if name not in fe.CHAMPS:
            continue
        if (fe.FORMULAS.get(name) or {}).get("primaryDamage") == "magic" \
                or fe.CHAMPS.get(name, {}).get("primaryDamage") == "magic":
            magic += 1
        else:
            phys += 1
        # The carry is the first non-tank in the comp: who you actually have to kill.
        if carry is None and fe.CHAMP_CLASS.get(name) not in ("Tank",):
            carry = name
    carry = carry or (comp[0] if comp else "Ahri")
    tgt = fe.champion_target(carry, LEVEL, [], []) or fe.dummy_target(2900, 95, 60)
    total = max(1, phys + magic)
    return tgt, phys / total, magic / total


def run_champion(entry: dict, verbose: bool) -> list[dict]:
    champ = entry["name"]
    builds, runes = legal_builds(champ)
    if not builds:
        return [{"champion": champ, "scenario": s, "status": "SKIP",
                 "note": "no legal builds in the ladder pool"}
                for s in ("A_pure", "B_comp", "C_constrained")]
    held = {s for _r, _g, s in captured(champ)}
    metrics = {tuple(b): fe.metrics(champ, b, runes, LEVEL, fast=True) for b in builds}
    exp = entry.get("expect") or {}
    results = []

    def judge(scenario, build, m, extra=None):
        cls = classify(build)
        surv = survival_seconds(m)
        fails = []
        for field in ("damageItems", "defensiveItems", "pureTankItems"):
            rng = exp.get(field)
            if rng and not (rng[0] <= cls[field] <= rng[1]):
                fails.append(f"{field}={cls[field]} outside {rng[0]}-{rng[1]}")
        need = exp.get("minSurvivalSeconds")
        # The floor is stored to one decimal because that is how --calibrate
        # printed it, so compare at that precision. Without the tolerance Ahri
        # failed with "survival 2.1s < 2.1s", which is a bug in the test rather
        # than a finding about the build.
        if need and surv < need - 0.05:
            fails.append(f"survival {surv:.1f}s < {need}s")
        if exp.get("requireSupportItem") and not (set(build) & supportitem.SUPPORT_ITEMS):
            fails.append("no support item")
        row = {"champion": champ, "scenario": scenario,
               "status": "PASS" if not fails else "FAIL",
               "build": sorted(build), "why": fails,
               **cls, "survivalSeconds": round(surv, 1),
               "heldByCapturedPlayer": frozenset(build) in held}
        if extra:
            row.update(extra)
        results.append(row)
        if verbose:
            mark = "PASS" if not fails else "FAIL"
            print(f"    {scenario:14} {mark}  {', '.join(sorted(build))}")
            if fails:
                print(f"                   {'; '.join(fails)}")
        return row

    # ---- A: the stated objective, alone -----------------------------------
    variant = entry.get("variant", "standard")
    best_a = max(builds, key=lambda b: fe.fight_score(metrics[tuple(b)], variant, champ))
    judge("A_pure", best_a, metrics[tuple(best_a)], {"variant": variant})

    # ---- B: against a named enemy comp ------------------------------------
    carry, ad_share, ap_share = enemy_carry(entry.get("comp") or [])
    comp_scores = {tuple(b): fe.score_vs_comp(champ, b, runes, carry, ad_share,
                                              ap_share, LEVEL)["score"] for b in builds}
    best_b = max(builds, key=lambda b: comp_scores[tuple(b)])
    judge("B_comp", best_b, metrics[tuple(best_b)],
          {"comp": entry.get("comp"), "adShare": round(ad_share, 2)})

    # ---- C: most damage that still survives the fight ----------------------
    #
    # The constraint is applied as a FILTER, not as a penalty term. A weighted
    # sum can always buy its way past a soft constraint with enough damage,
    # which is exactly how the old linear durability term let an optimiser
    # trade away survival; a filter cannot be bought off.
    floor = float(exp.get("minSurvivalSeconds") or 0.0)
    survivors = [b for b in builds
                 if survival_seconds(metrics[tuple(b)]) >= floor]
    if survivors:
        key = "burst3" if variant in fe.BURSTY else "dps8"
        best_c = max(survivors, key=lambda b: metrics[tuple(b)][key])
        same = sorted(best_c) == sorted(best_a)
        judge("C_constrained", best_c, metrics[tuple(best_c)],
              {"survivorsOf": f"{len(survivors)}/{len(builds)}",
               "sameAsUnconstrained": same})
    else:
        results.append({"champion": champ, "scenario": "C_constrained",
                        "status": "SKIP",
                        "note": f"no build survives {floor}s of "
                                f"{fe.FOCUS_DPS:.0f} dps",
                        "survivorsOf": f"0/{len(builds)}"})
        if verbose:
            print(f"    C_constrained  SKIP  nothing survives {floor}s")
    return results


def calibrate(entries) -> int:
    """Do REAL top-50 builds satisfy the benchmark's expectations?

    A structural expectation is a claim about what a correct answer looks like,
    and the cheapest way for that claim to be wrong is for me to have made the
    numbers up. So this runs every expectation against the builds captured from
    the top fifty players: whatever they actually hold has to pass, or the
    expectation is measuring my intuition rather than the optimizer.
    """
    print(f"{'champion':12} {'builds':>7}  {'dmg':>9} {'def':>9} {'pure':>9} "
          f"{'survival':>10}   expectation")
    for entry in entries:
        champ = entry["name"]
        if champ not in fe.CHAMPS:
            continue
        builds, runes = legal_builds(champ)
        held = [b for b in builds if frozenset(b) in {s for _r, _g, s in captured(champ)}]
        if not held:
            print(f"{champ:12} {'0':>7}  no captured build is inside the ladder pool")
            continue
        cls = [classify(b) for b in held]
        surv = [survival_seconds(fe.metrics(champ, b, runes, LEVEL, fast=True))
                for b in held]
        exp = entry.get("expect") or {}
        rng = lambda f: (min(c[f] for c in cls), max(c[f] for c in cls))  # noqa: E731
        d, v, p = rng("damageItems"), rng("defensiveItems"), rng("pureTankItems")
        bits = []
        for field, got in (("damageItems", d), ("defensiveItems", v), ("pureTankItems", p)):
            want = exp.get(field)
            if want and not (want[0] <= got[0] and got[1] <= want[1]):
                bits.append(f"{field} humans {got[0]}-{got[1]} vs spec {want[0]}-{want[1]}")
        need = exp.get("minSurvivalSeconds")
        # Same tolerance as judge(): the floor is stored to one decimal.
        if need and min(surv) < need - 0.05:
            bits.append(f"survival humans from {min(surv):.1f}s vs spec {need}s")
        print(f"{champ:12} {len(held):>7}  {d[0]}-{d[1]:<7} {v[0]}-{v[1]:<7} "
              f"{p[0]}-{p[1]:<7} {min(surv):>5.1f}-{max(surv):<4.1f}   "
              + ("; ".join(bits) if bits else "spec fits"))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--champions", default="")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--calibrate", action="store_true",
                    help="check the spec against real top-50 builds instead of running it")
    ap.add_argument("--json", default="", help="write the full results here")
    args = ap.parse_args()

    entries = SPEC["champions"]
    if args.champions:
        want = {c.strip().lower() for c in args.champions.split(",")}
        entries = [e for e in entries if e["name"].lower() in want]

    if args.calibrate:
        return calibrate(entries)

    rows = []
    for entry in entries:
        if entry["name"] not in fe.CHAMPS:
            print(f"{entry['name']}: not in roster")
            continue
        if args.verbose:
            print(f"\n{entry['name']}  ({entry['tests']})")
        rows.extend(run_champion(entry, args.verbose))

    print()
    print("=" * 78)
    print(f"{'champion':12} {'A pure':>10} {'B comp':>10} {'C constr':>10}   "
          f"{'human':>6}  notes")
    print("=" * 78)
    by_champ: dict[str, dict] = {}
    for r in rows:
        by_champ.setdefault(r["champion"], {})[r["scenario"]] = r
    npass = nfail = nskip = 0
    for champ, got in by_champ.items():
        cells = []
        for s in ("A_pure", "B_comp", "C_constrained"):
            r = got.get(s)
            st = r["status"] if r else "-"
            cells.append(f"{st:>10}")
            npass += st == "PASS"
            nfail += st == "FAIL"
            nskip += st == "SKIP"
        human = sum(1 for s in ("A_pure", "B_comp", "C_constrained")
                    if got.get(s, {}).get("heldByCapturedPlayer"))
        note = ""
        c = got.get("C_constrained") or {}
        if c.get("sameAsUnconstrained"):
            note = "C == A (constraint not binding)"
        elif c.get("status") == "SKIP":
            note = c.get("note", "")
        print(f"{champ:12} " + " ".join(cells) + f"   {human}/3    {note}")
    print("=" * 78)
    print(f"{npass} pass, {nfail} fail, {nskip} skipped, of {npass + nfail + nskip}")
    fails = [r for r in rows if r["status"] == "FAIL"]
    if fails:
        print("\nFAILURES")
        for r in fails:
            print(f"  {r['champion']:12} {r['scenario']:14} {'; '.join(r['why'])}")
            print(f"               {', '.join(r['build'])}")
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=1, default=list), "utf-8")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
