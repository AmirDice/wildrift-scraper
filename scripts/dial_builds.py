"""Playstyle dial: precompute anchor builds along the damage<->tankiness axis.

For each champion, searches the best legal 5-item build at 5 anchor weightings
(offense/defense): 90/10, 70/30, 50/50, 30/70, 10/90. The user-facing dial
snaps to the nearest anchor and shows that build with its engine metrics.

ZERO LLM calls: the candidate pool is the union of the item pools already
stored by the variant searches (searched.pool), so this is pure engine compute.
Runes/boots are borrowed from the champion's nearest generated variant.

Identity bounds derive from the dial position (tank items unlock as tankiness
rises; full tank stays Tank-class-only). Reactive items stay banned.

Output: a `dial` list on each champion in data/champion_builds.json.

Run:
    python -m scripts.dial_builds --only "Hecarim"
    python -m scripts.dial_builds
"""
from __future__ import annotations

import argparse
import json
from itertools import combinations
from pathlib import Path

from scripts.search_builds import (IDENTITY_BOUNDS, SITUATIONAL_ONLY, greedy_order,
                                   is_defensive, is_tank, legal)
from web.fight_engine import FORMULAS, ITEMS, _build_lists, attack_profile, score_items

ROOT = Path(__file__).resolve().parent.parent
BUILDS = ROOT / "data" / "champion_builds.json"
WEB_OUT = ROOT / "web-next" / "src" / "data" / "builds.json"

# (offense weight, tank_min, tank_max, def_min, def_max, nearest variant kind)
ANCHORS = [
    (0.90, 0, 0, 0, 1, "damage"),
    (0.70, 0, 1, 0, 2, "damage"),
    (0.50, 0, 2, 1, 3, "balanced"),
    (0.30, 1, 3, 2, 4, "tanky"),
    (0.10, 2, 4, 3, 5, "tanky"),
]
DAMAGE_LIKE = ("damage", "dps", "oneshot", "burst", "crit", "antitank", "poke")
TANK_LIKE = ("tanky", "survivability")


def style_for(name: str, rec: dict) -> dict:
    """Grounded auto-vs-ability classification, measured on the champion's
    highest-damage build (that's where the playstyle shows most clearly)."""
    builds = rec.get("builds") or {}
    key = next((k for k in ("damage", "dps", "crit", "oneshot", "burst", "standard", "balanced", "poke")
                if k in builds), next(iter(builds), None))
    if not key:
        return attack_profile(name)
    items, runes = _build_lists(builds[key])
    return attack_profile(name, items, runes)


def _nearest_variant(rec: dict, kind: str) -> tuple[str, dict] | None:
    builds = rec.get("builds") or {}
    prefs = {"damage": DAMAGE_LIKE, "tanky": TANK_LIKE,
             "balanced": ("standard", "balanced", "sustained", "battlemage", "utility")}[kind]
    for v in prefs:
        if v in builds:
            return v, builds[v]
    return (next(iter(builds.items()))) if builds else None

def dial_for(name: str, rec: dict) -> list[dict]:
    role = rec.get("role", "")
    # candidate pool = union of every variant's stored search pool
    pool: list[str] = []
    for bd in (rec.get("builds") or {}).values():
        for s in (bd.get("searched") or {}).get("pool") or []:
            if s in ITEMS and s not in pool and s not in SITUATIONAL_ONLY:
                pool.append(s)
    if len(pool) < 8:
        return []

    out = []
    for w_off, t_lo, t_hi, d_lo, d_hi, kind in ANCHORS:
        nv = _nearest_variant(rec, kind)
        if not nv:
            continue
        variant, bd = nv
        _, runes = _build_lists(bd)
        boots = bd.get("boots", {}).get("slug") if bd.get("boots") else None
        if rec.get("class") == "Tank" and w_off <= 0.30:
            t_hi, d_hi = 5, 5  # true tanks may go full tank at the tanky end
        tl, dl = t_lo, d_lo
        if sum(1 for s in pool if is_tank(s)) < tl:
            tl = 0
        if sum(1 for s in pool if is_defensive(s)) < dl:
            dl = 0
        weights = (w_off, 1 - w_off)

        best: tuple[float, tuple[str, ...] | None] = (float("-inf"), None)
        for combo in combinations(pool, 5):
            if not legal(combo):
                continue
            n_tank = sum(1 for s in combo if is_tank(s))
            n_def = sum(1 for s in combo if is_defensive(s))
            if not (tl <= n_tank <= t_hi and dl <= n_def <= d_hi):
                continue
            items = list(combo) + ([boots] if boots else [])
            s = score_items(name, items, runes, variant, role, fast=True,
                            weights=weights)["score"]
            if s > best[0]:
                best = (s, combo)
        if not best[1]:
            continue
        ordered = greedy_order(name, list(best[1]), boots, runes, variant, role)
        items = ordered + ([boots] if boots else [])
        m = score_items(name, items, runes, variant, role, weights=weights)
        out.append({
            "offense": int(w_off * 100),
            "variantRunes": variant,
            "items": [{"slug": s, "name": ITEMS[s]["name"], "cost": ITEMS[s]["cost"],
                       "icon": ITEMS[s]["icon"]} for s in ordered],
            "boots": ({"slug": boots, "name": ITEMS[boots]["name"],
                       "icon": ITEMS[boots]["icon"]} if boots and boots in ITEMS else None),
            "engine": m,
        })
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    builds = json.loads(BUILDS.read_text(encoding="utf-8"))
    only = {n.strip() for n in args.only.split(",") if n.strip()}
    names = [n for n in builds if (not only or n in only) and n in FORMULAS]
    print(f"{len(names)} champions to dial")

    for name in names:
        style = style_for(name, builds[name])
        builds[name]["attackStyle"] = style
        anchors = dial_for(name, builds[name])
        if not anchors:
            print(f"  ! {name}: no pool stored — run search_builds first")
            continue
        builds[name]["dial"] = anchors
        spread = " | ".join(f"{a['offense']}%: {a['engine']['score']:g}" for a in anchors)
        flag = "  [FLAGGED formulas]" if style["dataQuality"] == "flagged" else ""
        print(f"  {name:12} {style['style']:>14} ({style['autoness']:.2f}){flag}")
        print(f"  {'':12} {spread}")
        payload = json.dumps(builds, ensure_ascii=False, indent=2)
        BUILDS.write_text(payload, encoding="utf-8")
        WEB_OUT.write_text(payload, encoding="utf-8")

    print("\ndial complete")


if __name__ == "__main__":
    main()
