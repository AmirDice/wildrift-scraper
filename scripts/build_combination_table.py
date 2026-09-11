"""Score every legal 5-item combination the engine can reach for a champion.

The hybrid the owner proposed: the ENGINE measures first, mechanically, and the
model then picks from measured options using the player's settings. This
generates the measurement half.

Why this shape:
  * The pool is supplied, not computed. This used to be the champion's ladder
    items plus the eight the ENGINE rated highest on its own, on the reasoning
    that ladder-only caps the system at what top players already adopted. That
    reasoning is sound and the implementation was not: the engine nominated by
    single-item marginal value, which is the measurement already tested and
    rejected (mean Spearman rho +0.19 over 18 champions, INVERTING for Ashe
    -0.47, Jinx -0.43, Jax -0.35, Malphite -0.33). Those nominations filled the
    top of the table with builds nobody plays, and real builds fell to #1366
    for Ashe. Measured 2026-08-19: engine-nominated pools produced 3 holders
    across 10 champions, model-nominated pools 8 across 3.

    So the pool now comes from --pool or --llm-pool, and ladder-only is the
    default. --engine-extras still exists to reproduce the old behaviour, and
    says what it is.
  * Every combination is scored on ALL THREE axes (burst, sustained,
    durability) at a full build and at an early 3-item state, because "early
    game" and "one-shot" in the player's settings have to map onto different
    numbers, not different adjectives.
  * Combinations holding items the engine cannot fully see (Zhonya's stasis,
    Banshee's shield, Quicksilver's cleanse) are FLAGGED rather than silently
    ranked low. The model can reason about stasis; the engine cannot, so the
    flag marks where its own judgement has to carry.
  * Exact matches against real captured top-50 builds are reported, so a
    combination no human has assembled is visible as such.

Nothing here is a verdict. It is a measured table.

    python -m scripts.build_combination_table --champions Gwen,Diana,Ekko
"""
from __future__ import annotations

import argparse
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
from web.advisor import supportitem  # noqa: E402

LEVEL = 15
EARLY_ITEMS = 3
ENGINE_EXTRAS = 8
TOP_ROWS = 8

RAW = {i["slug"]: i for i in
       json.loads((ROOT / "data" / "items.json").read_text(encoding="utf-8"))}
LADDER = json.loads(
    (ROOT / "web-next" / "src" / "data" / "ladder_builds.json").read_text(encoding="utf-8"))
CAPTURES = ROOT / "data" / "captures_archive"


def is_boots(slug):
    return (RAW.get(slug) or {}).get("category") == "Boots"


def completed_pool():
    return [s for s, i in RAW.items()
            if not is_boots(s) and not set(i.get("categories") or []) & {"Basic", "MidTier"}]


def engine_blind(slug):
    """Item states numbers the engine has no channel for."""
    passives = [p for p in (RAW.get(slug) or {}).get("passives") or []
                if any(c.isdigit() for c in p)]
    return bool(passives) and not fe.ENGINE_FX.get(slug)


def metric_key(champ):
    """The single axis this kit's damage is DESCRIBED on, kept for the readout."""
    return {"burst": "burst3", "durability": "ehp"}.get(fe.damage_metric(champ), "dps8")


# The variant the table ranks under. "standard" is the champion's best
# all-around build for a typical game, which is what a table with no player
# settings attached should be showing.
RANK_VARIANT = "standard"


def real_builds(champ):
    """(rank, frozenset of non-boots slugs) for each captured top-50 player."""
    out = []
    prefix = champ.split()[0].lower().replace("'", "")[:5]
    for session in sorted(CAPTURES.glob("*/*")):
        if not session.name.lower().startswith(prefix):
            continue
        path = session / "builds.jsonl"
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            b = json.loads(line)
            slugs = frozenset(i["slug"] for i in (b.get("items") or [])
                              if i.get("slug") and not is_boots(i["slug"]))
            if len(slugs) >= 5:
                out.append((int(b["rank"]), slugs))
    return out


def ladder_pool(champ):
    return [i["slug"] for i in (LADDER.get(champ) or {}).get("items") or []
            if i["slug"] in RAW and not is_boots(i["slug"])]


