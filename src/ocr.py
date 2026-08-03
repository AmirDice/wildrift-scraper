"""OCR helpers for reading text (and winrates specifically) from screenshots.

Strategy
--------
Tesseract is sensitive to text size, contrast, and noise. Wild Rift's
leaderboard text is small and rendered over textured/blurred backgrounds, so
we preprocess each crop before handing it to Tesseract:

    1. convert to grayscale
    2. upscale (Tesseract prefers x-heights >= 20 px)
    3. binarize via Otsu — try both polarities and keep the one that produces
       more confident output
    4. run Tesseract with a single-line PSM and a tight character whitelist

`read_winrate()` is the convenience wrapper used by the scraper: it returns a
float in [0, 100] or None if nothing parseable was found.

Run as a CLI to tune against a saved screenshot:

    python -m src.ocr data/leaderboard_ahri.png --crop 980,310,140,40
    python -m src.ocr data/leaderboard_ahri.png --crop 980,310,140,40 --debug
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pytesseract


# Tesseract binary discovery on Windows: pytesseract defaults to PATH, but the
# winget install lands at "C:\Program Files\Tesseract-OCR\tesseract.exe" and
# is not always added to PATH. We probe a few common locations.
def _configure_tesseract() -> None:
    env_path = os.environ.get("TESSERACT_CMD")
    if env_path and Path(env_path).exists():
        pytesseract.pytesseract.tesseract_cmd = env_path
        return
    if shutil.which("tesseract"):
        return  # already on PATH
    for candidate in (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ):
        if Path(candidate).exists():
            pytesseract.pytesseract.tesseract_cmd = candidate
            return
    # Leave default; pytesseract will raise a clear error on first call.


_configure_tesseract()


# A whitelist scoped to numbers + dot + percent gives Tesseract a strong prior
# for winrate-style text like "53.7%" or "100%".
WINRATE_TESSERACT_CONFIG = (
    "--oem 3 --psm 7 "
    "-c tessedit_char_whitelist=0123456789.% "
)

# General-purpose config for reading mixed text in a region (champion names,
# labels, numbers). PSM 6 = "uniform block of text". No whitelist.
GENERAL_TESSERACT_CONFIG = "--oem 3 --psm 6"

WINRATE_PATTERN = re.compile(r"(\d{1,3})(?:[.,](\d{1,2}))?\s*%?")
# Matches "57.8%" or "100%" anywhere in OCR output, with optional spaces.
PERCENT_PATTERN = re.compile(r"(\d{1,3}(?:[.,]\d{1,2})?)\s*%")


@dataclass
class OCRResult:
    text: str
    confidence: float  # mean Tesseract confidence in [0, 100], or -1 if unknown
    image: np.ndarray  # the preprocessed image actually fed to Tesseract


@dataclass
class OCRWord:
    text: str
    x: int       # center x in preprocessed-image coords
    y: int       # center y in preprocessed-image coords
    w: int
    h: int
    confidence: float


def preprocess(img: np.ndarray, scale: float = 3.0, invert: bool = False) -> np.ndarray:
    """Grayscale + upscale + Otsu threshold. Returns a uint8 binary image."""
    if img.ndim == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img
    if scale != 1.0:
        gray = cv2.resize(
            gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
        )
    # Light denoise before threshold helps on textured backgrounds.
    gray = cv2.bilateralFilter(gray, d=5, sigmaColor=50, sigmaSpace=50)
    flag = cv2.THRESH_BINARY_INV if invert else cv2.THRESH_BINARY
    _, binary = cv2.threshold(gray, 0, 255, flag | cv2.THRESH_OTSU)
    return binary


def _run_tesseract(img: np.ndarray, config: str) -> tuple[str, float]:
    """Return (joined_text, mean_confidence). Confidence is -1 if Tesseract
    returned no per-word data."""
    data = pytesseract.image_to_data(
        img, config=config, output_type=pytesseract.Output.DICT
    )
    words: list[str] = []
    confs: list[float] = []
    for text, conf in zip(data.get("text", []), data.get("conf", [])):
        if not text or not text.strip():
            continue
        words.append(text.strip())
        try:
            c = float(conf)
        except (TypeError, ValueError):
            c = -1.0
        if c >= 0:
            confs.append(c)
    return " ".join(words), (sum(confs) / len(confs) if confs else -1.0)


def read_text(img: np.ndarray, config: str = WINRATE_TESSERACT_CONFIG) -> OCRResult:
    """Try both polarities of Otsu threshold; return the higher-confidence
    result. Falls back to the non-inverted version if confidences are equal
    (or both missing)."""
    best: OCRResult | None = None
    for invert in (False, True):
        pre = preprocess(img, invert=invert)
        text, conf = _run_tesseract(pre, config)
        candidate = OCRResult(text=text, confidence=conf, image=pre)
        if best is None or candidate.confidence > best.confidence:
            best = candidate
    assert best is not None
    return best


def parse_winrate(text: str) -> float | None:
    """Extract a percentage from raw OCR text. Returns float in [0, 100] or None."""
    if not text:
        return None
    cleaned = text.replace(" ", "").replace(",", ".")
    match = WINRATE_PATTERN.search(cleaned)
    if not match:
        return None
    whole = int(match.group(1))
    frac = match.group(2)
    value = float(f"{whole}.{frac}") if frac else float(whole)
    if value < 0 or value > 100:
        return None
    return value


def read_winrate(img: np.ndarray) -> tuple[float | None, OCRResult]:
    """Convenience: OCR + parse. Returns (winrate, raw_result)."""
    result = read_text(img, WINRATE_TESSERACT_CONFIG)
    return parse_winrate(result.text), result


# Pattern for the mastery SCORE on screen 5 — either a comma-grouped integer
# like "19,076" or a 3+ digit run like "638". 1-2 digit numbers are excluded
# as noise (score values are always big).
_SCORE_PATTERN = re.compile(r"^(\d{1,3}(?:,\d{3})+|\d{3,})$")

# Pattern for the GAMES count — any 1-5 digit integer or comma-grouped one.
# On the RECENT tab games counts are often single/double digits (the player
# played 12 games this period), so this is intentionally looser than
# _SCORE_PATTERN. The 5-digit cap avoids grabbing chunks of the score.
_GAMES_PATTERN = re.compile(r"^(\d{1,3}(?:,\d{3})?|\d{1,5})$")


def find_target_data(
    image: np.ndarray,
    region: tuple[int, int, int, int],
    target: str,
    tile_half_width_px: int | None = None,
) -> tuple[float | None, int | None, int | None]:
    """OCR screen 5's champion-tile strip and return (winrate, score, games)
    for the `target` champion's tile, and ONLY that tile. The returned score
    and games belong to `target`, never to a neighboring tile.

    Within a tile the vertical order is (CHAMPION AND LANE tab):
        NAME -> "Highest Achieved" -> <score> -> "Games" -> <games> -> "Win Rate" -> <pct>

    On the RECENT tab the label changes to "Season highest" (and a few text
    positions shift because of character count) but the vertical ordering is
    still score-above-games-above-winrate, so the anchoring logic is the same.

    Strategy: anchor on the target champion-name word's position, then take
    only integers that are (a) below that y-position and (b) within
    tile_half_width_px of its x-position. The first such integer (smallest y)
    is the mastery score, the second is the games count.

    `tile_half_width_px` is in *preprocessed* (upscaled, scale=3.0)
    coordinates. When None (default), it is auto-derived from the OCR region
    width assuming 4 visible tiles: a tile is region_w/4 in original / ~3x
    upscaled, and we use ~80% of half-tile to stay comfortably inside our
    tile while excluding neighbors. Concrete defaults:
        emulator (region_w=909):  ~273   (was hardcoded 180)
        phone CHAMPION_LANE (1367): ~410
        phone RECENT (1561):       ~468
    """
    from . import champions as champ_module

    x, y, w, h = region
    crop = image[y:y + h, x:x + w]
    if crop.size == 0:
        return (None, None, None)

    # Auto-derive tile-half-width if caller didn't specify one. Formula:
    #     tile_w_original  = region_w / 4   (4 visible tiles)
    #     half_tile_upscaled = tile_w_original * scale / 2  (scale = 3.0)
    #     allowance        = 80% of half-tile, then capped at the tile center
    # The result scales correctly with whichever phone/emulator layout we hit.
    if tile_half_width_px is None:
        tile_half_width_px = int((w / 4) * 3.0 * 0.5 * 0.8)

    words = read_words(crop, GENERAL_TESSERACT_CONFIG)
    if not words:
        return (None, None, None)

    target_lower = target.lower()
    max_word_count = champ_module.MAX_WORD_COUNT

    # Find the target champion's name position (could be multi-word like
    # "Master Yi"). Pick the FIRST occurrence reading left-to-right.
    name_x: int | None = None
    name_y: int | None = None
    i = 0
    while i < len(words) and name_x is None:
        matched = False
        for span in range(min(max_word_count, len(words) - i), 0, -1):
            tokens = [words[i + k].text for k in range(span)]
            canonical = champ_module.match(tokens)
            if canonical is not None and canonical.lower() == target_lower:
                xs = [words[i + k].x for k in range(span)]
                ys = [words[i + k].y for k in range(span)]
                name_x = sum(xs) // span
                name_y = sum(ys) // span
                matched = True
                break
            elif canonical is not None:
                i += span
                matched = True
                break
        if not matched:
            i += 1

    if name_x is None or name_y is None:
        return (None, None, None)

    # Winrate: closest percentage (any y) to name_x. Also remember the y
    # of the in-tile percent so we can clip the games search above it.
    winrate: float | None = None
    pct_y_in_tile: int | None = None
    best_pct_dist = float("inf")
    for word in words:
        m = PERCENT_PATTERN.fullmatch(word.text)
        if not m:
            continue
        try:
            value = float(m.group(1).replace(",", "."))
        except ValueError:
            continue
        if not (0 <= value <= 100):
            continue
        dist = abs(word.x - name_x)
        if dist < best_pct_dist:
            best_pct_dist = dist
            winrate = value
        # In-tile percent: any percent within tile_half_width of the name
        # x, below the name. Track the topmost such percent.
        if (
            word.y > name_y
            and abs(word.x - name_x) <= tile_half_width_px
            and (pct_y_in_tile is None or word.y < pct_y_in_tile)
        ):
            pct_y_in_tile = word.y

    # SCORE pass: tight pattern + high lower bound. Mastery scores are
    # always large numbers, so this comfortably excludes stray digits and
    # mis-OCR'd percents.
    score: int | None = None
    score_y: int | None = None
    score_candidates: list[tuple[int, int]] = []  # (y, value)
    for word in words:
        if not _SCORE_PATTERN.match(word.text):
            continue
        try:
            value = int(word.text.replace(",", ""))
        except ValueError:
            continue
        if not (500 <= value <= 10_000_000):
            continue
        if word.y <= name_y:
            continue
        if abs(word.x - name_x) > tile_half_width_px:
            continue
        score_candidates.append((word.y, value))
    score_candidates.sort()
    if score_candidates:
        score_y, score = score_candidates[0]

    # GAMES pass: looser pattern (1+ digit) bounded between the score's y
    # and the percent's y, so we don't grab the winrate digits if Tesseract
    # dropped the % sign. This fixes the RECENT-tab case where a player
    # has fewer than 100 games and the old single-pass logic excluded
    # them as "noise".
    games: int | None = None
    if score_y is not None:
        games_candidates: list[tuple[int, int]] = []
        for word in words:
            if not _GAMES_PATTERN.match(word.text):
                continue
            try:
                value = int(word.text.replace(",", ""))
            except ValueError:
                continue
            if not (1 <= value <= 100_000):
                continue
            if word.y <= score_y:
                continue
            if pct_y_in_tile is not None and word.y >= pct_y_in_tile:
                continue
            if abs(word.x - name_x) > tile_half_width_px:
                continue
            # Defence in depth: skip values that *look* like a winrate
            # whose '%' was dropped by OCR. Anything <= 100 sitting close
            # to the in-tile percent's y (when we couldn't find one) is
            # suspicious, but we can't tell reliably without an anchor;
            # the score_y / pct_y_in_tile sandwich is the real guard here.
            games_candidates.append((word.y, value))
        games_candidates.sort()
        if games_candidates:
            games = games_candidates[0][1]

    return (winrate, score, games)


def read_words(img: np.ndarray, config: str = GENERAL_TESSERACT_CONFIG) -> list[OCRWord]:
    """Run OCR and return per-word data with bounding boxes.

    Tries both threshold polarities (like read_text) and returns whichever set
    of words had higher mean confidence.
    """
    best: tuple[float, list[OCRWord]] | None = None
    for invert in (False, True):
        pre = preprocess(img, invert=invert)
        data = pytesseract.image_to_data(
            pre, config=config, output_type=pytesseract.Output.DICT
        )
        words: list[OCRWord] = []
        confs: list[float] = []
        n = len(data.get("text", []))
        for i in range(n):
            text = (data["text"][i] or "").strip()
            if not text:
                continue
            try:
                conf = float(data["conf"][i])
            except (TypeError, ValueError):
                conf = -1.0
            x, y = data["left"][i], data["top"][i]
            w, h = data["width"][i], data["height"][i]
            words.append(OCRWord(
                text=text,
                x=x + w // 2,
                y=y + h // 2,
                w=w,
                h=h,
                confidence=conf,
            ))
            if conf >= 0:
                confs.append(conf)
        mean = sum(confs) / len(confs) if confs else -1.0
        if best is None or mean > best[0]:
            best = (mean, words)
    assert best is not None
    return best[1]


_RANK_BADGE_CONFIGS = (
    "--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789",
    "--oem 3 --psm 8 -c tessedit_char_whitelist=0123456789",
    "--oem 3 --psm 10 -c tessedit_char_whitelist=0123456789",
    "--oem 3 --psm 13 -c tessedit_char_whitelist=0123456789",
)


def read_rank_badge(
    image: np.ndarray,
    slot_idx: int,
    rank_1_y: int,
    row_pitch: float,
    badge_x_range: tuple[int, int],
    band_half_height: int = 45,
) -> tuple[int, int, int] | None:
    """OCR the rank-number badge at the given slot.

    Returns (rank, y_top, y_bottom) of the detected digit in original image
    coordinates, or None if nothing parseable was found. y_top/y_bottom give
    the actual bounding box of the digit on screen — used by the scroll
    safety check to detect partial visibility.

    Tries multiple PSMs and both threshold polarities since banner styles
    vary by rank. Rank 1 has a stylized gold trophy that does not OCR.
    """
    cy = int(round(rank_1_y + slot_idx * row_pitch))
    x0, x1 = badge_x_range
    y_start = max(0, cy - band_half_height)
    crop = image[y_start: cy + band_half_height, x0:x1]
    if crop.size == 0:
        return None

    for invert in (False, True):
        pre = preprocess(crop, invert=invert)
        # preprocess() upscales the image; recover the y scale factor so we
        # can map detected bounding boxes back to original image coords.
        scale_y = pre.shape[0] / max(1, crop.shape[0])
        for cfg in _RANK_BADGE_CONFIGS:
            data = pytesseract.image_to_data(
                pre, config=cfg, output_type=pytesseract.Output.DICT
            )
            n = len(data.get("text", []))
            for i in range(n):
                text = (data["text"][i] or "").strip()
                if not text or not text.isdigit():
                    continue
                try:
                    rank = int(text)
                except ValueError:
                    continue
                y_top_us = data["top"][i]
                y_bot_us = y_top_us + data["height"][i]
                y_top = y_start + int(round(y_top_us / scale_y))
                y_bot = y_start + int(round(y_bot_us / scale_y))
                return (rank, y_top, y_bot)
    return None


def read_all_visible_ranks(
    image: np.ndarray,
    rank_1_y: int,
    row_pitch: float,
    badge_x_range: tuple[int, int],
    num_slots: int = 5,
) -> dict[int, tuple[int, int, int]]:
    """Return {slot_idx: (rank, y_top, y_bottom)} for every slot whose badge
    OCR'd successfully. y values are in original image coordinates."""
    out: dict[int, tuple[int, int, int]] = {}
    for slot in range(num_slots):
        r = read_rank_badge(image, slot, rank_1_y, row_pitch, badge_x_range)
        if r is not None:
            out[slot] = r
    return out


