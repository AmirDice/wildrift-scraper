"""PHASE 0 of the marginal-value experiment: does the fight engine's opinion of
an item predict what strong players actually build?

Nothing here touches the advisor, the prompt, or any shipped file. It makes no
model calls. It answers one question before we consider feeding engine numbers
to the model at all: if the engine's ranking disagrees with the top-50 ladder
across the roster, then the measurement is not fit to inform anything and the
experiment stops here.

Method, per champion:
  * context = that champion's own ladder core, which is what makes the
    measurement CONTEXTUAL. Measuring an item alone would have missed the case
    that started this (Dusk and Dawn is only strong while holding Nashor's).
  * for every candidate item, marginal value = value(context + item) minus
    value(context), measured at an EARLY context (2 items) and a LATE one
    (4 items), since an item's worth depends on when it lands.
  * value is DPS for damage classes and effective HP for tanks, the same split
    the spike panel uses -- ranking a tank on damage would be nonsense.
  * items that cannot legally join the context (exclusivity) are skipped.

Output: per-champion top items by engine value against their ladder rank, a
Spearman rank correlation between the two, and a coverage note listing items
whose passives the engine cannot see at all (Stasis, spell shields, cleanse),
because those are exactly the ones a number would libel.

Usage:
    python -m scripts.marginal_value_probe
    python -m scripts.marginal_value_probe --champions Gwen,Ashe --verbose
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent

import web.fight_engine as fe  # noqa: E402
from web.advisor import itemmeta  # noqa: E402
from web.advisor.validate import hard_exclusive_violation  # noqa: E402

LEVEL = 15
EARLY_CONTEXT = 2
LATE_CONTEXT = 4

# A spread across roles and damage types, not a convenience sample: the
# experiment has to fail visibly on champions the engine models badly.
DEFAULT_CHAMPIONS = [
    "Gwen", "Kayle", "Diana", "Ekko",          # on-hit / hybrid AP
    "Riven", "Jax", "Renekton",                # bruisers
    "Malphite", "Amumu", "Ornn",               # tanks
    "Ashe", "Jinx", "Kai'Sa",                  # marksmen
    "Lux", "Ahri", "Veigar",                   # mages (most utility-blind)
    "Zed", "Katarina",                         # assassins
]


def load_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


LADDER = load_json(ROOT / "web-next" / "src" / "data" / "ladder_builds.json", {})
RAW_ITEMS = {i["slug"]: i for i in load_json(ROOT / "data" / "items.json", [])}
ITEM_FX = load_json(ROOT / "data" / "item_engine.json", {})
for _slug, _fx in load_json(ROOT / "data" / "item_engine_overrides.json", {}).items():
    if isinstance(_fx, dict):
        ITEM_FX.setdefault(_slug, {}).update(
            {k: v for k, v in _fx.items() if not k.startswith("_")})


def is_boots(slug: str) -> bool:
    return (RAW_ITEMS.get(slug) or {}).get("category") == "Boots"


def completed_non_boots() -> list[str]:
    out = []
    for slug, item in RAW_ITEMS.items():
        if is_boots(slug):
            continue
        if set(item.get("categories") or []) & {"Basic", "MidTier"}:
            continue
        out.append(slug)
    return sorted(out)


def has_number(text: str) -> bool:
    return any(c.isdigit() for c in text)


def unmeasurable(slug: str) -> bool:
    """True when the item states numbers the engine has no channel for.

    Deliberately crude and deliberately loud: an item with a numeric passive
    and no effect entry is one the engine scores as a bare statstick, so any
    ranking that includes it is understating it by an unknown amount.
    """
    passives = [p for p in (RAW_ITEMS.get(slug) or {}).get("passives") or [] if has_number(p)]
    return bool(passives) and not ITEM_FX.get(slug)


def ladder_context(champ: str) -> tuple[list[str], list[str], dict[str, int]]:
    """The champion's own ladder core (items, runes) and each item's pick count."""
    rec = LADDER.get(champ) or {}
    items, counts = [], {}
    for row in rec.get("items") or []:
        slug = row.get("slug")
        if not slug or is_boots(slug):
            continue
        counts[slug] = row.get("count", 0)
        items.append(slug)
    runes = [k["name"] for k in (rec.get("keystones") or [])[:1]]
    runes += [m["name"] for m in (rec.get("minors") or [])[:4]]
    return items, runes, counts


def value_of(champ: str, items: list[str], runes: list[str], tank: bool) -> float:
    m = fe.metrics(champ, items, runes, LEVEL, fast=True)
    return float(m["ehp"] if tank else m["dps8"])


def spearman(pairs: list[tuple[float, float]]) -> float | None:
    """Rank correlation, written out rather than pulling in scipy."""
    n = len(pairs)
    if n < 3:
        return None

    def ranks(values):
        order = sorted(range(n), key=lambda i: values[i])
        out = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and values[order[j + 1]] == values[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                out[order[k]] = avg
            i = j + 1
        return out

    ra, rb = ranks([p[0] for p in pairs]), ranks([p[1] for p in pairs])
    mean_a, mean_b = sum(ra) / n, sum(rb) / n
    num = sum((ra[i] - mean_a) * (rb[i] - mean_b) for i in range(n))
    den_a = sum((ra[i] - mean_a) ** 2 for i in range(n)) ** 0.5
    den_b = sum((rb[i] - mean_b) ** 2 for i in range(n)) ** 0.5
    return num / (den_a * den_b) if den_a and den_b else None


def probe(champ: str, verbose: bool = False) -> dict | None:
    core, runes, counts = ladder_context(champ)
    if len(core) < LATE_CONTEXT + 1:
        print(f"{champ}: skipped, ladder record too thin ({len(core)} items)")
        return None
    tank = fe.CHAMP_CLASS.get(champ) == "Tank"
    pool = completed_non_boots()

    rows = []
    for slug in pool:
        marginals = {}
        for label, depth in (("early", EARLY_CONTEXT), ("late", LATE_CONTEXT)):
            context = [s for s in core if s != slug][:depth]
            if hard_exclusive_violation(context + [slug]):
                marginals[label] = None
                continue
            try:
                base = value_of(champ, context, runes, tank)
                with_item = value_of(champ, context + [slug], runes, tank)
            except Exception:
                marginals[label] = None
                continue
            marginals[label] = (with_item - base) / base * 100 if base else None
        if marginals.get("early") is None and marginals.get("late") is None:
            continue
        vals = [v for v in marginals.values() if v is not None]
        rows.append({
            "slug": slug,
            "early": marginals.get("early"),
            "late": marginals.get("late"),
            "avg": sum(vals) / len(vals),
            "cost": fe.ITEMS.get(slug, {}).get("cost", 3000),
            "ladder": counts.get(slug, 0),
            "blind": unmeasurable(slug),
        })

    rows.sort(key=lambda r: r["avg"], reverse=True)
    engine_rank = {r["slug"]: i + 1 for i, r in enumerate(rows)}

    # Correlate ONLY over items the ladder actually has an opinion about.
    scored = [r for r in rows if r["ladder"] > 0]
    rho = spearman([(-engine_rank[r["slug"]], r["ladder"]) for r in scored])

    print(f"\n===== {champ} ({fe.CHAMP_CLASS.get(champ)}, "
          f"{'EHP' if tank else 'DPS'}) =====")
    print(f"  ladder core: {', '.join(core[:5])}")
    print(f"  {'item':<26} {'early%':>7} {'late%':>7} {'avg%':>7} {'gold':>5} {'ladder':>7}")
    for r in rows[:10]:
        e = f"{r['early']:+.1f}" if r["early"] is not None else "  -  "
        l = f"{r['late']:+.1f}" if r["late"] is not None else "  -  "
        mark = "  <- ladder core" if r["ladder"] >= 15 else ""
        print(f"  {r['slug']:<26} {e:>7} {l:>7} {r['avg']:+6.1f} {r['cost']:>5} "
              f"{r['ladder']:>7}{mark}")
    if verbose:
        print("  ladder items the engine ranks poorly:")
        for r in sorted(scored, key=lambda r: -r["ladder"])[:8]:
            print(f"    {r['slug']:<26} ladder {r['ladder']:>3}  engine rank "
                  f"{engine_rank[r['slug']]:>3}/{len(rows)}  {'(engine-blind)' if r['blind'] else ''}")
    print(f"  Spearman(engine rank, ladder pick count) over {len(scored)} ladder items: "
          f"{rho:+.2f}" if rho is not None else "  correlation: n/a")
    blind_in_core = [s for s in core[:6] if unmeasurable(s)]
    if blind_in_core:
        print(f"  ENGINE-BLIND items inside this champion's ladder core: {blind_in_core}")
    return {"champion": champ, "rho": rho, "rows": rows, "core": core,
            "blind_core": blind_in_core}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--champions", default="")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    champs = ([c.strip() for c in args.champions.split(",") if c.strip()]
              or DEFAULT_CHAMPIONS)

    results = [r for r in (probe(c, args.verbose) for c in champs) if r]
    rhos = [(r["champion"], r["rho"]) for r in results if r["rho"] is not None]
    print("\n" + "=" * 66)
    print("SUMMARY -- does engine marginal value predict ladder choice?")
    for champ, rho in sorted(rhos, key=lambda x: x[1]):
        print(f"  {champ:<12} {rho:+.2f}")
    if rhos:
        avg = sum(r for _, r in rhos) / len(rhos)
        pos = sum(1 for _, r in rhos if r > 0.2)
        print(f"\n  mean rho {avg:+.2f} over {len(rhos)} champions; "
              f"{pos} clearly positive (>+0.2), {sum(1 for _, r in rhos if r < -0.2)} "
              f"clearly negative (<-0.2)")
    blind = sorted({s for r in results for s in r["blind_core"]})
    if blind:
        print(f"\n  engine-blind items sitting in ladder cores: {blind}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