def llm_nominations(champ):
    """The items the MODEL puts forward, read from its own candidateItemScores.

    This is the half of the hybrid the model is good at. It picks candidates
    from kit reasoning; the engine then ranks combinations of them, which is
    the half the engine is good at.
    """
    import os
    import re
    import subprocess
    env = dict(os.environ)
    try:
        text = (ROOT / "web-next" / ".env.local").read_text(encoding="utf-8")
        for var in ("GEMINI_API_KEY", "ADVISOR_MODEL", "ADVISOR_MODEL_PREMIUM"):
            m = re.search(rf'{var}="?([^"\n]+)"?', text)
            if m:
                env[var] = m.group(1)
    except Exception:
        pass
    role = fe.CHAMP_ROLE.get(champ) or "Mid"
    proc = subprocess.run(
        [sys.executable, "-m", "web.build_advisor", "--champion", champ, "--role", role],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=400, cwd=str(ROOT), env=env)
    if proc.returncode:
        return []
    try:
        data = json.loads(proc.stdout)
    except Exception:
        return []
    return [row["item"] for row in (data.get("candidateItemScores") or [])
            if row.get("item") in RAW and not is_boots(row["item"])]


def build_pool(champ, runes, source="ladder", supplied=None):
    """The item pool to enumerate over. Returns (pool, added).

    `source` is "ladder" (default), "llm" (the model nominates), "engine" (the
    REJECTED marginal-value method, kept only to reproduce old output), or
    "supplied" with an explicit slug list.
    """
    ladder = ladder_pool(champ)
    if source == "supplied":
        extra = [s for s in (supplied or []) if s in RAW and not is_boots(s)]
        added = [s for s in extra if s not in ladder]
        return list(dict.fromkeys(ladder + extra)), added
    if source == "llm":
        nominated = llm_nominations(champ)
        added = [s for s in nominated if s not in ladder]
        return ladder + added, added
    if source != "engine":
        return ladder, []
    key = metric_key(champ)
    base = ladder[:2] or completed_pool()[:1]
    scored = []
    for slug in completed_pool():
        if slug in ladder:
            continue
        ctx = [s for s in base if s != slug]
        if hard_exclusive_violation(ctx + [slug]):
            continue
        try:
            before = fe.metrics(champ, ctx, runes, LEVEL, fast=True)[key]
            after = fe.metrics(champ, ctx + [slug], runes, LEVEL, fast=True)[key]
        except Exception:
            continue
        scored.append((slug, (after - before) / before if before else 0.0))
    scored.sort(key=lambda r: -r[1])
    extras = [s for s, _v in scored[:ENGINE_EXTRAS]]
    print("  WARNING: --engine-extras nominates by single-item marginal value, "
          "the method measured to invert for marksmen and tanks. See the module "
          "docstring.", file=sys.stderr)
    return ladder + extras, extras


#: The axes a build can genuinely trade off against each other. `sustained` and
#: `burst` are kept SEPARATE on purpose: collapsing them into one damage number
#: is what fight_score does at ranking time, and doing it here as well would
#: discard the build that is second-best at everything and best at burst, which
#: is exactly the build a burst-leaning player wants.
PARETO_AXES = ("dps8", "burst3", "ehp", "support", "early")