def scan_visible_ranks(
    image: np.ndarray,
    badge_x_range: tuple[int, int],
    y_range: tuple[int, int] | None = None,
    max_rank: int = 250,
    hint: float | None = None,
    expected_pitch: float | None = None,
) -> tuple[dict[int, int], float | None]:
    """Locate every rank badge visible in the leaderboard's badge column.

    One screenshot, one OCR pass over the badge-column strip: returns
    ({rank: row_center_y_in_original_coords}, measured_row_pitch_px).
    Pitch is None when fewer than two consecutive ranks were read.

    This is what makes tap-by-detection work: instead of assuming rows sit at
    calibrated positions, we read where they actually are after any scroll and
    tap those coordinates. Rank 1's stylized trophy badge does not OCR — when
    rank 2 and a pitch are known, rank 1 is extrapolated one pitch above.

    Robustness: OCR misreads are filtered by keeping the longest chain of
    top-to-bottom ranks that increase by exactly +1 (leaderboard rows are
    always consecutive). A lone garbage token cannot survive that filter.
    """
    x0, x1 = badge_x_range
    h = image.shape[0]
    y0, y1 = y_range if y_range is not None else (0, h)
    crop = image[y0:y1, x0:x1]
    if crop.size == 0:
        return {}, None

    scale = 3.0
    candidates: list[tuple[int, int]] = []  # (y_orig_center, ocr_rank)
    seen_y: set[int] = set()

    def _collect(pre: np.ndarray) -> None:
        data = pytesseract.image_to_data(
            pre,
            config="--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789",
            output_type=pytesseract.Output.DICT,
        )
        n = len(data.get("text", []))
        for i in range(n):
            text = (data["text"][i] or "").strip()
            if not text.isdigit():
                continue
            rank = int(text)
            if not (1 <= rank <= max_rank):
                continue
            cy_pre = data["top"][i] + data["height"][i] // 2
            cy = y0 + int(round(cy_pre / scale))
            # Merge duplicate detections of the same badge across passes.
            if any(abs(cy - s) < 12 for s in seen_y):
                continue
            seen_y.add(cy)
            candidates.append((cy, rank))

    # Illumination flattening before Otsu: the panel's vertical luminance
    # gradient made a GLOBAL threshold binarize lower rows thicker, which
    # deterministically closed the open top of "3" into "5" (and "2" into
    # "4") -- a real frame read rank 31 as 51 at 86 confidence, twice in a
    # row. Dividing out the low-frequency background removes the gradient;
    # the glyphs keep their local contrast.
    gray0 = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    g = gray0.astype(np.float32)
    bg = cv2.GaussianBlur(g, (0, 0), sigmaX=25)
    flat = np.clip((g / np.maximum(bg, 1.0)) * 128.0, 0, 255).astype(np.uint8)
    flat = cv2.resize(flat, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    flat = cv2.bilateralFilter(flat, d=5, sigmaColor=50, sigmaSpace=50)
    # PSM 6 is the only mode that reads these ornate banner badges (verified
    # against saved screenshots; sparse-text PSMs return nothing).
    for invert in (False, True):
        flag = cv2.THRESH_BINARY_INV if invert else cv2.THRESH_BINARY
        _, pre = cv2.threshold(flat, 0, 255, flag | cv2.THRESH_OTSU)
        _collect(pre)

    if len(candidates) < 4:
        # Ornate badge styles (the emulator's gold/silver/bronze banners)
        # lose contrast under flattening; the classic global-Otsu path reads
        # those. Only runs when the flattened pass came up short.
        for invert in (False, True):
            _collect(preprocess(crop, scale=scale, invert=invert))

    if len(candidates) < 4:
        # Last resort: adaptive thresholding, per-neighborhood and immune to
        # anything global illumination can do.
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        for thresh_type in (cv2.THRESH_BINARY, cv2.THRESH_BINARY_INV):
            pre = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, thresh_type, 61, 6)
            _collect(pre)

    if not candidates:
        return {}, None
    candidates.sort()

    # Anchor: runs of consecutive (+1) ranks going down the screen.
    # Leaderboard rows are always consecutive, so chains are built from
    # plausibly-correct badges -- but misreads can BE consecutive too: a real
    # frame read "29,30,51,52,53" ("31-33" misread as "51-53"), and pure
    # longest-chain picked the majority-wrong run, then grid-snapped the two
    # CORRECT reads to match it. The caller's predicted position (`hint`)
    # therefore outweighs one extra chain link: a chain near the prediction
    # beats a slightly longer chain claiming a physically impossible teleport.
    # Once the right chain anchors, grid-snap rewrites the misread badges by
    # position, so the same OCR output yields a fully correct window.
    def chain_mean(ch: list[tuple[int, int]]) -> float:
        return sum(r for _, r in ch) / len(ch)

    def chain_score(ch: list[tuple[int, int]]) -> float:
        score = float(len(ch))
        if hint is not None and abs(chain_mean(ch) - hint) <= 6:
            score += 2.5
        return score

    best_chain: list[tuple[int, int]] = []
    for start in range(len(candidates)):
        chain = [candidates[start]]
        for j in range(start + 1, len(candidates)):
            if candidates[j][1] == chain[-1][1] + 1:
                chain.append(candidates[j])
        if not best_chain or chain_score(chain) > chain_score(best_chain):
            best_chain = chain
        elif (
            chain_score(chain) == chain_score(best_chain) and hint is not None
            and abs(chain_mean(chain) - hint) < abs(chain_mean(best_chain) - hint)
        ):
            best_chain = chain
    if not best_chain:
        return {}, None

    ranks = {rank: y for y, rank in best_chain}
    pitch: float | None = None
    if len(best_chain) >= 2:
        (y_first, r_first), (y_last, r_last) = best_chain[0], best_chain[-1]
        pitch = (y_last - y_first) / (r_last - r_first)

    # Row pitch is a DEVICE CONSTANT (~0.135x screen height on every layout
    # measured). A chain whose pitch disagrees with the known value is built
    # from garbage tokens (avatar digits, name text), not badges -- and
    # top-fill would then inflate it into a convincing fake window ("ranks
    # 1-17"). Reject it outright.
    if (
        expected_pitch is not None and pitch is not None
        and abs(pitch - expected_pitch) / expected_pitch > 0.30
    ):
        return {}, None

    if pitch is not None and pitch > 0:
        # Grid-snap correction: rows are evenly spaced, so any detection whose
        # y sits on a grid slot IS that slot's rank, whatever digit OCR read.
        # (Observed: the bronze "3" banner misreads as "2"; its position still
        # identifies it unambiguously.)
        anchor_y, anchor_rank = best_chain[0]
        for cy, _ocr_rank in candidates:
            slots_away = (cy - anchor_y) / pitch
            slot = round(slots_away)
            if abs(slots_away - slot) > 0.35:
                continue  # not on the grid: genuine garbage, drop it
            inferred = anchor_rank + slot
            if inferred < 1 or inferred > max_rank or inferred in ranks:
                continue
            ranks[inferred] = cy
        # The TOP badges (gold/silver trophies, ranks 1-2) OCR worst, but
        # their rows sit on the same grid: fill every missing rank above the
        # topmost read badge, as long as its extrapolated y still lands
        # plausibly inside the list area -- a genuinely scrolled-off rank
        # would extrapolate above the list top and is never invented.
        min_y = y0 + 0.09 * (y1 - y0)
        r = min(ranks)
        y_up = float(ranks[r])
        while r > 1 and y_up - pitch >= min_y:
            r -= 1
            y_up -= pitch
            ranks.setdefault(r, int(round(y_up)))
    return ranks, pitch


