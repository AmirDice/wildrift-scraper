"""Sanity report for the CN Legendary loadout snapshot (cn_loadouts.json).

Run after every `python scripts/export_loadouts_for_web.py`:

    python scripts/check_loadouts.py

The icon matcher can read a page perfectly and the page can still be wrong
for our purposes. Ahri mid on 2026-11-17 is the reference case: the app
itself showed Trinity Force + Black Cleaver cores on a mage, on 2 rows, and
every icon matched at 0.94+. So this checks the DATA, not the read:

  sparse      item tab with fewer than MIN_ITEM_ROWS rows (a near-empty page)
  stale       a tab dated more than MAX_TAB_AGE_DAYS before its capture
              (boots is reported once in total: the app's boots page has been
              frozen at July 2026 for every champion)
  disagrees   item cores share < MIN_LADDER_OVERLAP of their items, pick
              weighted, with what our own EU/NA top 30 build. Can be a real
              regional meta (Swain/Wukong tank builds) -- review, do not auto-drop.
  low-match   an icon matched below LOW_SCORE (only when capture files exist)

The advisor applies the same rules when it builds a prompt
(web/advisor/prompt.py: official_builds_block): sparse and stale tabs are
dropped, and a disagreeing page is shown with a caution line.

Exit code is 0 either way; this is a report, not a gate.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from web.advisor import prompt as pm  # noqa: E402

LOW_SCORE = 0.85


def low_match_icons(champion: str, lane: str) -> list[str]:
    """Icons matched below LOW_SCORE in the newest capture for this page."""
    from src.capture_runs import all_runs
    best = None
    for root in all_runs("loadouts"):
        for path in root.glob(f"{champion}_{lane}_*/loadouts.json"):
            if best is None or path.parent.name > best.parent.name:
                best = path
    if best is None:
        return []
    payload = json.loads(best.read_text(encoding="utf-8"))
    out = []
    for tab_name, tab in (payload.get("tabs") or {}).items():
        for row in (tab or {}).get("rows") or []:
            for ent in row.get("entities") or []:
                score = ent.get("score")
                if isinstance(score, (int, float)) and score < LOW_SCORE:
                    out.append(f"{tab_name} r{row.get('rank')}: {ent.get('name')} ({score:.2f})")
    return out


def main() -> None:
    store = pm._official_store()
    champions = store.get("champions") or {}
    problems: list[tuple[str, str, list[str]]] = []
    boots_dates: Counter = Counter()
    pages = 0
    for slug, entries in sorted(champions.items()):
        for rec in entries:
            pages += 1
            lane = rec.get("lane", "")
            issues = []
            tabs = rec.get("tabs") or {}
            items = tabs.get("items") or {}
            rows = items.get("rows") or []
            if rows and len(rows) < pm.MIN_ITEM_ROWS:
                issues.append(f"sparse: {len(rows)} item rows")
            for name, tab in tabs.items():
                if not tab:
                    continue
                if name == "boots":
                    boots_dates[str(tab.get("date"))[:6]] += 1
                    continue
                if tab.get("rows") and not pm._tab_fresh(rec, tab):
                    issues.append(f"stale: {name} dated {tab.get('date')}")
            overlap = pm.ladder_overlap(slug, rec)
            if overlap is not None and overlap < pm.MIN_LADDER_OVERLAP:
                top = sorted(rows, key=lambda r: -(r.get("pickRate") or 0))[:1]
                issues.append(f"disagrees: {overlap:.0%} overlap with EU/NA ladder, top core "
                              f"{' + '.join(top[0]['entities']) if top else '-'}")
            if issues:
                issues += [f"low-match: {x}" for x in low_match_icons(slug, lane)]
                problems.append((slug, lane, issues))

    print(f"cn_loadouts.json: {pages} lane pages, generated {store.get('generatedAt', '?')}")
    months = ", ".join(f"{m[:4]}-{m[4:]}: {n}" for m, n in sorted(boots_dates.items()))
    print(f"boots tab dates by month (the app's boots page is frozen): {months}")
    print(f"{len(problems)} pages to review:")
    for slug, lane, issues in problems:
        print(f"  {slug} {lane}")
        for issue in issues:
            print(f"    - {issue}")


if __name__ == "__main__":
    main()
