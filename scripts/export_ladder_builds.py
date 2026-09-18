"""Trim data/ladder_consensus.json for the Custom Lab's opponent picker.

The consensus file records what each champion's top-50 ladder players actually
equip (items, keystones, minors, each with count/of). The Lab wants the same
facts client-side so the duel opponent can stand on "the most common build"
rather than our recommended one -- but the full file is 260KB and the Lab only
needs the head of each list.

    python -m scripts.export_ladder_builds
    python -m scripts.export_ladder_builds --region na

Writes web-next/src/data/ladder_builds[_<region>].json. Re-run after every
ladder collection (whenever that region's ladder_consensus is rebuilt), or the
Lab's "most common" opponent quietly falls behind the boards.

PER SERVER, because that is the question the champion pages and the Build
Studio now ask: what do the top 50 on THIS server build. EU keeps the
unsuffixed name every other reader already imports; a new region gets its own
file, and the site treats a missing file as "not collected yet" rather than
falling back to another server's answer.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "ladder_consensus.json"
OUT = ROOT / "web-next" / "src" / "data" / "ladder_builds.json"
REGIONS = ("eu", "na")

ITEMS_KEPT = 10
KEYSTONES_KEPT = 3
MINORS_KEPT = 8


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--region", default="eu", choices=REGIONS,
                    help="which server's consensus to trim (default: eu)")
    args = ap.parse_args()
    suffix = "" if args.region == "eu" else f"_{args.region}"
    src = SRC.with_name(f"ladder_consensus{suffix}.json")
    out_path = OUT.with_name(f"ladder_builds{suffix}.json")
    if not src.exists():
        raise SystemExit(
            f"no {args.region.upper()} consensus at {src.relative_to(ROOT)}. "
            f"Build it first: python -m scripts.build_ladder_pulse --region {args.region}")
    consensus = json.loads(src.read_text(encoding="utf-8"))
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
    out_path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")),
                        encoding="utf-8")
    size = out_path.stat().st_size
    print(f"wrote {out_path} ({len(out)} champions, {size / 1024:.0f}KB)")


if __name__ == "__main__":
    main()
