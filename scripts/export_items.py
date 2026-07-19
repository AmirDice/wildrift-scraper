"""Export the clean item DB to the frontend for the /items page.

Source: data/items.json (the scraped, patch-7.2 item DB, icons already rehosted
to /items/<slug>.webp). We copy the display fields and clean the passive text:
wr-meta embeds stat-icon markers like "[physicalVamp]" which we either drop
(when they're a leading icon before a number) or expand to words (inline refs).

Output: web-next/src/data/items.json

Run:
    python -m scripts.export_items
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "items.json"
OUT = ROOT / "web-next" / "src" / "data" / "items.json"


def _prettify(token: str) -> str:
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", token)
    return spaced[:1].upper() + spaced[1:]


def _clean_passive(text: str) -> str:
    # icon marker directly before a +/number (e.g. "[physicalVamp] +8%") -> drop
    text = re.sub(r"\[([a-zA-Z]+)\]\s+(?=[+\d])", "", text)
    # remaining inline references (e.g. "total [crit] gain") -> spaced word
    text = re.sub(r"\[([a-zA-Z]+)\]", lambda m: _prettify(m.group(1)), text)
    return re.sub(r"\s{2,}", " ", text).strip()


def main() -> None:
    raw = json.loads(SRC.read_text(encoding="utf-8"))
    rows = raw if isinstance(raw, list) else list(raw.values())
    out = []
    for it in rows:
        out.append({
            "slug": it["slug"],
            "name": it["name"],
            "cost": it.get("cost", 0),
            "icon": it.get("icon"),
            "category": it.get("category", ""),
            "categories": it.get("categories", []),
            "tags": it.get("tags", []),
            "stats": it.get("stats", {}),
            "passives": [_clean_passive(p) for p in (it.get("passives") or [])],
        })
    out.sort(key=lambda x: (x["category"], -x["cost"], x["name"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(out)} items ({OUT.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