def scan_champion_rows(
    image: np.ndarray,
    name_x_range: tuple[int, int],
    y_range: tuple[int, int] = (150, 1020),
) -> list[tuple[int, str | None]]:
    """Locate champion rows on the CHAMPION tab of the leaderboard.

    Unlike player rows there are no number badges -- rows are identified by
    the champion NAME text. Returns [(row_center_y, canonical_name_or_None)]
    top to bottom. Rows whose name failed OCR are still returned as grid
    slots (name None): rows sit on the same ~146px pitch as player rows, so
    a gap of ~2 pitches between named rows means one unread row between them.
    The caller confirms identity from the screen-2 champion label anyway.
    """
    from . import champions as champ_module

    x0, x1 = name_x_range
    y0, y1 = y_range
    crop = image[y0:y1, x0:x1]
    if crop.size == 0:
        return []
    scale = 3.0
    words = read_words(crop, GENERAL_TESSERACT_CONFIG)
    # group words into rows by (downscaled) y proximity
    groups: list[list[OCRWord]] = []
    for w in sorted(words, key=lambda w: w.y):
        if groups and abs(w.y - groups[-1][-1].y) < 60:  # preprocessed coords
            groups[-1].append(w)
        else:
            groups.append([w])
    named: list[tuple[int, str]] = []
    for g in groups:
        toks = [w.text for w in sorted(g, key=lambda w: w.x)]
        hit = None
        for span in range(min(champ_module.MAX_WORD_COUNT, len(toks)), 0, -1):
            for start in range(len(toks) - span + 1):
                hit = champ_module.match(toks[start:start + span])
                if hit:
                    break
            if hit:
                break
        if hit:
            cy = y0 + int(round(sum(w.y for w in g) / len(g) / scale))
            named.append((cy, hit))
    if not named:
        return []
    named.sort()
    # pitch from consecutive named rows (fallback to the device constant)
    diffs = [b[0] - a[0] for a, b in zip(named, named[1:]) if 100 <= b[0] - a[0] <= 200]
    pitch = (sum(diffs) / len(diffs)) if diffs else 146.0
    # grid-fill unread slots between and around the named rows
    slots: list[tuple[int, str | None]] = list(named)
    for (ya, _na), (yb, _nb) in zip(named, named[1:]):
        gap = round((yb - ya) / pitch)
        for k in range(1, gap):
            slots.append((int(round(ya + k * pitch)), None))
    # extend one slot above/below when there is room inside the list area
    top_y, bot_y = named[0][0], named[-1][0]
    if top_y - pitch > y0 + 40:
        slots.append((int(round(top_y - pitch)), None))
    if bot_y + pitch < y1 - 40:
        slots.append((int(round(bot_y + pitch)), None))
    slots.sort(key=lambda t: t[0])
    return slots


