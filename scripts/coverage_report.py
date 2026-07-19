"""Report what the engine does NOT model, across champions, items and runes.

The extraction pipeline is deliberately closed-vocabulary: anything it cannot
express as a known key is dropped rather than invented. That is the right
trade, but it makes gaps silent. This prints the gaps so they can be triaged
instead of discovered one build complaint at a time.

Run:
    python -m scripts.coverage_report            # summary
    python -m scripts.coverage_report --detail   # every dropped line
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def _load(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def _real(d: dict) -> dict:
    """Drop _note / _meta bookkeeping keys."""
    return {k: v for k, v in d.items() if not k.startswith("_")}


def champions(detail: bool) -> None:
    forms = _real(_load("ability_formulas.json"))
    rows, total_un, total_ab = [], 0, 0
    for name, rec in sorted(forms.items()):
        abils = rec.get("abilities", {})
        un = {k: a.get("unmodeled") or [] for k, a in abils.items()}
        n_un = sum(len(v) for v in un.values())
        # An ability with no damage AND no steroid AND no defensive is fully dark.
        dark = [k for k, a in abils.items()
                if not a.get("damage") and not a.get("steroids") and not a.get("defensive")]
        total_un += n_un
        total_ab += len(abils)
        rows.append((n_un, name, len(abils), dark, un))

    print(f"\n{'='*66}\nCHAMPIONS  ({len(forms)} extracted, {total_ab} abilities, "
          f"{total_un} unmodeled notes)\n{'='*66}")
    for n_un, name, n_ab, dark, un in sorted(rows, reverse=True):
        flag = f"  DARK: {','.join(dark)}" if dark else ""
        print(f"  {name:14} {n_un:3} unmodeled / {n_ab} abilities{flag}")
        if detail:
            for slot, notes in un.items():
                for t in notes:
                    print(f"        {slot}: {t[:110]}")


def items(detail: bool) -> None:
    its = _load("items.json")
    fx = _load("item_engine.json")
    over = _load("item_engine_overrides.json") if (DATA / "item_engine_overrides.json").exists() else {}

    gaps, stat_sticks, modeled = [], [], []
    for it in its:
        slug = it["slug"]
        text = " ".join(it.get("passives") or []).strip()
        eff = {**(fx.get(slug) or {}), **(over.get(slug) or {})}
        if eff:
            modeled.append(slug)
        elif text:
            gaps.append((slug, text))       # has a passive, engine sees nothing
        else:
            stat_sticks.append(slug)        # legitimately pure stats

    print(f"\n{'='*66}\nITEMS  ({len(its)} total | {len(modeled)} modeled | "
          f"{len(gaps)} WITH PASSIVE BUT NO EFFECT | {len(stat_sticks)} pure stat sticks)"
          f"\n{'='*66}")
    for slug, text in sorted(gaps):
        print(f"  {slug}")
        if detail:
            print(f"        {text[:150]}")


def runes(detail: bool) -> None:
    rs = _load("runes.json")
    fx = _load("rune_effects.json")
    # The engine reads BOTH: hand-curated rune_effects.json first, then falls
    # back to the LLM-extracted rune_engine.json. Counting only the first
    # understated coverage as 26/53 when it is really 37/53.
    eng = _load("rune_engine.json") if (DATA / "rune_engine.json").exists() else {}
    known = (set(fx.get("keystones", {})) | set(fx.get("minors", {}))
             | {k for k, v in eng.items() if v})

    missing = [r for r in rs if r["name"] not in known]
    print(f"\n{'='*66}\nRUNES  ({len(rs)} total | {len(known & {r['name'] for r in rs})} modeled "
          f"| {len(missing)} UNMODELED)\n{'='*66}")
    by_type: dict[str, list] = {}
    for r in missing:
        by_type.setdefault(r.get("type") or "?", []).append(r)
    for t, group in sorted(by_type.items()):
        print(f"  -- {t} ({len(group)})")
        for r in sorted(group, key=lambda x: x["name"]):
            print(f"     {r['name']}")
            if detail:
                print(f"        {(r.get('description') or '')[:150]}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--detail", action="store_true", help="print each dropped line")
    args = ap.parse_args()
    champions(args.detail)
    items(args.detail)
    runes(args.detail)
    print()


if __name__ == "__main__":
    main()
