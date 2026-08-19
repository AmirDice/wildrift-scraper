"""Read the profile STATS page and the rank popup with OCR instead of a model.

The stats page is the last thing in the pipeline that needed paying for. Items,
runes and spells already come from icon matching, names and win-rate strips are
OCR-first with a model fallback -- but every stats page was a model call, and
there are two per player.

It is a good OCR target. The layout is a fixed grid of large, high-contrast
numerals: a two-column counter panel on the left, six label/value rows on the
right, and the queue in a dropdown at the top. Nothing here is prose.

Regions are FRACTIONS of the frame, not pixels, so a different device
resolution scales instead of breaking. They were calibrated against a
2340x1080 capture; `--debug` prints every crop's raw read so a shifted layout
can be re-fitted quickly.

Every field returns None when unreadable rather than a guess, so the caller can
decide whether the frame is worth a model call. That decision belongs to the
caller, not here.
"""
from __future__ import annotations

import re

import cv2
import numpy as np

from .ocr import _configure_tesseract, preprocess

import pytesseract

# ---- region table (x0, y0, x1, y1) as fractions of width/height -------------
# Right panel: six rows, label on the left and a right-aligned value. Only the
# value is cropped; the labels are known from the row order.
_RIGHT_ROWS = ("kda", "teamfight_participation", "gold_per_minute",
               "damage_dealt_per_match", "damage_taken_per_match",
               "turret_damage_per_match")
_RIGHT_X = (0.755, 0.855)
_RIGHT_Y0 = 0.198
_RIGHT_STEP = 0.1127
_RIGHT_H = 0.050

# Left panel: Games and Win Rate share a row, then a 2x4 grid of counters.
_LEFT_PAIRS = (("mvp", "s_rating"), ("a_rating", "legendary"),
               ("pentakill", "quadra_kill"), ("triple_kill", "first_blood"))
_LEFT_COL_A = (0.120, 0.195)
_LEFT_COL_B = (0.270, 0.345)
_LEFT_Y0 = 0.386
_LEFT_STEP = 0.1140
_LEFT_H = 0.050

_GAMES_BOX = (0.122, 0.298, 0.185, 0.350)
_WINRATE_BOX = (0.275, 0.298, 0.355, 0.350)
_NAME_BOX = (0.122, 0.148, 0.215, 0.208)
_QUEUE_BOX = (0.685, 0.018, 0.755, 0.068)

_DIGITS = "--psm 7 -c tessedit_char_whitelist=0123456789.,%"
_WORDS = "--psm 7"


def _crop(img: np.ndarray, box: tuple[float, float, float, float]) -> np.ndarray:
    h, w = img.shape[:2]
    x0, y0, x1, y1 = box
    return img[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]


#: (scale, psm) variants to read each crop with, then vote.
#:
#: Chosen by measurement, not habit. Over-upscaling DEGRADES this font: at
#: scale 4 a bold "55" reads "35" and "5.1" reads "9.1", while 1.5 to 2.5 read
#: both correctly. psm 13 returns empty or wrong on these crops ("816" for
#: "31,416"). So every variant here is a low scale with psm 7 or 6, which
#: agreed on every field of the calibration frame -- the vote guards against a
#: single variant slipping on a frame we have not seen, rather than papering
#: over settings known to be bad.
_VARIANTS = ((2.0, 7), (2.0, 6), (2.5, 7), (1.5, 6))


_GAP = 24          # blank rows between stacked crops, so words never merge


def _read_batch(img: np.ndarray, boxes: dict, config: str,
                scale: float = 2.0, psm: int = 6) -> dict:
    """Read MANY crops in ONE tesseract call.

    Tesseract costs ~0.33s per invocation almost entirely in process startup,
    so 18 fields x 4 variants was 24 seconds a page -- 60+ hours across a
    hundred champions. The crops are stacked into one tall image with blank
    gaps, read once, and each detected word is assigned back to whichever band
    its centre falls in. Mapping by geometry rather than by line order means an
    unreadable crop leaves a hole instead of shifting every field after it.
    """
    _configure_tesseract()
    bands: list[tuple[str, int, int]] = []
    tiles: list[np.ndarray] = []
    y = 0
    for field, box in boxes.items():
        crop = _crop(img, box)
        if crop.size == 0:
            continue
        tile = preprocess(crop, scale=scale)
        tiles.append(tile)
        bands.append((field, y, y + tile.shape[0]))
        y += tile.shape[0] + _GAP
    if not tiles:
        return {}
    width = max(t.shape[1] for t in tiles)
    canvas = np.zeros((y, width), dtype=tiles[0].dtype)
    at = 0
    for tile in tiles:
        canvas[at:at + tile.shape[0], :tile.shape[1]] = tile
        at += tile.shape[0] + _GAP

    base = config.split(" -c ")[-1] if " -c " in config else ""
    cfg = f"--psm {psm}" + (f" -c {base}" if base else "")
    data = pytesseract.image_to_data(canvas, config=cfg,
                                     output_type=pytesseract.Output.DICT)
    found: dict[str, list[tuple[int, str]]] = {}
    for i, text in enumerate(data.get("text") or []):
        text = (text or "").strip()
        if not text:
            continue
        centre = data["top"][i] + data["height"][i] / 2
        for field, y0, y1 in bands:
            if y0 <= centre <= y1:
                found.setdefault(field, []).append((data["left"][i], text))
                break
    return {f: " ".join(t for _x, t in sorted(v)) for f, v in found.items()}


