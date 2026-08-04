"""Read leaderboard rank badges by matching the game's own digit glyphs.

Why this exists. Tesseract reads this font's "3" as a "5" and its "2" as a
"4", because the glyphs differ only by whether the top stroke reads as
closed, and the scanner's illumination flattening biases the leading digit
into closing. A whole visible window shares one binarization, so it misreads
together and stays internally consecutive -- 51,52,53 is as plausible a
leaderboard window as 31,32,33 -- which is invisible to every consistency
check we can build downstream. One overnight run lost two champions to it and
churned three more.

Template matching sidesteps the entire failure. The problem was never really
recognition: it is one font, at one size, drawn at a fixed pitch, so a glyph
can be compared against the game's own pixels rather than interpreted. That
is deterministic, needs no subprocess (tesseract costs about a second per
scan, two to four scans per profile), and reports a real confidence -- so an
unclear glyph becomes an honest "unknown" instead of a confident wrong digit,
which is exactly what the old failure could not express.

Templates are built by scripts/build_digit_bank.py from captured leaderboard
frames, labelled by the manifest: every capture records the tap_y that opened
a given rank's profile, so the row at that y IS that rank, confirmed by the
player the tap produced. Numbering is frozen on disk -- a rebuild must not
silently re-map digits under a shipped bank.
"""
from __future__ import annotations

import functools
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
BANK = ROOT / "data" / "icon_bank" / "rank_digits.npz"

N = 28              # template resolution
GLYPH_H = 0.82      # glyph height as a fraction of the tile, before matching
MIN_SCORE = 0.60    # below this, no digit is credible
MIN_GAP = 0.05      # winner must beat the runner-up by this much

# A row crop is taken this far above/below the row centre, and this far into
# the badge column. Generous on purpose: segmentation finds the glyphs, the
# crop only has to contain them without reaching the neighbouring rows.
ROW_HALF_H = 45


