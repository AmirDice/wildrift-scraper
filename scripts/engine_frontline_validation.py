"""Validate the production engine tournament on a small frontline sample.

This is intentionally model-free.  It supplies one legal, identity-consistent
seed for every production damage archetype, then calls the same
``build_advisor._engine_challenger`` used by the API.  Unlike the historical
frontline sweep, the report therefore includes the production item-pool gate,
identity-combo gate, adaptive frontier and engine purchase-order projection.

The default sample is deliberately small so changes can be checked before a
full 50-champion frontline run:

    python -m scripts.engine_frontline_validation
"""
from __future__ import annotations

import argparse
import itertools
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from web import build_advisor as adv  # noqa: E402
from web import fight_engine as fe  # noqa: E402
from web.advisor import itemmeta, profiles, supportitem, validate as validate_mod  # noqa: E402
from web.champion_roles import primary_role  # noqa: E402


DEFAULT_CHAMPIONS = ["Sett", "Hecarim", "Olaf", "Rammus", "Malphite"]
BIASES = ["balanced", "max_damage", "max_durability"]


def _page() -> dict:
    """Return one real legal page, in the schema the production challenger uses."""
    raw = fe.legal_rune_pages("Precision", "Conqueror", limit=1)
    if not raw:
        raise RuntimeError("the production rune catalog has no legal Precision page")
    page = raw[0]
    return {
        "keystone": page[0],
        "primaryTree": "Precision",
        "minors": page[1:4],
        "flex": page[4],
    }


def _identity_errors(champion: str, items: list[str]) -> list[str]:
    card = adv.prompt_mod.identity_card(champion)
    champion_class = (adv.CHAMPS.get(champion) or {}).get("class", "")
    errors = []
    for slug in items:
        errors.extend(validate_mod.identity_violations(
            [slug], card, champion_name=champion, champion_class=champion_class))
    errors.extend(validate_mod.identity_combo_violations(
        items, card, champion_name=champion, champion_class=champion_class))
    return errors


def _seed_for_path(champion: str, path: str, eligible: list[str], role: str = "") -> list[str]:
    """Find a legal five-item seed without hand-coding champion item builds."""
    rng = random.Random(f"frontline-validation:{champion}:{path}")

    def legal(combo: list[str]) -> bool:
        if len(combo) != 5 or len(set(combo)) != 5:
            return False
        if validate_mod.hard_exclusive_violation(combo):
            return False
        if _identity_errors(champion, combo):
            return False
        return adv._combo_matches_archetype(tuple(combo), path)

    mandatory_support = (
        sorted(s for s in eligible if s in supportitem.SUPPORT_ITEMS)
        if supportitem.is_support(role) else []
    )

    # Random combinations make this cheap even for a 60-item bruiser path,
    # while the deterministic fallback keeps the result reproducible if the
    # catalog becomes unusually small.
    for _ in range(25_000):
        if mandatory_support:
            support_slug = rng.choice(mandatory_support)
            rest = [s for s in eligible if s not in supportitem.SUPPORT_ITEMS]
            combo = [support_slug, *rng.sample(rest, 4)]
        else:
            combo = rng.sample(eligible, 5)
        if legal(combo) and supportitem.build_is_legal(combo, role):
            return combo
    for combo in itertools.combinations(eligible[:32], 5):
        combo = list(combo)
        if legal(combo) and supportitem.build_is_legal(combo, role):
            return combo
    raise RuntimeError(
        f"no identity-safe seed for {champion} / {path} from {len(eligible)} items")


def _production_inputs(champion: str) -> tuple[str, list[str], list[dict], list[dict]]:
    role = primary_role(champion).lower()
    profile = profiles.profile(champion, log=False)
    record = adv.CHAMPS.get(champion) or {}
    pool, _withheld = itemmeta.filter_candidates(
        record, profile["combatProfile"], profile["scalingProfile"],
        damage_path="standard", enemies_known=False, role=role)
    paths = adv._damage_archetypes(
        champion, profile["combatProfile"], profile["scalingProfile"], "standard")
    page = _page()
    summoners = ["Flash", "Smite"] if role == "jungle" else ["Flash", "Ignite"]
    candidates = []
    seed_meta = []
    for index, row in enumerate(paths):
        path = row["id"]
        eligible = [
            slug for slug in pool
            if adv._item_supports_archetype(slug, path)
            and adv._identity_item_allowed(champion, slug)
        ]
        if supportitem.is_support(role):
            eligible = sorted(set(eligible) | {
                slug for slug in pool if slug in supportitem.SUPPORT_ITEMS
                and adv._identity_item_allowed(champion, slug)
            })
        items = _seed_for_path(champion, path, eligible, role)
        candidates.append({
            "id": f"SEED-{index + 1}",
            "archetype": path,
            "hypothesis": "identity-safe validation seed; engine chooses the result",
            "items": items,
            "boots": "plated-steelcaps" if path == "tank-frontline" else "boots-of-dynamism",
            "runes": dict(page),
            "summoners": list(summoners),
        })
        seed_meta.append({"archetype": path, "eligibleItems": len(eligible), "items": items})
    return role, pool, candidates, seed_meta