def locate_badge_column(
    image: np.ndarray,
    window_w: int = 170,
    step: int = 50,
) -> tuple[tuple[int, int] | None, dict[int, int], float | None]:
    """Find the rank-badge column automatically by sliding an OCR window
    across the left half of the screen and keeping whichever x-window yields
    the most rank badges. Returns (x_range, ranks, pitch) — x_range is None
    if nothing scanned like a leaderboard.

    Meant to run once per session (or when the configured range finds
    nothing), then be persisted via config.save_calibration, since it costs
    several OCR passes.
    """
    w = image.shape[1]
    best: tuple[int, tuple[int, int], dict[int, int], float | None] | None = None
    for x0 in range(int(w * 0.25), int(w * 0.60) - window_w, step):
        rng = (x0, x0 + window_w)
        ranks, pitch = scan_visible_ranks(image, rng)
        # Acceptance is strict because a wrong answer gets PERSISTED: at
        # least 4 badges, and a pitch matching how leaderboard rows actually
        # render (both measured devices sit at ~0.135x screen height; the
        # band below covers standard layouts -- a compact/popup layout needs
        # manual --badge-x calibration). One real run locked onto avatar
        # digits at the right of the list and poisoned every later run.
        if pitch is None or not (100 <= pitch <= 200) or len(ranks) < 4:
            continue
        score = len(ranks)
        if best is None or score > best[0]:
            best = (score, rng, ranks, pitch)
    if best is None:
        return None, {}, None
    return best[1], best[2], best[3]