def pareto_front(rows, axes=PARETO_AXES):
    """The builds no other build beats on every axis at once.

    A build is DOMINATED when some other build is at least as good on every
    axis and strictly better on one. Dominated builds are not close calls --
    nothing about them is worth choosing, at any weighting of the axes, so no
    playstyle dial and no enemy comp can make one the right answer.

    This is what the score cannot do. fight_score has to commit to weights, and
    the moment it does, a build that wins on an axis the weights happen to
    discount disappears into the middle of a ranked list. The frontier is
    weight-free: it is every build that is the best answer to SOME question.

    Written to be checkable rather than clever -- O(n^2) over a few thousand
    rows is milliseconds, and the obvious version is the one that can be read
    against the definition above.

    MEASURED, AND IT DOES NOT WORK AS A PRE-FILTER. The idea was to hand the
    model a few dozen genuinely competitive builds instead of thousands of
    ranked rows. Over 8 champions on ladder-only pools the frontier is indeed
    small -- 1% to 57% of the pool -- but it keeps only 22 of the 82 builds
    real top-50 players hold:

        Ekko 7/11   Riven 5/11   Darius 4/10   Nami 3/9
        Malphite 1/10   Ashe 1/7   Ahri 1/8   Jinx 0/16

    So 73% of real builds are "dominated" by the engine's axes. They are not
    dominated in the game; they are dominated in a model whose axes are
    correlated (dps8, burst3 and early all rise together with damage items) and
    incomplete. Nothing here measures stickiness -- move speed and slows, which
    is why Stridebreaker and Dead Man's Plate are bought -- or resist TYPE
    against a specific enemy comp, or an item active. Filtering on axes that
    miss what players optimise for throws away their answers.

    Nami is the tell in the other direction: she has the largest frontier
    (57%) because `support` is a live axis for her and genuinely trades off
    against damage. Where the engine can see a real trade-off, the frontier is
    wide.

    KEPT AS A DIAGNOSTIC, which is what it is good for. Frontier size measures
    how much genuine choice the engine can see for a champion. Jinx returning
    ONE undominated build out of 91 does not mean Jinx has one good build; it
    means the engine sees no trade-offs in her item pool at all, and that is a
    modelling gap worth chasing rather than a filter worth shipping.
    """
    vals = [tuple(r.get(a, 0.0) for a in axes) for r in rows]
    keep = []
    for i, vi in enumerate(vals):
        dominated = False
        for j, vj in enumerate(vals):
            if i == j:
                continue
            if all(b >= a for a, b in zip(vi, vj)) and any(b > a for a, b in zip(vi, vj)):
                dominated = True
                break
        if not dominated:
            keep.append(rows[i])
    return keep

