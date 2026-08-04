"""Build the rank-digit template bank from captured leaderboard frames.

The labels come from the captures themselves, not from OCR -- which matters,
because OCR is the thing being replaced and training on its output would bake
the "3 reads as 5" error straight into the templates.

Every capture session writes, per rank, the leaderboard frame and the tap_y
that opened that rank's profile. The tap produced a profile whose player the
extraction then read, so the row at tap_y IS that rank. Rows sit on a fixed
pitch, so the neighbours are that rank minus/plus one, and they are harvested
too (bounded, and only when their glyphs fall wholly inside the frame).

    python -m scripts.build_digit_bank                 # build from captures
    python -m scripts.build_digit_bank --sessions 12   # sample fewer
    python -m scripts.build_digit_bank --sheet         # contact sheet only

Numbering is frozen by construction here (a template is stored under the
digit it depicts), so a rebuild cannot silently re-map digits the way the
first rune-cluster pass did.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

from src.config import SCREEN_2_BADGE_X_RANGE, load_calibration
from src.rank_digits import BANK, N, ROW_HALF_H, glyph_boxes, normalise

ROOT = Path(__file__).resolve().parent.parent
CAPTURES = ROOT / "data" / "captures"
PITCH = 146.7          # device row pitch, measured
NEIGHBOURS = (-2, -1, 0, 1, 2)


def harvest(sessions: list[Path], badge_x: tuple[int, int]) -> dict[int, list[np.ndarray]]:
    """digit -> list of normalised tiles, labelled from the manifests."""
    tiles: dict[int, list[np.ndarray]] = defaultdict(list)
    for s in sessions:
        manifest = s / "manifest.jsonl"
        if not manifest.exists():
            continue
        for line in manifest.open(encoding="utf-8"):
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            frame = s / (e.get("lb_frame") or "")
            rank, tap_y = e.get("rank"), e.get("tap_y")
            if not frame.exists() or rank is None or tap_y is None:
                continue
            img = cv2.imread(str(frame))
            if img is None:
                continue
            gray_full = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            for step in NEIGHBOURS:
                r = rank + step
                # Ranks 1-3 wear ornate trophy banners rather than plain
                # numerals; they are grid-extrapolated by the scanner and
                # must not pollute the digit templates.
                if r < 4:
                    continue
                y = int(round(tap_y + step * PITCH))
                y0, y1 = y - ROW_HALF_H, y + ROW_HALF_H
                if y0 < 0 or y1 > img.shape[0]:
                    continue
                crop = gray_full[y0:y1, badge_x[0]:badge_x[1]]
                boxes = glyph_boxes(crop)
                if len(boxes) != len(str(r)):
                    continue     # segmentation disagrees with the label: skip
                for (bx0, by0, bx1, by1), ch in zip(boxes, str(r)):
                    tile = normalise(crop[by0:by1, bx0:bx1])
                    if tile is not None:
                        tiles[int(ch)].append(tile)
    return tiles


def consolidate(tiles: list[np.ndarray]) -> np.ndarray:
    """One template from many tiles: average, then re-average over the half
    that agrees best with it. Captures are JPEG and a few labels will be
    wrong (a mistapped row), so a plain mean smears; trimming to the
    consistent half removes the outliers without hand-picking."""
    stack = np.stack(tiles)
    mean = stack.mean(axis=0)
    mean /= max(float(np.linalg.norm(mean)), 1e-6)
    scores = (stack.reshape(len(stack), -1) @ mean.reshape(-1))
    keep = stack[scores >= np.median(scores)]
    out = keep.mean(axis=0)
    return out / max(float(np.linalg.norm(out)), 1e-6)


def contact_sheet(bank: dict[int, np.ndarray], path: Path) -> None:
    """Every template, in digit order, upscaled to be read at a glance. The
    one manual check worth doing: the glyph under each label must be that
    digit."""
    cells = []
    for d in range(10):
        t = bank.get(d)
        img = np.zeros((N, N), np.float32) if t is None else t.copy()
        img = (img - img.min()) / max(img.ptp(), 1e-6)
        cell = cv2.resize((img * 255).astype(np.uint8), (N * 4, N * 4),
                          interpolation=cv2.INTER_NEAREST)
        cell = cv2.cvtColor(cell, cv2.COLOR_GRAY2BGR)
        cv2.putText(cell, str(d), (4, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (0, 220, 255), 2)
        cells.append(cell)
    cv2.imwrite(str(path), np.hstack(cells))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sessions", type=int, default=14,
                    help="how many capture sessions to sample (0 = all)")
    ap.add_argument("--sheet", action="store_true",
                    help="only write the contact sheet for an existing bank")
    args = ap.parse_args()

    sheet = ROOT / "data" / "icon_bank" / "rank_digits_sheet.png"
    if args.sheet:
        from src.rank_digits import templates
        contact_sheet(templates(), sheet)
        print(f"contact sheet -> {sheet}")
        return

    # The DEVICE's column, not the config default: the constant in config is
    # the emulator's geometry (575-695) while this phone's badges sit at
    # 985-1155. Building against the constant harvests the player avatars,
    # which look convincingly like templates right up until nothing matches.
    cal = load_calibration()
    badge_x = (int(cal.get("badge_x0", SCREEN_2_BADGE_X_RANGE[0])),
               int(cal.get("badge_x1", SCREEN_2_BADGE_X_RANGE[1])))
    print(f"badge column: x={badge_x}")

    sessions = sorted(p for p in CAPTURES.iterdir() if p.is_dir())
    if args.sessions and len(sessions) > args.sessions:
        random.seed(7)
        sessions = random.sample(sessions, args.sessions)
    print(f"harvesting from {len(sessions)} capture session(s)")

    tiles = harvest(sessions, badge_x)
    if not tiles:
        raise SystemExit("no tiles harvested -- are there captures on disk?")
    missing = [d for d in range(10) if len(tiles.get(d, [])) < 20]
    for d in range(10):
        print(f"  digit {d}: {len(tiles.get(d, [])):>5} tiles")
    if missing:
        raise SystemExit(
            f"too few examples of {missing} -- sample more sessions before "
            f"freezing a bank that cannot read them")

    bank = {d: consolidate(tiles[d]) for d in range(10)}
    BANK.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(BANK, **{str(d): t for d, t in bank.items()})
    contact_sheet(bank, sheet)
    print(f"\nbank  -> {BANK}")
    print(f"sheet -> {sheet}   (check every glyph matches its label)")


if __name__ == "__main__":
    main()
