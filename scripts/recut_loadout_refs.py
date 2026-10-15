"""Re-cut the labelled reference tiles with the geometry that ships.

Run this after ANY change to the icon geometry in src/loadouts.py. A
reference and a live tile have to be cut by the same rule, and when
they are not the bank quietly loses whichever icons the drift hurt
most.

For almost every icon that is invisible -- the same art still correlates
at 0.99 either way. Font of Life is the exception, and it is instructive:
it is a near-uniform green glow with almost no internal structure, so the
content-box crop lands differently and the correlation falls to 0.524,
under the 0.55 assignment gate. Its 89 tiles were refused, the name never
entered the bank, and every Font of Life in the ladder would have read as
Triumph.

Lowering the gate would be treating the symptom and would let genuinely
unknown art in. The cause is that the reference and the live tile are cut
by two different rules, so the fix is to cut them by one.

Each labelled group recorded the frame, row and slot its representative
tile came from. Re-cutting from that exact source keeps the label on the
exact icon the owner looked at, and makes it pixel-consistent with what
the builder will meet.
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import icon_match as M  # noqa: E402
from src import loadouts as L  # noqa: E402

CAPTURES = ROOT / "data" / "captures_loadouts"
OUT = ROOT / "data" / "icon_bank" / "loadout_labelled.npz"
LABELS = ROOT / "data" / "loadout_icon_labels.json"


def recut(src: str):
    """The tile at a recorded 'session/frame rN sI', cut the shipping way."""
    where, row_s, slot_s = src.rsplit(" ", 2)
    session, frame = where.split("/")
    r = int(row_s[1:]) - 1
    s = int(slot_s[1:])
    path = CAPTURES / session / f"{frame}.png"
    image = cv2.imread(str(path))
    if image is None:
        return None
    tab = frame.split("_")[0]
    rows = L.find_rows(image)
    if r >= len(rows):
        return None
    geom = L.measure_icons(image, rows, L.TABS[tab]["icons"])
    if geom is None:
        return None
    tiles = geom.tiles(image, rows[r])
    return tiles[s] if s < len(tiles) else None


def main() -> int:
    doc = json.loads(LABELS.read_text(encoding="utf-8"))
    labels, source = doc["labels"], doc["_source"]

    with np.load(OUT) as z:
        old = {k: z[k] for k in z.files}

    out, kept_sheet, recut_n = {}, [], 0
    for kind in ("items", "runes"):
        for key in sorted(k for k in old if k.startswith(kind + "-")):
            tile = recut(source[key]) if key in source else None
            if tile is None or tile.size == 0:
                # The frame the sheet took it from is one the width guard
                # now refuses. Keep the sheet tile: a reference that is a
                # little off beats no reference at all.
                out[key] = old[key]
                kept_sheet.append(key)
            else:
                out[key] = tile
                recut_n += 1

    np.savez_compressed(OUT, **out)
    print(f"{recut_n} references re-cut, {len(kept_sheet)} kept from the sheet"
          + (f" ({', '.join(kept_sheet[:6])})" if kept_sheet else ""))

    # The point of the exercise: does every reference now agree with a live
    # cut of its own icon? Re-score each one against its own source tile.
    worst = []
    w_r = M._weights(True, True)
    w_i = M._weights(True, False)
    for kind in ("items", "runes"):
        w = w_r if kind == "runes" else w_i
        for key in sorted(k for k in out if k.startswith(kind + "-")):
            live = recut(source[key]) if key in source else None
            if live is None:
                continue
            s = M._score(M._norm_tile(live), w, M._norm_tile(out[key]))
            worst.append((s, key, labels.get(key, "?")))
    worst.sort()
    print("lowest self-agreement after the re-cut:")
    for s, key, name in worst[:6]:
        print(f"  {s:.4f}  {key:10s} {name}")
    print(f"  ... {sum(1 for s, _k, _n in worst if s < 0.55)} below the "
          f"0.55 assignment gate, out of {len(worst)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