def run(champ, want_block=False, source="ladder", supplied=None, pareto=False):
    rec = LADDER.get(champ) or {}
    runes = [k["name"] for k in (rec.get("keystones") or [])[:1]]
    runes += [m["name"] for m in (rec.get("minors") or [])[:4]]
    metric = fe.damage_metric(champ)
    key = metric_key(champ)
    pool, extras = build_pool(champ, runes, source=source, supplied=supplied)
    humans = real_builds(champ)

    # THE SUPPORT ITEM IS NOT OPTIONAL, and the enumerator did not know it.
    #
    # A support opens on one of two 0-gold items and never sells it: Soulcast
    # pays 75 gold a minute and stacks to 250 Health and 20 AD / 40 AP. A
    # support build without one has given up the role's income for the game.
    # web/advisor/supportitem.py has enforced this on the MODEL's answer since
    # it was written; the ranking side never learned it, so seven of the
    # engine's top eight Nami builds had no support item while 41 of 47 real
    # top-50 Nami players build Black Mist Scythe. Costing zero, the item also
    # let a 13,500 gold build outrank a 10,600 one with nothing charging for
    # the difference, because fight_score does not price gold.
    role = fe.CHAMP_ROLE.get(champ) or ""
    rows = []
    for combo in itertools.combinations(pool, 5):
        build = list(combo)
        if hard_exclusive_violation(build):
            continue
        if not supportitem.build_is_legal(build, role):
            continue
        full = fe.metrics(champ, build, runes, LEVEL, fast=True)
        early = 0.0
        for trio in itertools.combinations(build, EARLY_ITEMS):
            if hard_exclusive_violation(list(trio)):
                continue
            early = max(early, fe.metrics(champ, list(trio), runes, LEVEL, fast=True)[key])
        exact = sorted(r for r, s in humans if s == frozenset(build))
        rows.append({
            "items": build,
            # RANK ON THE COMPOSITE, not on the single axis.
            #
            # The axis alone judged an enchanter on her own sustained damage,
            # so Sona's engine-optimal build came back as Guinsoo's Rageblade
            # and Terminus and every build a real Sona player holds landed in
            # the bottom 6% of 5291. fight_score already blends offence,
            # defence AND ally value, and metrics() already computes the
            # support term -- the table was computing it and throwing it away
            # at sort time.
            "primary": fe.fight_score(full, RANK_VARIANT, champ),
            "axis": full[key],
            "support": full.get("support", 0),
            "burst3": full["burst3"],
            "dps8": full["dps8"],
            "ehp": full["ehp"],
            "early": early,
            "aoe8": full.get("aoe8", 0),
            "gold": sum(RAW[s]["cost"] for s in build),
            "blind": [s for s in build if engine_blind(s)],
            "exact": exact,
        })
    rows.sort(key=lambda r: -r["primary"])
    all_rows = rows
    front_note = ""
    if pareto:
        front = pareto_front(rows)
        # How many builds a real top-50 player holds SURVIVE the filter. If the
        # frontier drops builds humans actually run, it is discarding real
        # answers and the filter is wrong -- so it is reported every time
        # rather than assumed.
        held = {s for _r, s in humans}
        before = len([r for r in rows if frozenset(r["items"]) in held])
        after = len([r for r in front if frozenset(r["items"]) in held])
        front_note = (f"pareto: {len(front)} of {len(rows)} builds are undominated "
                      f"({100.0 * len(front) / max(1, len(rows)):.1f}%); "
                      f"captured human builds kept {after}/{before}")
        rows = front

    bar = "=" * 92
    print("")
    print(bar)
    print(f"{champ}  |  class {fe.CHAMP_CLASS.get(champ)}  |  role {role or '?'}  |  "
          f"ranked on fight_score({RANK_VARIANT})  |  damage axis {metric.upper()} ({key})")
    if supportitem.is_support(role):
        _sup = [s for s in pool if s in supportitem.SUPPORT_ITEMS]
        print(f"  support role: every build holds exactly one of {_sup or 'NONE IN POOL'}")
    added_by = {"llm": "nominated by the MODEL", "engine": "added by the ENGINE "
                "(marginal value, known to invert)", "supplied": "supplied"}
    print(f"pool: {len(pool)} items = {len(pool) - len(extras)} ladder"
          + (f" + {len(extras)} {added_by.get(source, source)}" if extras else ""))
    if extras:
        print(f"  added: {', '.join(extras)}")
    print(f"legal 5-item combinations scored: {len(all_rows)}   "
          f"captured human builds available: {len(humans)}")
    if front_note:
        print(front_note)
    print(bar)
    print(f"{'#':>2} {'build':<58} {'score':>6} {key:>8} {'early3':>7} "
          f"{'burst3':>7} {'dps8':>6} {'ehp':>5} {'sup':>5} {'gold':>6}")
    for i, r in enumerate(rows[:TOP_ROWS], 1):
        label = " + ".join(s.split("-")[0][:9] for s in r["items"])
        print(f"{i:>2} {label:<58} {r['primary']:>6.1f} {r['axis']:>8.0f} "
              f"{r['early']:>7.0f} {r['burst3']:>7.0f} {r['dps8']:>6.0f} "
              f"{r['ehp']:>5.0f} {r['support']:>5.0f} {r['gold']:>6}")
        if r["blind"]:
            print(f"     engine cannot fully measure: {', '.join(r['blind'])}")
        if r["exact"]:
            print(f"     EXACT MATCH with captured top-50 rank(s) {r['exact']}")

    best = rows[0]
    print("")
    print(f"  engine's top build: {' + '.join(best['items'])}")
    if best["exact"]:
        print(f"  played verbatim by captured top-50 rank(s) {best['exact']}")
    else:
        print("  NOT played verbatim by any captured top-50 player")
    matched = sum(1 for r in rows[:TOP_ROWS] if r["exact"])
    print(f"  of the top {TOP_ROWS} engine builds, {matched} are played verbatim by a captured player")
    if humans:
        overlap = []
        for rank, slugs in humans:
            hit = next((i for i, r in enumerate(rows, 1) if frozenset(r["items"]) == slugs), None)
            if hit:
                overlap.append((rank, hit))
        if overlap:
            overlap.sort(key=lambda x: x[1])
            shown = ", ".join(f"rank {r} -> engine #{p}" for r, p in overlap[:6])
            print(f"  where captured human builds land in the engine ranking: {shown}")
        else:
            print("  no captured human build appears anywhere in this pool "
                  "(they use items outside it)")
    if want_block:
        print("")
        print("-" * 92)
        print("WHAT THE MODEL WOULD RECEIVE")
        print("-" * 92)
        print(prompt_block(champ, rows, pool))