def _check_build(champion: str, row: dict, candidates: list[dict]) -> dict:
    items = list(row.get("items") or [])
    errors = []
    if len(items) != 5 or len(set(items)) != 5:
        errors.append("five unique completed items expected")
    errors.extend(_identity_errors(champion, items))
    if adv.ITEMS.get(row.get("boots") or "", {}).get("bootsTier") != 2:
        errors.append("engine result does not have a tier-2 boot")
    if validate_mod.hard_exclusive_violation(items):
        errors.append("hard-exclusive item conflict")
    if not adv.ITEMS.get(row.get("boots") or ""):
        errors.append("unknown boots")
    ordered = adv._ordered_engine_items(tuple(items), candidates)
    return {
        "items": items,
        "purchaseOrderProjection": ordered,
        "boots": row.get("boots"),
        "archetype": row.get("archetype"),
        "identityErrors": errors,
        "valid": not errors,
    }


def run(champions: list[str]) -> dict:
    started = time.time()
    runs = []
    for champion in champions:
        role, pool, candidates, seed_meta = _production_inputs(champion)
        klass = (adv.CHAMPS.get(champion) or {}).get("class", "")
        for bias in BIASES:
            one_started = time.time()
            challenger, meta = adv._engine_challenger(
                champion, candidates, role=role, enemies_known=False,
                skill_level="average", build_bias=bias,
                allowed_items=pool,
                priority_items=["thornmail"] if champion == "Rammus" else [],
                return_top=3,
            )
            top = []
            for row in meta.get("topEngineBuilds") or []:
                projected = _check_build(champion, row, candidates)
                projected["score"] = row.get("score")
                projected["runes"] = row.get("runes")
                top.append(projected)
            winner = None
            if challenger:
                winner = {
                    "id": challenger.get("id"),
                    "items": list(challenger.get("items") or []),
                    "boots": challenger.get("boots"),
                    "runes": challenger.get("runes"),
                    "archetype": challenger.get("archetype"),
                    "identityErrors": _identity_errors(
                        champion, list(challenger.get("items") or [])),
                    "purchaseOrder": list(challenger.get("items") or []),
                    "valid": not _identity_errors(
                        champion, list(challenger.get("items") or [])),
                }
            run_row = {
                "champion": champion,
                "class": klass,
                "role": role,
                "bias": bias,
                "seconds": round(time.time() - one_started, 1),
                "candidateSeeds": seed_meta,
                "candidateCount": len(candidates),
                "poolSize": len(pool),
                "challenger": winner,
                "topEngineBuilds": top,
                "search": {
                    key: meta.get(key)
                    for key in ("searched", "scenarioEvaluations", "paths",
                                "authoredBestScore", "challengerScore",
                                "objective", "blend", "reason", "engineTie",
                                "runePolicy", "bootPolicy")
                    if key in meta
                },
                "validation": {
                    "topBuilds": len(top),
                    "invalidTopBuilds": sum(not row["valid"] for row in top),
                    "challengerValid": bool(winner and winner["valid"]),
                },
            }
            if not top and not winner:
                run_row["error"] = "engine returned no valid candidate or top build"
            runs.append(run_row)
            best = (winner or (top[0] if top else {}))
            print(
                f"  {champion:10} {bias:15} {run_row['seconds']:>5.1f}s "
                f"{best.get('items', [])} + {best.get('boots', '-')}",
                flush=True,
            )
    report = {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "mode": "production-engine-challenger",
        "modelCalls": 0,
        "identityGate": "production",
        "champions": champions,
        "biases": BIASES,
        "runs": runs,
        "summary": {
            "expectedRuns": len(champions) * len(BIASES),
            "completedRuns": len(runs),
            "errors": sum(1 for row in runs if row.get("error")),
            "invalidTopBuilds": sum(row["validation"]["invalidTopBuilds"] for row in runs),
            "elapsedSeconds": round(time.time() - started, 1),
        },
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("champions", nargs="*", default=DEFAULT_CHAMPIONS)
    parser.add_argument(
        "--all-frontline", action="store_true",
        help="run every current Bruiser and Tank in champions_wr.json",
    )
    parser.add_argument("--out", default="reports/engine_frontline_validation.json")
    args = parser.parse_args()
    champions = args.champions
    if args.all_frontline:
        from web import champion_meta  # local import keeps the five-run path small
        roster = json.loads((ROOT / "data" / "champions_wr.json").read_text(encoding="utf-8"))
        champions = sorted(
            row["name"] for row in roster
            if champion_meta.champion_class(row.get("name")) in {"Bruiser", "Tank"}
        )
    report = run(champions)
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {out} in {report['summary']['elapsedSeconds'] / 60:.1f} minutes", flush=True)
    return 0 if report["summary"]["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
