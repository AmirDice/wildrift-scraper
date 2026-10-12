"""Build the compact CN Legendary loadout snapshot consumed by the website.

The capture folders remain the source of truth.  This export deliberately:

* keeps only rows whose icons have a name in the website catalogues;
* resolves the capture's ``skills`` tab as summoner-spell pairs;
* records visible coverage separately from the app's reported coverage; and
* selects the newest capture for each champion/lane pair.

Run from the repository root:

    python scripts/export_loadouts_for_web.py
"""

from __future__ import annotations

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


def main() -> None:
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
    for path in CAPTURES.rglob("loadouts.json"):
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
        "source": "CN companion app · Legendary ranked",
        "coverage": {
            "champions": len(captured_slugs),
            "totalChampions": len(all_slugs),
            "lanePages": totals["lanes"],
            "missing": missing,
        },
        "recognizedRows": {key: value for key, value in totals.items() if key != "lanes"},
        "champions": champions,
    }
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