def unmeasured_note(slug):
    """What the engine cannot see about this item, quoted from its own text.

    The model is handed the effect verbatim rather than a label, because
    "unmeasured" tells it nothing while "2.5s of invulnerability" tells it
    everything it needs to overrule a number.
    """
    passives = [p for p in (RAW.get(slug) or {}).get("passives") or []
                if any(c.isdigit() for c in p)]
    text = " | ".join(" ".join(p.split()) for p in passives)
    return text[:190]


def prompt_block(champ, rows, pool, top=5):
    """The engine's measurements as the model would receive them.

    Two halves, and the second is the point: a ranked table on its own would
    quietly bury every item the engine cannot score, which for a tank is most
    of what its players actually build. So the unmeasured items are listed
    beside the table with their real effect text and an explicit licence to
    substitute one in.
    """
    key = metric_key(champ)
    metric = fe.damage_metric(champ)
    unmeasured = [(s, RAW[s].get("name", s), unmeasured_note(s))
                  for s in pool if engine_blind(s)]
    lines = []
    lines.append(f"ENGINE-MEASURED BUILDS for {champ}. Every legal five-item combination "
                 f"from this champion's pool was simulated; these are the strongest on "
                 f"{metric.upper()}, which is the axis this kit is decided on. The numbers "
                 f"are measurements, not a recommendation -- they are what the simulation "
                 f"produced, and they are blind to everything listed under CANNOT MEASURE "
                 f"below.")
    for i, r in enumerate(rows[:top], 1):
        played = (f" [played by top-50 rank {r['exact'][0]}]" if r["exact"]
                  else " [no captured top-50 player runs this exact five]")
        lines.append(
            f"  {i}. {', '.join(r['items'])}"
            f"\n     score={r['primary']:.1f}  {key}={r['axis']:.0f}  "
            f"early3={r['early']:.0f}  "
            f"burst3={r['burst3']:.0f}  dps8={r['dps8']:.0f}  aoe8={r['aoe8']:.0f}  "
            f"ehp={r['ehp']:.0f}  gold={r['gold']}{played}")
    if unmeasured:
        lines.append("")
        lines.append("ITEMS THE SIMULATION CANNOT MEASURE. Each of these carries an effect "
                     "with no damage number the engine can compute -- invulnerability, a "
                     "spell shield, a cleanse, an aura, a slow. They were therefore ABSENT "
                     "from the scoring above, and their absence is not evidence against "
                     "them. You can reason about these effects and the engine cannot:")
        for slug, name, note in unmeasured:
            lines.append(f"  - {slug} ({name}): {note}")
        lines.append("YOU MAY SUBSTITUTE. If one of these answers something this specific "
                     "game demands -- a burst threat that Stasis blanks, a hook or a "
                     "suppression that a spell shield eats, healing that only an aura "
                     "reaches -- swap it in for the weakest measured item above and say in "
                     "your reasoning which measured item you gave up and what the effect "
                     "buys instead. Do not substitute to be safe by default: the measured "
                     "build is the baseline and the burden is on the swap.")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--champions", default="Gwen,Diana,Ekko")
    ap.add_argument("--block", action="store_true",
                    help="print the prompt block the model would receive")
    ap.add_argument("--pool", default="",
                    help="comma-separated item slugs to add to the ladder pool")
    ap.add_argument("--llm-pool", action="store_true",
                    help="widen the pool with the MODEL's own candidateItemScores")
    ap.add_argument("--pareto", action="store_true",
                    help="keep only undominated builds: no other build is at least "
                         "as good on every axis and better on one")
    ap.add_argument("--engine-extras", action="store_true",
                    help="REPRODUCES OLD BEHAVIOUR: widen with 8 items chosen by "
                         "single-item marginal value, the method measured to invert "
                         "for marksmen and tanks")
    args = ap.parse_args()
    supplied = [s.strip() for s in args.pool.split(",") if s.strip()]
    source = ("supplied" if supplied else
              "llm" if args.llm_pool else
              "engine" if args.engine_extras else "ladder")
    for champ in [c.strip() for c in args.champions.split(",") if c.strip()]:
        if champ not in fe.CHAMPS:
            print(f"{champ}: not in roster")
            continue
        run(champ, want_block=args.block, source=source, supplied=supplied,
            pareto=args.pareto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