def read_player_name(image: np.ndarray, region: tuple[int, int, int, int]) -> str | None:
    """OCR a region containing a player's display name (e.g. shown at the
    top of screen 5). Returns the cleaned-up string (whitespace collapsed,
    leading/trailing junk stripped), or None if OCR returned nothing.

    Unlike read_champion_name, this doesn't try to match against any list —
    it just gives back whatever Tesseract saw. The returned text may contain
    non-ASCII characters (Chinese/Korean etc.) since we use the general
    PSM-6 config without any character whitelist.
    """
    x, y, w, h = region
    crop = image[y:y + h, x:x + w]
    if crop.size == 0:
        return None
    result = read_text(crop, GENERAL_TESSERACT_CONFIG)
    text = " ".join(result.text.split()).strip()
    return text or None


def read_champion_name(image: np.ndarray, region: tuple[int, int, int, int]) -> str | None:
    """OCR a region containing a single champion-name label (e.g. "AATROX")
    and return the canonical champion name. Returns None if no match."""
    from . import champions as champ_module

    x, y, w, h = region
    crop = image[y:y + h, x:x + w]
    result = read_text(crop, GENERAL_TESSERACT_CONFIG)
    tokens = [t for t in result.text.split() if t.strip()]
    # Try longest spans first (handles "Master Yi", "Twisted Fate", etc.)
    for span in range(min(champ_module.MAX_WORD_COUNT, len(tokens)), 0, -1):
        for start in range(len(tokens) - span + 1):
            canonical = champ_module.match(tokens[start:start + span])
            if canonical is not None:
                return canonical
    return None


