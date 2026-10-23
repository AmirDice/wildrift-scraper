"""Build the compact CN Legendary loadout snapshot consumed by the website.

The capture folders remain the source of truth.  This export deliberately:

* keeps only rows whose icons have a name in the website catalogues;
* resolves the capture's ``skills`` tab as summoner-spell pairs;
* records visible coverage separately from the app's reported coverage; and
* selects the newest capture for each champion/lane pair;
* archives every run as a dated snapshot in data/history/cn_loadouts/, so the
  numbers outlive the screenshots they were read from; and
* marks each row with its rank, win rate and pick rate in the previous
  snapshot, which is what the site's movement arrows read.

Run from the repository root:

    python scripts/export_loadouts_for_web.py

Archive an older run from its own capture folder (once, before its
screenshots are deleted):

    python scripts/export_loadouts_for_web.py --archive-only data/captures_loadouts/old
"""

from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
CAPTURES = ROOT / "data" / "captures_loadouts"
WEB_DATA = ROOT / "web-next" / "src" / "data"
PUBLIC = ROOT / "web-next" / "public"
OUTPUT = WEB_DATA / "cn_loadouts.json"
HISTORY = ROOT / "data" / "history" / "cn_loadouts"
#: A previous snapshot this close to the current one is the same run, not a
#: comparison point.
MIN_GAP_DAYS = 1


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def normalized_image(path: Path) -> np.ndarray:
    image = Image.open(path).convert("RGB").resize((32, 32))
    pixels = np.asarray(image, dtype=np.float32)
    return (pixels - pixels.mean()) / (pixels.std() + 1e-6)


def spell_matcher(spells: list[dict[str, Any]]):
    references: dict[str, np.ndarray] = {}
    for spell in spells:
        icon = PUBLIC / str(spell["icon"]).lstrip("/")
        if icon.exists():
            references[str(spell["name"])] = normalized_image(icon)

    def match(path: Path) -> str | None:
        if not path.exists() or not references:
            return None
        sample = normalized_image(path)
        ranked = sorted(
            ((float((sample * reference).mean()), name) for name, reference in references.items()),
            reverse=True,
        )
        best_score, best_name = ranked[0]
        runner_up = ranked[1][0] if len(ranked) > 1 else -1.0
        # Captured spell tiles normally score 0.82-0.93.  A conservative
        # threshold keeps blank or mis-cropped tiles out of the public data.
        if best_score < 0.72 or best_score - runner_up < 0.08:
            return None
        return best_name

    return match


def metrics(row: dict[str, Any]) -> tuple[float, float] | None:
    win_rate = finite(row.get("winRate"))
    pick_rate = finite(row.get("pickRate"))
    if win_rate is None or pick_rate is None:
        return None
    if not (0 <= win_rate <= 100 and 0 <= pick_rate <= 100):
        return None
    return round(win_rate, 2), round(pick_rate, 2)


def clean_named_rows(
    rows: list[dict[str, Any]],
    *,
    count: int,
    allowed: set[str],
    key: str,
) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for row in rows:
        values = [str(entity.get(key, "")).strip() for entity in row.get("entities", [])]
        if len(values) != count or any(not value or value == "?" or value not in allowed for value in values):
            continue
        # Duplicate items/runes in a single row signal a bad icon read.
        if len(set(values)) != len(values):
            continue
        row_metrics = metrics(row)
        if row_metrics is None:
            continue
        win_rate, pick_rate = row_metrics
        cleaned.append(
            {
                "rank": int(row.get("rank") or len(cleaned) + 1),
                "winRate": win_rate,
                "pickRate": pick_rate,
                "entities": values,
            }
        )
    return cleaned