def glyph_boxes(gray: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Bounding boxes (x0, y0, x1, y1) of the bright glyphs in a row crop,
    ordered left to right.

    The badge column is a dark panel with bright numerals, so a simple
    brightness cut separates them; the digits never touch (measured gap ~5px
    at a ~25px glyph width), so column runs are glyphs. Segmentation only has
    to find WHERE the glyphs are, which thickening does not move -- the
    matching itself then runs on greyscale, so the binarization that caused
    the original bug cannot influence the answer.
    """
    if gray.size == 0:
        return []
    thresh = gray.mean() + 2.0 * gray.std()
    mask = gray > thresh
    cols = mask.sum(axis=0)
    runs: list[list[int]] = []
    for x, c in enumerate(cols):
        if c > 2:
            if runs and x - runs[-1][1] <= 3:
                runs[-1][1] = x
            else:
                runs.append([x, x])
    boxes: list[tuple[int, int, int, int]] = []
    for x0, x1 in runs:
        w = x1 - x0 + 1
        if not (8 <= w <= 45):
            continue
        rows = np.where(mask[:, x0:x1 + 1].sum(axis=1) > 0)[0]
        if rows.size == 0:
            continue
        y0, y1 = int(rows[0]), int(rows[-1])
        h = y1 - y0 + 1
        if not (18 <= h <= 70):
            continue
        if w > 1.4 * h:          # wider than tall is not a digit
            continue
        boxes.append((x0, y0, x1 + 1, y1 + 1))
    return boxes


def normalise(patch: np.ndarray) -> np.ndarray | None:
    """A glyph patch as a fixed-size, zero-mean, unit-norm tile.

    Scaled by HEIGHT, not fitted to the box: every digit in this font is the
    same height, so height is the reliable common scale and the widths stay
    meaningful afterwards -- which is most of what separates a "1" from a "0".
    """
    if patch.size == 0 or patch.shape[0] < 4:
        return None
    scale = (N * GLYPH_H) / patch.shape[0]
    w = max(1, int(round(patch.shape[1] * scale)))
    h = max(1, int(round(patch.shape[0] * scale)))
    if w > N:
        return None
    small = cv2.resize(patch.astype(np.float32), (w, h), interpolation=cv2.INTER_AREA)
    tile = np.full((N, N), float(np.median(patch)), dtype=np.float32)
    y0 = (N - h) // 2
    x0 = (N - w) // 2
    tile[y0:y0 + h, x0:x0 + w] = small
    tile -= tile.mean()
    norm = float(np.linalg.norm(tile))
    if norm < 1e-6:
        return None
    return tile / norm


@functools.lru_cache(maxsize=1)
def templates() -> dict[int, np.ndarray]:
    """digit -> normalised template. Empty when no bank has been built."""
    if not BANK.exists():
        return {}
    data = np.load(BANK)
    return {int(k): data[k] for k in data.files}


def read_digit(tile: np.ndarray) -> tuple[int | None, float]:
    """Best digit for one normalised tile, plus its margin over the runner-up.

    The margin is the confidence that matters. A high score against the best
    template means little if the second-best scores just as well; refusing
    there is the whole point of doing this by templates.
    """
    bank = templates()
    if not bank:
        return None, 0.0
    scored = sorted(
        ((float((tile * t).sum()), d) for d, t in bank.items()), reverse=True)
    (best, digit), (second, _) = scored[0], scored[1]
    if best < MIN_SCORE or best - second < MIN_GAP:
        return None, best - second
    return digit, best - second


def _bright_mask(gray: np.ndarray) -> np.ndarray:
    """Where the numerals are, robust to the panel's luminance gradient.

    That gradient is the root of the original bug: a global threshold
    binarizes lower rows thicker and closes a 3 into a 5. Here it only has to
    find glyph POSITIONS, and the matching then runs on the raw greyscale --
    so flattening can move a boundary by a pixel but can no longer change
    which digit comes out.
    """
    g = gray.astype(np.float32)
    bg = cv2.GaussianBlur(g, (0, 0), sigmaX=25)
    flat = np.clip((g / np.maximum(bg, 1.0)) * 128.0, 0, 255)
    return flat > (flat.mean() + 2.0 * flat.std())


def read_column(
    image: np.ndarray,
    badge_x: tuple[int, int],
    y_range: tuple[int, int] | None = None,
) -> dict[int, int]:
    """Every rank badge visible in the column: {rank: row_centre_y}.

    Finds rows from the glyphs themselves rather than from a prior scan, so
    nothing here depends on tesseract. Rows that cannot be read with margin
    are simply absent; the caller's grid inference fills them from position,
    which is the behaviour we want for the clipped top and bottom rows.
    """
    if not templates():
        return {}
    x0, x1 = badge_x
    y0, y1 = y_range if y_range is not None else (0, image.shape[0])
    crop = image[y0:y1, x0:x1]
    if crop.size == 0:
        return {}
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    mask = _bright_mask(gray).astype(np.uint8)
    count, _lbl, stats, cents = cv2.connectedComponentsWithStats(mask, connectivity=8)
    glyphs: list[tuple[float, int, int, int, int, int]] = []  # (cy, cx, x, y, w, h)
    for i in range(1, count):
        gx, gy, gw, gh, area = (int(stats[i, cv2.CC_STAT_LEFT]), int(stats[i, cv2.CC_STAT_TOP]),
                                int(stats[i, cv2.CC_STAT_WIDTH]), int(stats[i, cv2.CC_STAT_HEIGHT]),
                                int(stats[i, cv2.CC_STAT_AREA]))
        if not (8 <= gw <= 45 and 18 <= gh <= 70):
            continue
        if gw > 1.4 * gh or area < 0.15 * gw * gh:
            continue
        glyphs.append((float(cents[i][1]), int(cents[i][0]), gx, gy, gw, gh))
    if not glyphs:
        return {}

    rows: list[list[tuple[float, int, int, int, int, int]]] = []
    for g in sorted(glyphs):
        if rows and abs(g[0] - rows[-1][0][0]) < 25:
            rows[-1].append(g)
        else:
            rows.append([g])

    out: dict[int, int] = {}
    for row in rows:
        if len(row) > 3:
            continue
        value = 0
        good = True
        for _cy, _cx, gx, gy, gw, gh in sorted(row, key=lambda g: g[1]):
            tile = normalise(gray[gy:gy + gh, gx:gx + gw])
            if tile is None:
                good = False
                break
            digit, _margin = read_digit(tile)
            if digit is None:
                good = False
                break
            value = value * 10 + digit
        # Ranks 1-3 wear ornate trophy banners that seat the numeral ~20px
        # above the row centre, so their glyph centroid is not a safe tap
        # target. The bank was built without them and the scanner already
        # extrapolates them from the grid, which puts them on the real row.
        if good and value >= 4:
            cy = int(round(y0 + sum(g[0] for g in row) / len(row)))
            out.setdefault(value, cy)
    return out


def read_row(image: np.ndarray, y: int, badge_x: tuple[int, int]) -> tuple[int | None, float]:
    """The rank drawn on the row centred at `y`, or None when unreadable.

    Returns (rank, confidence). Any glyph the bank cannot place with margin
    fails the whole row: a rank read as "3" because its tens digit was
    dropped is worse than no read at all, and the caller has grid inference
    for rows that decline to answer.
    """
    h = image.shape[0]
    y0, y1 = max(0, y - ROW_HALF_H), min(h, y + ROW_HALF_H)
    crop = image[y0:y1, badge_x[0]:badge_x[1]]
    if crop.size == 0:
        return None, 0.0
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    boxes = glyph_boxes(gray)
    if not boxes or len(boxes) > 3:
        return None, 0.0
    value = 0
    worst = 1.0
    for bx0, by0, bx1, by1 in boxes:
        tile = normalise(gray[by0:by1, bx0:bx1])
        if tile is None:
            return None, 0.0
        digit, margin = read_digit(tile)
        if digit is None:
            return None, margin
        value = value * 10 + digit
        worst = min(worst, margin)
    return (value or None), worst
