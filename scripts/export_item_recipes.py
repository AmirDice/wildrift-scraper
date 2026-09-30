"""Extract current completed-item recipes from the official 7.3 patch data.

The item scrape contains completed stats but not the shop graph.  The 7.3
notes do contain authoritative build-path lines for the items whose paths
changed in that patch.  Keep those paths separate and optional: the fight
math never treats a missing recipe as an empty recipe, and a later patch can
replace this file without touching item stats.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def load(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def key(value: str) -> str:
    value = (value or "").replace("’", "'").replace("‘", "'")
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def parse_components(value: str) -> list[str]:
    # Use the current (right-hand) path when a patch line contains old → new.
    if "→" in value:
        value = value.rsplit("→", 1)[1]
    if ":" in value:
        value = value.split(":", 1)[1]
    if value.strip().lower() == "no recipe":
        return []
    parts = []
    for raw in value.split("+"):
        component = re.sub(r"\s*\([^)]*\)\s*$", "", raw).strip()
        # Gold-only tails are not components.  Keep names such as B. F. Sword.
        if not component or re.fullmatch(r"[0-9][0-9, ]*", component):
            continue
        component = re.sub(r"^\+\s*", "", component).strip()
        component = component.replace("Vampiric Scepter Scepter", "Vampiric Scepter")
        component = component.replace(" +", "").strip()
        if component and component not in parts:
            parts.append(component)
    return parts


def main() -> None:
    item_rows = load("items.json")
    by_name = {key(row.get("name", "")): row["slug"] for row in item_rows}
    recipes: dict[str, dict] = {}
    notes = load("patch_notes_7_3.json")
    for blade in notes.get("blades", []):
        for block in blade.get("blocks", []):
            title = str(block.get("title") or "").strip()
            slug = by_name.get(key(title))
            if not slug:
                continue
            for line in block.get("lines", []) or []:
                if "build path" not in str(line).lower():
                    continue
                components = parse_components(str(line))
                if components:
                    recipes[slug] = {
                        "components": components,
                        "source": "data/patch_notes_7_3.json",
                        "patch": "7.3",
                    }
                break
    out = {
        "_meta": {
            "source": "data/patch_notes_7_3.json",
            "patch": "7.3",
            "note": "Only authoritative paths printed in the patch notes are included. Missing entries mean recipe data is unavailable, not no recipe.",
        },
        **dict(sorted(recipes.items())),
    }
    (DATA / "item_recipes.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote data/item_recipes.json ({len(recipes)} recipes)")


if __name__ == "__main__":
    main()
