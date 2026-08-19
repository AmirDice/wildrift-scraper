"""Score every legal 5-item combination the engine can reach for a champion.

The hybrid the owner proposed: the ENGINE measures first, mechanically, and the
model then picks from measured options using the player's settings. This
generates the measurement half.

Why this shape:
  * The pool is the champion's ladder items PLUS the items the engine rates
    highest on its own. Ladder-only would cap the system at what top players
    have already adopted; adding engine picks lets it propose something they
    have not, which is the point of measuring rather than copying.
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
    return {"burst": "burst3", "durability": "ehp"}.get(fe.damage_metric(champ), "dps8")


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


def build_pool(champ, runes):
    """Ladder items plus the engine's own top picks. Returns (pool, extras)."""
    ladder = [i["slug"] for i in (LADDER.get(champ) or {}).get("items") or []
              if i["slug"] in RAW and not is_boots(i["slug"])]
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
    return ladder + extras, extras


def run(champ, want_block=False):
    rec = LADDER.get(champ) or {}
    runes = [k["name"] for k in (rec.get("keystones") or [])[:1]]
    runes += [m["name"] for m in (rec.get("minors") or [])[:4]]
    metric = fe.damage_metric(champ)
    key = metric_key(champ)
    pool, extras = build_pool(champ, runes)
    humans = real_builds(champ)

    rows = []
    for combo in itertools.combinations(pool, 5):
        build = list(combo)
        if hard_exclusive_violation(build):
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
            "primary": full[key],
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

    bar = "=" * 92
    print("")
    print(bar)
    print(f"{champ}  |  class {fe.CHAMP_CLASS.get(champ)}  |  judged on {metric.upper()} ({key})")
    print(f"pool: {len(pool)} items = {len(pool) - len(extras)} ladder + "
          f"{len(extras)} added by the engine on merit")
    print(f"  engine added: {', '.join(extras) or 'none'}")
    print(f"legal 5-item combinations scored: {len(rows)}   "
          f"captured human builds available: {len(humans)}")
    print(bar)
    print(f"{'#':>2} {'build':<58} {key:>8} {'early3':>7} {'burst3':>7} "
          f"{'dps8':>6} {'aoe8':>6} {'ehp':>5} {'gold':>6}")
    for i, r in enumerate(rows[:TOP_ROWS], 1):
        label = " + ".join(s.split("-")[0][:9] for s in r["items"])
        print(f"{i:>2} {label:<58} {r['primary']:>8.0f} {r['early']:>7.0f} "
              f"{r['burst3']:>7.0f} {r['dps8']:>6.0f} {r['aoe8']:>6.0f} "
              f"{r['ehp']:>5.0f} {r['gold']:>6}")
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
            f"\n     {key}={r['primary']:.0f}  early3={r['early']:.0f}  "
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
    args = ap.parse_args()
    for champ in [c.strip() for c in args.champions.split(",") if c.strip()]:
        if champ not in fe.CHAMPS:
            print(f"{champ}: not in roster")
            continue
        run(champ, want_block=args.block)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
