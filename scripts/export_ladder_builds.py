"""Trim data/ladder_consensus.json for the Custom Lab's opponent picker.

The consensus file records what each champion's top-50 ladder players actually
equip (items, keystones, minors, each with count/of). The Lab wants the same
facts client-side so the duel opponent can stand on "the most common build"
rather than our recommended one -- but the full file is 260KB and the Lab only
needs the head of each list.

    python -m scripts.export_ladder_builds

Writes web-next/src/data/ladder_builds.json. Re-run after every ladder
collection (whenever ladder_consensus.json is rebuilt), or the Lab's
"most common" opponent quietly falls behind the boards.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "ladder_consensus.json"
OUT = ROOT / "web-next" / "src" / "data" / "ladder_builds.json"

ITEMS_KEPT = 10
KEYSTONES_KEPT = 3
MINORS_KEPT = 8


def main() -> None:
    consensus = json.loads(SRC.read_text(encoding="utf-8"))
    out = {}
    for name, rec in consensus.items():
        items = [
            {"slug": i["slug"], "count": i["count"], "of": i["of"]}
            for i in (rec.get("items") or [])[:ITEMS_KEPT]
        ]
        keystones = [
            {"name": k["name"], "count": k["count"]}
            for k in (rec.get("keystones") or [])[:KEYSTONES_KEPT]
        ]
        minors = [
            {"name": m["name"], "count": m["count"]}
            for m in (rec.get("minors") or [])[:MINORS_KEPT]
        ]
        if items:
            out[name] = {"items": items, "keystones": keystones, "minors": minors}
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    size = OUT.stat().st_size
    print(f"wrote {OUT} ({len(out)} champions, {size / 1024:.0f}KB)")


if __name__ == "__main__":
    main()