def _read(img: np.ndarray, box, config: str) -> str:
    """Read one crop, taking the majority answer across preprocessing variants.

    A single misread digit is silent and permanent in the data, so agreement
    between independent reads is worth the extra passes -- the crops are tiny
    and this is still hundreds of times cheaper than a model call.
    """
    crop = _crop(img, box)
    if crop.size == 0:
        return ""
    base = config.split(" -c ")[-1] if " -c " in config else ""
    votes: list[str] = []
    for scale, psm in _VARIANTS:
        cfg = f"--psm {psm}" + (f" -c {base}" if base else "")
        try:
            text = pytesseract.image_to_string(preprocess(crop, scale=scale), config=cfg)
        except Exception:  # noqa: BLE001 -- a bad variant must not kill the field
            continue
        text = " ".join(text.split())
        if text:
            votes.append(text)
    if not votes:
        return ""
    best = max(sorted(set(votes), key=votes.index), key=votes.count)
    return best


def _num(text: str, allow_float: bool = True) -> float | int | None:
    """The number in an OCR read, commas stripped, percent sign dropped."""
    cleaned = (text or "").replace(",", "").replace("%", "").strip()
    m = re.search(r"\d+(?:\.\d+)?", cleaned)
    if not m:
        return None
    value = m.group(0)
    if "." in value:
        return float(value) if allow_float else int(float(value))
    return int(value)


def read_stats_page_ocr(image: np.ndarray, debug: bool = False) -> dict:
    """Same field set as gemini_ocr.read_stats_page, read with OCR.

    Unreadable fields come back None so the caller can weigh a model call.
    """
    _configure_tesseract()
    FLOATS = {"win_rate", "kda", "teamfight_participation"}

    numeric: dict[str, tuple] = {"games": _GAMES_BOX, "win_rate": _WINRATE_BOX}
    for i, (left, right) in enumerate(_LEFT_PAIRS):
        y0 = _LEFT_Y0 + i * _LEFT_STEP
        numeric[left] = (_LEFT_COL_A[0], y0, _LEFT_COL_A[1], y0 + _LEFT_H)
        numeric[right] = (_LEFT_COL_B[0], y0, _LEFT_COL_B[1], y0 + _LEFT_H)
    for i, field in enumerate(_RIGHT_ROWS):
        y0 = _RIGHT_Y0 + i * _RIGHT_STEP
        numeric[field] = (_RIGHT_X[0], y0, _RIGHT_X[1], y0 + _RIGHT_H)

    raw = _read_batch(image, numeric, _DIGITS)
    out: dict = {f: _num(raw.get(f, ""), allow_float=f in FLOATS) for f in numeric}

    # Second pass, one more call, only for whatever the first pass missed --
    # a different scale reads crops the first settings choked on.
    missing = {f: box for f, box in numeric.items() if out.get(f) is None}
    if missing:
        retry = _read_batch(image, missing, _DIGITS, scale=1.5, psm=6)
        for field, text in retry.items():
            value = _num(text, allow_float=field in FLOATS)
            if value is not None:
                out[field] = value
                raw[field] = text

    words = _read_batch(image, {"player_name": _NAME_BOX, "queue": _QUEUE_BOX},
                        _WORDS, psm=6)
    for field in ("player_name", "queue"):
        text = (words.get(field) or "").strip(" |-_‘’—")
        out[field] = text or None
        raw[field] = words.get(field, "")

    out["tier"] = None          # unused downstream; kept for shape parity
    if debug:
        for key in list(numeric) + ["player_name", "queue"]:
            print(f"    {key:<28} raw={raw.get(key, '')!r:<18} -> {out.get(key)!r}")
    return out


def stats_confidence(stats: dict) -> float:
    """Share of the fields that actually read, so a caller can set a threshold.

    player_name and tier are excluded: the name is already resolved elsewhere
    and tier is unused downstream, so neither should drag a numeric page's
    score down.
    """
    fields = [f for f in stats if f not in ("player_name", "tier", "queue")]
    if not fields:
        return 0.0
    got = sum(1 for f in fields if stats.get(f) is not None)
    return got / len(fields)