def clean_matchups(rows: list[dict[str, Any]], champions: set[str]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for row in rows:
        entities = row.get("entities", [])
        if len(entities) != 1:
            continue
        champion = str(entities[0].get("champion", "")).strip()
        if champion not in champions:
            continue
        row_metrics = metrics(row)
        if row_metrics is None:
            continue
        win_rate, pick_rate = row_metrics
        cleaned.append(
            {
                "rank": int(row.get("rank") or len(cleaned) + 1),
                "winRate": win_rate,
                "pickRate": pick_rate,
                "entities": [champion],
            }
        )
    return cleaned


def clean_spells(
    rows: list[dict[str, Any]],
    capture: Path,
    match_spell,
) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for row in rows:
        names: list[str] = []
        for entity in row.get("entities", []):
            icon_name = str(entity.get("icon", "")).strip()
            name = match_spell(capture / "icons" / icon_name) if icon_name else None
            if name:
                names.append(name)
        if len(names) != 2 or len(set(names)) != 2:
            continue
        row_metrics = metrics(row)
        if row_metrics is None:
            continue
        win_rate, pick_rate = row_metrics
        cleaned.append(
            {
                "rank": int(row.get("rank") or len(cleaned) + 1),
                "winRate": win_rate,
                "pickRate": pick_rate,
                "entities": names,
            }
        )
    return cleaned


def exported_tab(source: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "date": source.get("date"),
        "sourceRows": int(source.get("nRows") or len(source.get("rows", []))),
        "recognizedRows": len(rows),
        "reportedCoverage": round(finite(source.get("pickCoverage")) or 0.0, 2),
        "visibleCoverage": round(sum(row["pickRate"] for row in rows), 2),
        "rows": rows,
    }


def run_date(champions: dict[str, list[dict[str, Any]]]) -> str:
    """The date most of a snapshot's lanes were captured on (YYYY-MM-DD)."""
    counts: dict[str, int] = {}
    for records in champions.values():
        for record in records:
            day = str(record.get("capturedAt") or "")[:10]
            if day:
                counts[day] = counts.get(day, 0) + 1
    return max(counts, key=counts.get) if counts else datetime.now(timezone.utc).strftime("%Y-%m-%d")


def archive(output: dict[str, Any]) -> Path:
    """Write the snapshot under its run date, refusing to replace a fuller
    snapshot with an emptier one (a half-failed extraction must not erase
    the record it was meant to extend)."""
    HISTORY.mkdir(parents=True, exist_ok=True)
    path = HISTORY / f"{run_date(output['champions'])}.json"
    if path.exists():
        existing = load_json(path)
        if existing.get("coverage", {}).get("lanePages", 0) > output["coverage"]["lanePages"]:
            print(f"Kept {path.relative_to(ROOT)}: it has more lane pages than this run")
            return path
    path.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Archived {path.relative_to(ROOT)}")
    return path


def previous_snapshot(current_date: str) -> dict[str, Any] | None:
    """The newest archived snapshot from an earlier run."""
    if not HISTORY.exists():
        return None
    current = datetime.fromisoformat(current_date)
    earlier = sorted(
        path for path in HISTORY.glob("*.json")
        if (current - datetime.fromisoformat(path.stem)).days >= MIN_GAP_DAYS
    )
    return load_json(earlier[-1]) if earlier else None


def row_key(row: dict[str, Any]) -> str:
    return " + ".join(str(entity) for entity in row.get("entities") or [])


def attach_movement(output: dict[str, Any], previous: dict[str, Any]) -> int:
    """Give every row its numbers from the previous snapshot.

    `prev` holds the old rank, win rate and pick rate; a row the previous
    snapshot did not list is `new`. Lanes the previous run did not capture
    get neither, so no row claims a movement it cannot show.
    """
    marked = 0
    for slug, records in output["champions"].items():
        before = {record["lane"]: record for record in previous.get("champions", {}).get(slug, [])}
        for record in records:
            old = before.get(record["lane"])
            if not old or str(old.get("capturedAt"))[:10] >= str(record.get("capturedAt"))[:10]:
                continue
            record["previousCapturedAt"] = old.get("capturedAt")
            for name, tab in record["tabs"].items():
                old_tab = old.get("tabs", {}).get(name, {})
                old_rows = {row_key(row): row for row in old_tab.get("rows", [])}
                if not old_rows:
                    continue
                # A row is only "new" if the previous run read the whole tab:
                # Riven's Baron items had 8 of their rows recognised on Oct 11
                # and 14 on Oct 15, and a core the old pass failed to read is
                # not a core players started building.
                old_complete = old_tab.get("recognizedRows", 0) >= old_tab.get("sourceRows", 0) > 0
                for row in tab["rows"]:
                    match = old_rows.get(row_key(row))
                    if match:
                        row["prev"] = {"rank": match.get("rank"), "winRate": match.get("winRate"),
                                       "pickRate": match.get("pickRate")}
                    elif old_complete:
                        row["new"] = True
                    else:
                        continue
                    marked += 1
    return marked


#: The site's balance score (web-next/src/lib/loadout-score.ts), mirrored so
#: the weekly pick is chosen here the same way the page chooses today's.
PRIOR = 15
RECOMMEND_MIN_PICK = 3
#: How far back "this week" reaches from the newest capture of a lane.
WEEK_DAYS = 7
#: Points kept in each row's trend.
TREND_POINTS = 8
#: Tabs that are pooled and trended. Matchups stay on the latest capture.
POOLED_TABS = ("items", "runes", "boots", "spells")


def _recommended(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    total = sum(row["pickRate"] for row in rows)
    if not total:
        return None
    average = sum(row["winRate"] * row["pickRate"] for row in rows) / total
    eligible = [row for row in rows if row["pickRate"] >= RECOMMEND_MIN_PICK]
    if not eligible:
        return None
    return max(eligible, key=lambda row: (row["winRate"] * row["pickRate"] + average * PRIOR)
               / (row["pickRate"] + PRIOR))


def attach_week_and_trend(output: dict[str, Any]) -> tuple[int, int]:
    """Pool each lane's captures from the last WEEK_DAYS, and trend each row.

    A single capture is one day of China's numbers, and between captures the
    recommended core changed for ~70% of lanes while the most-played cores
    barely moved: the top few are usually within a point of each other. So the
    week is pooled -- win rate weighted by pick share, pick rate averaged over
    the captures (a row absent from one counts 0 there) -- and the weekly pick
    is the balance score on the pooled rows. `bestIn` counts the captures in
    which a row was that day's pick, so one lucky day cannot pass for a habit.

    Pooling weights each day by pick SHARE: the app gives no game counts, so
    this assumes the days had similar volume.
    """
    snapshots = []
    for path in sorted(HISTORY.glob("????-??-??.json")):
        doc = load_json(path)
        if isinstance(doc.get("champions"), dict):
            snapshots.append(doc)
    pooled_lanes = trended = 0
    for slug, records in output["champions"].items():
        for record in records:
            # Every archived capture of this lane, oldest first, one per day.
            by_day: dict[str, dict[str, Any]] = {}
            for doc in snapshots:
                for old in doc["champions"].get(slug, []):
                    if old.get("lane") == record["lane"]:
                        by_day[str(old.get("capturedAt"))[:10]] = old
            by_day[str(record.get("capturedAt"))[:10]] = record
            days = sorted(by_day)
            latest = datetime.fromisoformat(days[-1])
            week = [d for d in days if (latest - datetime.fromisoformat(d)).days < WEEK_DAYS]
            for name in POOLED_TABS:
                tab = record["tabs"].get(name)
                if not tab:
                    continue
                # Trends live on the week rows only: the latest capture is
                # part of the week, so its rows find theirs there, and a copy
                # on both doubled the file to 3.5 MB.
                history = [(d, {row_key(r): r for r in by_day[d]["tabs"].get(name, {}).get("rows", [])})
                           for d in days[-TREND_POINTS:]]
                captures = [(d, by_day[d]["tabs"].get(name, {}).get("rows", [])) for d in week]
                captures = [(d, rows) for d, rows in captures if rows]
                if len(captures) < 2:
                    continue
                daily_best = {d: row_key(best) for d, rows in captures if (best := _recommended(rows))}
                acc: dict[str, dict[str, Any]] = {}
                for d, rows in captures:
                    for row in rows:
                        a = acc.setdefault(row_key(row), {"entities": row["entities"], "wr": 0.0, "pick": 0.0, "seen": 0})
                        a["wr"] += row["winRate"] * row["pickRate"]
                        a["pick"] += row["pickRate"]
                        a["seen"] += 1
                pooled = []
                for key, a in acc.items():
                    pooled.append({
                        "entities": a["entities"],
                        "winRate": round(a["wr"] / a["pick"], 2) if a["pick"] else 0.0,
                        "pickRate": round(a["pick"] / len(captures), 2),
                        "seen": a["seen"],
                        "bestIn": sum(1 for best in daily_best.values() if best == key),
                        "trend": [[d[5:], rr[key]["winRate"], rr[key]["pickRate"]]
                                  for d, rr in history if key in rr],
                    })
                trended += len(pooled)
                pooled.sort(key=lambda row: -row["pickRate"])
                for rank, row in enumerate(pooled, 1):
                    row["rank"] = rank
                best = _recommended(pooled)
                tab["week"] = {
                    "from": captures[0][0], "to": captures[-1][0], "captures": len(captures),
                    "best": row_key(best) if best else None,
                    "rows": pooled,
                }
            pooled_lanes += 1
    return pooled_lanes, trended


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--archive-only", type=Path, default=None,
                    help="build a snapshot from this capture folder alone and archive it, "
                         "without touching the website data")
    args = ap.parse_args()
    captures = args.archive_only.resolve() if args.archive_only else CAPTURES
    site = load_json(WEB_DATA / "site.json")
    items = load_json(WEB_DATA / "items.json")
    runes = load_json(WEB_DATA / "rune_icons.json")
    spells = load_json(WEB_DATA / "spells.json")

    champion_by_name = {champion["name"]: champion["slug"] for champion in site["champions"]}
    champion_names = set(champion_by_name)
    item_names = {item["name"] for item in items}
    rune_names = set(runes)
    match_spell = spell_matcher(spells)

    newest: dict[tuple[str, str], tuple[datetime, Path, dict[str, Any]]] = {}
    for path in captures.rglob("loadouts.json"):
        payload = load_json(path)
        champion = str(payload.get("champion", "")).strip()
        lane = str(payload.get("lane", "")).strip().lower()
        if champion not in champion_by_name or not lane:
            continue
        try:
            captured_at = datetime.fromisoformat(str(payload.get("capturedAt")))
        except ValueError:
            captured_at = datetime.min
        key = champion, lane
        if key not in newest or captured_at > newest[key][0]:
            newest[key] = captured_at, path.parent, payload

    champions: dict[str, list[dict[str, Any]]] = {}
    totals = {"lanes": 0, "items": 0, "boots": 0, "runes": 0, "spells": 0, "versus": 0}

    for (champion, lane), (_, capture, payload) in sorted(newest.items()):
        tabs = payload.get("tabs", {})
        versus_source = tabs.get("versus") or {}
        item_source = tabs.get("equip") or {}
        boots_source = tabs.get("boots") or {}
        rune_source = tabs.get("runes") or {}
        spell_source = tabs.get("skills") or {}

        versus_rows = clean_matchups(list(versus_source.get("rows") or []), champion_names)
        item_rows = clean_named_rows(
            list(item_source.get("rows") or []), count=3, allowed=item_names, key="name"
        )
        boots_rows = clean_named_rows(
            list(boots_source.get("rows") or []), count=1, allowed=item_names, key="name"
        )
        rune_rows = clean_named_rows(
            list(rune_source.get("rows") or []), count=5, allowed=rune_names, key="name"
        )
        spell_rows = clean_spells(list(spell_source.get("rows") or []), capture, match_spell)

        kind = str(versus_source.get("versusKindRead") or payload.get("versusKind") or "matchup")
        if kind not in {"matchup", "partners"}:
            kind = "matchup"

        record = {
            "lane": lane,
            "capturedAt": payload.get("capturedAt"),
            "bracket": payload.get("bracket") or "legendary",
            "mode": payload.get("mode") or "classic-ranked",
            "versusKind": kind,
            "tabs": {
                "items": exported_tab(item_source, item_rows),
                "runes": exported_tab(rune_source, rune_rows),
                "boots": exported_tab(boots_source, boots_rows),
                "spells": exported_tab(spell_source, spell_rows),
                "versus": exported_tab(versus_source, versus_rows),
            },
        }
        slug = champion_by_name[champion]
        champions.setdefault(slug, []).append(record)
        totals["lanes"] += 1
        totals["items"] += len(item_rows)
        totals["boots"] += len(boots_rows)
        totals["runes"] += len(rune_rows)
        totals["spells"] += len(spell_rows)
        totals["versus"] += len(versus_rows)

    lane_order = {"baron": 0, "jungle": 1, "mid": 2, "dragon": 3, "support": 4}
    for records in champions.values():
        records.sort(key=lambda record: lane_order.get(record["lane"], 99))

    all_slugs = {champion["slug"] for champion in site["champions"]}
    captured_slugs = set(champions)
    missing = sorted(all_slugs - captured_slugs)
    output = {
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source": "CN server · Legendary ranked",
        "coverage": {
            "champions": len(captured_slugs),
            "totalChampions": len(all_slugs),
            "lanePages": totals["lanes"],
            "missing": missing,
        },
        "recognizedRows": {key: value for key, value in totals.items() if key != "lanes"},
        "champions": champions,
    }
    if args.archive_only:
        archive(output)
        return
    archive(output)
    previous = previous_snapshot(run_date(champions))
    if previous:
        marked = attach_movement(output, previous)
        print(f"Movement against the {run_date(previous['champions'])} snapshot: {marked} rows")
    else:
        print("No earlier snapshot: rows carry no movement yet")
    lanes, rows = attach_week_and_trend(output)
    print(f"Week and trend: {lanes} lanes, {rows} rows trended")
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(
        f"Wrote {OUTPUT.relative_to(ROOT)}: "
        f"{len(captured_slugs)}/{len(all_slugs)} champions, {totals['lanes']} lane pages, "
        f"{OUTPUT.stat().st_size / 1024:.1f} KiB"
    )
    print("Missing:", ", ".join(missing) or "none")
    print("Recognized rows:", {key: value for key, value in totals.items() if key != "lanes"})


if __name__ == "__main__":
    main()