def find_champion_winrates(
    image: np.ndarray,
    region: tuple[int, int, int, int],
    champions: list[str] | None = None,
) -> dict[str, float]:
    """OCR a region containing one or more champion tiles and return a dict
    mapping canonical champion name -> winrate.

    Pairs each champion-name word with the percentage word that is nearest in
    x-position (same column = same tile).
    """
    from . import champions as champ_module

    champ_module_local = champ_module
    if champions is None:
        champions = champ_module_local.CHAMPIONS

    x, y, w, h = region
    crop = image[y:y + h, x:x + w]
    words = read_words(crop, GENERAL_TESSERACT_CONFIG)
    if not words:
        return {}

    # Find champion-name matches (greedy left-to-right, allowing multi-word names).
    name_hits: list[tuple[str, int]] = []  # (canonical_name, x_center)
    i = 0
    max_words = champ_module_local.MAX_WORD_COUNT
    while i < len(words):
        matched = False
        for span in range(min(max_words, len(words) - i), 0, -1):
            tokens = [words[i + k].text for k in range(span)]
            canonical = champ_module_local.match(tokens)
            if canonical is not None:
                xs = [words[i + k].x for k in range(span)]
                name_hits.append((canonical, sum(xs) // span))
                i += span
                matched = True
                break
        if not matched:
            i += 1

    # Find percentage matches.
    pct_hits: list[tuple[float, int]] = []  # (value, x_center)
    for word in words:
        m = PERCENT_PATTERN.fullmatch(word.text)
        if not m:
            continue
        try:
            value = float(m.group(1).replace(",", "."))
        except ValueError:
            continue
        if 0 <= value <= 100:
            pct_hits.append((value, word.x))

    # Pair each name with the percentage at the closest x.
    result: dict[str, float] = {}
    for name, nx in name_hits:
        if not pct_hits:
            break
        value, _px = min(pct_hits, key=lambda p: abs(p[1] - nx))
        result[name] = value
    return result


def _parse_crop(s: str) -> tuple[int, int, int, int]:
    parts = [int(p) for p in s.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("crop must be 'x,y,w,h'")
    return tuple(parts)  # type: ignore[return-value]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("image", type=Path, help="Path to a saved screenshot")
    parser.add_argument(
        "--crop", type=_parse_crop, default=None,
        help="Region to OCR as 'x,y,w,h' in image coords (default: whole image)",
    )
    parser.add_argument(
        "--mode", choices=("winrate", "text"), default="winrate",
        help="winrate: digits/percent whitelist + parse %. text: general OCR (names, labels, etc).",
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Save the preprocessed image next to the input as *_pre.png",
    )
    args = parser.parse_args()

    img = cv2.imread(str(args.image))
    if img is None:
        print(f"error: could not read {args.image}", file=sys.stderr)
        return 1

    if args.crop is not None:
        x, y, w, h = args.crop
        H, W = img.shape[:2]
        if x < 0 or y < 0 or x + w > W or y + h > H:
            print(f"error: crop {args.crop} out of bounds for {W}x{H} image", file=sys.stderr)
            return 1
        img = img[y:y + h, x:x + w]

    if args.mode == "winrate":
        value, result = read_winrate(img)
        print(f"raw text   : {result.text!r}")
        print(f"confidence : {result.confidence:.1f}")
        print(f"winrate    : {value}")
    else:
        result = read_text(img, GENERAL_TESSERACT_CONFIG)
        print(f"raw text   : {result.text!r}")
        print(f"confidence : {result.confidence:.1f}")

    if args.debug:
        out = args.image.with_name(args.image.stem + "_pre.png")
        cv2.imwrite(str(out), result.image)
        print(f"preprocessed image -> {out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
