"""Draw the loadout crop geometry on a real frame, so it can be corrected.

The icon crops have been the problem twice now. First the saturation
runs defined an icon's edges and produced 32px fragments of 89px icons;
that is fixed. What is left is a set of clusters the matcher cannot
name, and the likeliest remaining cause is still the crop -- an inferred
box that is slightly off is invisible in the output and fatal to a
template match.

Inference is the wrong tool for geometry that never moves. This renders
what is CURRENTLY being cropped, with the fractional value of every edge
printed on it, so the panel can be measured once by eye and written
down in coords/loadouts.json instead.

    python -m scripts.calibrate_loadouts --tab equip
    python -m scripts.calibrate_loadouts --tab runes --capture <dir>

Then edit coords/loadouts.json and run it again. The overlay reads the
same overrides the extractor does, so what is drawn is exactly what will
be cropped.

    {"columns": {"entity": [0.165, 0.610]},
     "icons": {"equip": {"centres": [0.14, 0.42, 0.70], "size": 0.26}}}

`columns` are fractions of the FRAME width. `icons.centres` and
`icons.size` are fractions of the ENTITY box, because that is the box
the icons sit inside; both are printed on the overlay.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import loadouts as L  # noqa: E402

CAPTURES = ROOT / "data" / "captures_loadouts"
OUT = ROOT / "data" / "debug_scans"

GREEN = (120, 240, 140)
CYAN = (240, 220, 90)
PINK = (150, 120, 250)
GREY = (170, 170, 170)


def _label(img, text, org, colour, scale=0.42):
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 3,
                cv2.LINE_AA)
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, colour, 1,
                cv2.LINE_AA)


def overlay(image: np.ndarray, tab: str) -> np.ndarray:
    out = image.copy()
    h, w = out.shape[:2]
    rows = L.find_rows(image)
    cols = L.OVERRIDES.get("columns") or {}
    bands = {
        "rank": cols.get("rank", L.RANK_X),
        "entity": cols.get("entity", L.ENTITY_X),
        "winrate": cols.get("winrate", L.WINRATE_X),
        "pickrate": cols.get("pickrate", L.PICKRATE_X),
    }

    # Column bands, drawn full height with their fractions at the top.
    for name, (f0, f1) in bands.items():
        x0, x1 = round(f0 * w), round(f1 * w)
        cv2.rectangle(out, (x0, 0), (x1, h - 1), GREY, 1)
        _label(out, f"{name} {f0:.3f}-{f1:.3f}", (x0 + 4, 18), GREY)

    expected = L.TABS[tab]["icons"]
    slots = L.icon_slots(tab)
    _label(out, f"{tab}: {len(rows)} rows, {expected} icons/row, "
                f"slots {'MEASURED' if slots else 'inferred from the image'}",
           (8, h - 12), CYAN, 0.5)

    for ri, (top, bottom) in enumerate(rows):
        cv2.line(out, (0, top), (w, top), PINK, 1)
        cv2.line(out, (0, bottom), (w, bottom), PINK, 1)
        cells = L.row_cells(image, (top, bottom))
        ex0 = round(bands["entity"][0] * w)
        ew = cells["entity"].shape[1]
        # The SAME spans the extractor crops, not a reconstruction of them.
        # Drawing it any other way is how this overlay first reported two
        # icons on a three-icon row that the segmenter had split correctly.
        spans = L.icon_spans(cells["entity"], expected, tab)
        for ii, (x0, x1) in enumerate(spans):
            iw = x1 - x0
            ax0 = ex0 + x0
            colour = GREEN if iw > 0.5 * (bottom - top) else (90, 90, 250)
            cv2.rectangle(out, (ax0, top), (ax0 + iw, bottom), colour, 2)
            if ri == 0:
                frac = (x0 + iw / 2) / max(1, ew)
                _label(out, f"{ii}: c={frac:.3f} w={iw}px",
                       (ax0 + 2, top - 6), colour, 0.38)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tab", default="equip", choices=sorted(L.TABS),
                    help="which tab's geometry to draw (default: equip)")
    ap.add_argument("--capture", type=Path, default=None,
                    help="a capture directory; default is the first on disk")
    ap.add_argument("--frame", type=int, default=0,
                    help="which frame of that tab (default: the first)")
    args = ap.parse_args()

    folder = args.capture
    if folder is None:
        candidates = sorted(d for d in CAPTURES.iterdir()
                            if (d / "manifest.json").is_file())
        if not candidates:
            print("no loadout captures on disk", file=sys.stderr)
            return 2
        folder = candidates[0]

    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    info = manifest["tabs"].get(args.tab)
    if not info or not info["frames"]:
        print(f"{folder.name} has no {args.tab} frames", file=sys.stderr)
        return 2
    frames = info["frames"]
    name = frames[min(args.frame, len(frames) - 1)]
    image = cv2.imread(str(folder / name))
    if image is None:
        print(f"cannot read {name}", file=sys.stderr)
        return 2

    out_path = OUT / f"_calib_{args.tab}.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), overlay(image, args.tab))

    slots = L.icon_slots(args.tab)
    print(f"{folder.name} / {name}  ({image.shape[1]}x{image.shape[0]})")
    print(f"drew {out_path.relative_to(ROOT)}")
    print()
    print("green box = an icon the matcher will be given; blue = suspiciously")
    print("narrow, which is the fragment bug and means the crop is wrong.")
    print()
    if slots:
        print(f"{args.tab} slots are MEASURED, from coords/loadouts.json:")
        print(f"  centres {slots['centres']}  size {slots['size']}")
    else:
        print(f"{args.tab} slots are INFERRED. To measure them instead, put "
              f"this in coords/loadouts.json and adjust until the boxes sit "
              f"on the icons:")
        print(json.dumps({"icons": {args.tab: {
            "centres": [round((i + 0.5) / L.TABS[args.tab]["icons"], 3)
                        for i in range(L.TABS[args.tab]["icons"])],
            "size": round(1.0 / L.TABS[args.tab]["icons"], 3)}}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
