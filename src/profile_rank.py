"""Read current and historical ladder ranks from a main-profile screenshot.

The profile screen displays two rank badges in the lower-right corner.  The
large badge is the current-season peak and the smaller badge is the highest
past-season rank.  This reader intentionally does not use a colour-only
heuristic: the rank artwork in ``web-next/public/tiers`` is matched with an
alpha mask, preserving both the silhouette and the pixels that distinguish
Sovereign from Challenger.

The count printed over each badge is read from a tight numeric crop after the
badge has been located.  Missing/ambiguous counts are returned as ``None``;
we never turn an uncertain OCR result into a made-up season count.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
import pytesseract

from .ocr import preprocess, read_text
from .tiers import canonical_profile_rank

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "web-next" / "public" / "tiers"
REFERENCE_DIR = ROOT / "data" / "ranks"

_RANK_ASSETS = {
    "Iron": "iron.webp",
    "Bronze": "bronze.webp",
    "Silver": "silver.webp",
    "Gold": "gold.webp",
    "Platinum": "platinum.webp",
    "Emerald": "emerald.webp",
    "Diamond": "diamond.webp",
    "Master": "master.webp",
    "Grandmaster": "grandmaster.webp",
    "Challenger": "challenger.webp",
    "Sovereign": "sovereign.webp",
}

_REFERENCE_NAME = re.compile(
    r"^\s*(?:(?P<current_count>\d+)x\s+)?(?P<current>[a-z]+)\s*,\s*"
    r"(?:(?P<historical_count>\d+)x\s+)?(?P<historical>[a-z]+)\s*$",
    re.IGNORECASE,
)
#: Single-CHARACTER modes, not single-line. The count is one or two glyphs in
#: a disc, and psm 7 reads the disc's surroundings as part of a text line.
_DIGITS = "--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789"
#: Tried in order on the ISOLATED glyphs. 13 and 8 carry most of them; 10 is
#: a last resort that rescues the odd glyph the other two decline (one
#: captured "5" read as nothing under both and cleanly under 10). Order
#: matters -- 10 is the loosest, so it only ever sees what the others refuse.
_DIGIT_CFGS = (
    "--oem 3 --psm 13 -c tessedit_char_whitelist=0123456789",
    "--oem 3 --psm 8 -c tessedit_char_whitelist=0123456789",
    "--oem 3 --psm 10 -c tessedit_char_whitelist=0123456789",
)
#: The count token's box as a fraction of the badge's own bbox. Measured off
#: 24 captured badges: the old (.25-.78, .58-1.06) was nearly half the badge
#: tall, so the token sat in a field of ornate artwork and nothing OCR'd.
_TOKEN_BOX = (0.28, 0.72, 0.78, 1.12)


@dataclass(frozen=True)
class ReferenceRanks:
    current: str
    historical: str
    current_count: int | None
    historical_count: int | None


@dataclass(frozen=True)
class _Template:
    rank: str
    image: np.ndarray
    mask: np.ndarray


def parse_reference_name(name: str) -> ReferenceRanks | None:
    """Parse a local reference filename such as ``13x grandmaster, 2x sovereign``."""
    stem = Path(name).stem
    match = _REFERENCE_NAME.match(stem)
    if not match:
        return None
    current = canonical_profile_rank(match.group("current"))
    historical = canonical_profile_rank(match.group("historical"))
    if not current or not historical:
        return None
    return ReferenceRanks(
        current=current,
        historical=historical,
        current_count=int(match.group("current_count")) if match.group("current_count") else None,
        historical_count=int(match.group("historical_count")) if match.group("historical_count") else None,
    )


def reference_ranks() -> dict[str, ReferenceRanks]:
    """Return the supplied screenshot labels, keyed by filename.

    The function is intentionally small and side-effect free so it can be
    used by calibration/tests without loading OpenCV templates.
    """
    out: dict[str, ReferenceRanks] = {}
    if not REFERENCE_DIR.exists():
        return out
    for path in sorted(REFERENCE_DIR.glob("*.jpg")):
        parsed = parse_reference_name(path.name)
        if parsed:
            out[path.name] = parsed
    return out


def _alpha_crop(image: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
    if image is None or image.size == 0:
        return None
    if image.ndim == 3 and image.shape[2] == 4:
        bgr, alpha = image[:, :, :3], image[:, :, 3]
    else:
        bgr = image
        # A few deployments convert the webp artwork to BGR and discard alpha.
        # Treat near-black pixels as transparent only for the outer crop; the
        # mask remains deliberately broad so dark Sovereign details survive.
        if bgr.ndim == 2:
            alpha = np.where(bgr > 8, 255, 0).astype(np.uint8)
            bgr = cv2.cvtColor(bgr, cv2.COLOR_GRAY2BGR)
        else:
            alpha = np.where(np.max(bgr, axis=2) > 8, 255, 0).astype(np.uint8)
    ys, xs = np.where(alpha > 24)
    if len(xs) == 0:
        return None
    x0, x1 = max(0, int(xs.min()) - 2), min(bgr.shape[1], int(xs.max()) + 3)
    y0, y1 = max(0, int(ys.min()) - 2), min(bgr.shape[0], int(ys.max()) + 3)
    return bgr[y0:y1, x0:x1].copy(), alpha[y0:y1, x0:x1].copy()


@lru_cache(maxsize=32)
def _template(rank: str, width: int) -> _Template | None:
    """Load a rank artwork resized to ``width`` pixels, retaining its mask."""
    path = ASSET_DIR / _RANK_ASSETS.get(rank, "")
    if not path.exists():
        return None
    source = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    cropped = _alpha_crop(source)
    if cropped is None:
        return None
    image, mask = cropped
    width = max(8, int(width))
    height = max(8, int(round(image.shape[0] * width / image.shape[1])))
    image = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
    mask = cv2.resize(mask, (width, height), interpolation=cv2.INTER_AREA)
    return _Template(rank, image, mask)


@lru_cache(maxsize=32)
def _asset_shape(rank: str) -> tuple[int, int] | None:
    path = ASSET_DIR / _RANK_ASSETS.get(rank, "")
    if not path.exists():
        return None
    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if image is None or image.ndim < 2:
        return None
    return int(image.shape[1]), int(image.shape[0])


def _match(source: np.ndarray, template: _Template) -> tuple[float, tuple[int, int]] | None:
    if source.shape[0] < template.image.shape[0] or source.shape[1] < template.image.shape[1]:
        return None
    mask = np.where(template.mask > 40, 255, 0).astype(np.uint8)
    try:
        scores = cv2.matchTemplate(source, template.image, cv2.TM_CCORR_NORMED, mask=mask)
    except cv2.error:
        # OpenCV builds without masked TM_CCORR support still get a useful
        # colour/shape match; transparent pixels are black in this fallback.
        scores = cv2.matchTemplate(source, template.image, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(scores)
    if score != score:  # NaN from an all-zero mask/source
        return None
    return float(score), (int(loc[0]), int(loc[1]))


#: How far the winning rank must sit above the runner-up rank for the read to
#: be believed. 0.03 was chosen from the measured distributions: it rejects
#: every Silver, Bronze and Iron read in the first NA collection while keeping
#: the nine Diamonds that sit deep on low-population boards (Corki, Rumble,
#: Sivir) and whose historical peaks corroborate them. It costs about 9% of
#: Master-and-above reads, which become unknown rather than wrong.
_MIN_MARGIN = 0.03

#: The HISTORICAL badge needs its own, much lower floor. It is drawn at .085 of
#: the frame height against the current badge's .125, so there is less pixel
#: detail to tell eleven similar crests apart and its margins are structurally
#: smaller: across seven hand-verified fixtures every historical badge read
#: Sovereign correctly on margins of 0.008 to 0.034, where the current badge on
#: the same frames ran 0.069 to 0.139. 0.03 was measured on the current badge
#: and applying it to both rejected six of those seven.
#:
#: A lower floor is also the right trade here: `tier`/`current_rank` is what
#: feeds the ladder component of the best-player score, while the historical
#: peak is only displayed. Seven independent frames agreeing on Sovereign is
#: signal; a coin flip would not keep landing on the same rank.
_MIN_MARGIN_HISTORICAL = 0.005


def _candidate(
    frame: np.ndarray, *, historical: bool
) -> tuple[str, float, tuple[int, int, int, int], float] | None:
    """Find the best badge in the expected lower-right profile region."""
    h, w = frame.shape[:2]
    if historical:
        x0, x1, y0, y1 = int(.875 * w), int(.999 * w), int(.67 * h), int(.95 * h)
        expected_h, centre = .085 * h, .95 * w
    else:
        x0, x1, y0, y1 = int(.78 * w), int(.945 * w), int(.64 * h), int(.95 * h)
        expected_h, centre = .125 * h, .875 * w
    source = frame[y0:y1, x0:x1]
    if source.size == 0:
        return None

    # Best adjusted score PER RANK, not one global best. The decision that
    # matters is "which rank is this", so the number that matters is how far
    # the winning rank sits above the runner-up rank -- see _MIN_MARGIN.
    per_rank: dict[str, tuple[float, tuple[int, int, int, int]]] = {}
    for rank in _RANK_ASSETS:
        # The profile layout is stable but phone scaling and crop margins vary.
        for factor in (.72, .86, 1.0, 1.14, 1.28):
            target_h = max(12, int(round(expected_h * factor)))
            # Assets are almost square; derive width from the source asset.
            raw_shape = _asset_shape(rank)
            if raw_shape is None or raw_shape[1] == 0:
                continue
            width = max(10, int(round(target_h * raw_shape[0] / raw_shape[1])))
            templ = _template(rank, width)
            if templ is None:
                continue
            found = _match(source, templ)
            if found is None:
                continue
            score, loc = found
            left = x0 + loc[0]
            top = y0 + loc[1]
            right = left + templ.image.shape[1]
            bottom = top + templ.image.shape[0]
            # Matching in the right place matters: it stops a champion icon or
            # a decorative badge elsewhere on the profile winning by accident.
            distance = abs((left + right) / 2 - centre) / max(1, w)
            adjusted = score - min(.12, distance * .75)
            # Only a FINITE score is a score. Masked correlation returns inf
            # when the variance under the mask underflows, and every ordinary
            # guard silently passes it: `inf != inf` is False, `inf < .50` is
            # False, and `inf - inf` is nan, which then also compares False
            # against the margin. Every Iron and Bronze read in the first NA
            # collection came through that gap, each reported "high".
            if not math.isfinite(float(adjusted)):
                continue
            prev = per_rank.get(rank)
            if prev is None or adjusted > prev[0]:
                per_rank[rank] = (adjusted, (left, top, right, bottom))
    # A blank is safer than assigning Challenger/Sovereign from a decorative
    # element.  Real badge matches in the supplied references are well above
    # this masked-correlation floor; low scores are deliberately declined.
    if not per_rank:
        return None
    ordered = sorted(per_rank.items(), key=lambda kv: -kv[1][0])
    (rank, (score, bbox)) = ordered[0]
    if score < .50:
        return None
    # The ABSOLUTE floor is not enough on its own. Measured over 153 profiles,
    # every one of the eleven templates scores 0.73-0.80 on a badge, so .50
    # passes all of them and the winner is whichever happened to edge ahead:
    # one rank-1 Sovereign was read as Silver because Silver beat Challenger
    # by 0.0044. What separates a real read from a coin toss is the MARGIN to
    # the runner-up rank -- median 0.0755 on reads that landed Master or above
    # against 0.0102 on the sub-Master reads that turned out to be wrong.
    # Below the threshold we return nothing, because "unknown" is a usable
    # answer and a fabricated tier is not.
    margin = score - ordered[1][1][0] if len(ordered) > 1 else score
    if margin < (_MIN_MARGIN_HISTORICAL if historical else _MIN_MARGIN):
        return None
    return rank, score, bbox, margin


def _isolate_digits(binary: np.ndarray) -> np.ndarray | None:
    """Crop a thresholded token to just its digit glyphs, or None.

    The crop still catches the badge's lower artwork, which thresholds into a
    jagged mass along the top edge. Dropping any component that touches an
    edge removes it, because the digits sit inside the disc and never do.
    """
    h, w = binary.shape
    count, _lbl, stats, _c = cv2.connectedComponentsWithStats(
        (binary > 0).astype(np.uint8), connectivity=8)
    keep: list[tuple[int, int, int, int]] = []
    for i in range(1, count):
        x, y, gw, gh, area = (int(stats[i, cv2.CC_STAT_LEFT]),
                              int(stats[i, cv2.CC_STAT_TOP]),
                              int(stats[i, cv2.CC_STAT_WIDTH]),
                              int(stats[i, cv2.CC_STAT_HEIGHT]),
                              int(stats[i, cv2.CC_STAT_AREA]))
        if y <= 1 or y + gh >= h - 1 or x <= 1 or x + gw >= w - 1:
            continue
        if not (0.20 * h <= gh <= 0.80 * h):
            continue
        if gw > 1.3 * gh or area < 0.15 * gw * gh:
            continue
        keep.append((x, y, gw, gh))
    if not keep:
        return None
    # A two-digit count is two glyphs on one baseline; anything off that line
    # is decoration that survived the edge test.
    centres = [k[1] + k[3] / 2 for k in keep]
    mid = sorted(centres)[len(centres) // 2]
    row = [k for k, c in zip(keep, centres) if abs(c - mid) < 0.25 * h]
    x0 = min(k[0] for k in row)
    y0 = min(k[1] for k in row)
    x1 = max(k[0] + k[2] for k in row)
    y1 = max(k[1] + k[3] for k in row)
    pad = max(2, int(0.12 * (y1 - y0)))
    return binary[max(0, y0 - pad):min(h, y1 + pad),
                  max(0, x0 - pad):min(w, x1 + pad)]


def _badge_count(frame: np.ndarray, bbox: tuple[int, int, int, int]) -> int | None:
    """The season count stamped on a badge, or None.

    Both POLARITIES are tried, and that is the whole trick. Otsu picks one
    global threshold, and the two badges sit on different grounds: on the
    historical badge the digit comes out white on black, while on the larger
    current badge the disc itself goes white and the digit is a black hole
    inside it. Searching only for bright glyphs found every historical count
    and not one current count -- 12 players all reading "?" for a figure that
    is perfectly legible on screen.

    Measured over 24 captured badges with known values: 0/20 before, 19/20
    after. Uncertain counts stay None; we never invent a season count.
    """
    left, top, right, bottom = bbox
    width, height = right - left, bottom - top
    ax0, ax1, ay0, ay1 = _TOKEN_BOX
    x0 = max(0, left + int(width * ax0))
    x1 = min(frame.shape[1], left + int(width * ax1))
    y0 = max(0, top + int(height * ay0))
    y1 = min(frame.shape[0], top + int(height * ay1))
    crop = frame[y0:y1, x0:x1]
    if crop.size == 0:
        return None
    for invert in (False, True):
        try:
            binary = preprocess(crop, scale=3.0, invert=invert)
        except Exception:  # noqa: BLE001 -- a bad crop must not stop a batch
            continue
        glyphs = _isolate_digits(binary)
        if glyphs is None or glyphs.size == 0:
            continue
        padded = cv2.copyMakeBorder(glyphs, 14, 14, 14, 14,
                                    cv2.BORDER_CONSTANT, value=0)
        for config in _DIGIT_CFGS:
            try:
                text = pytesseract.image_to_string(padded, config=config)
            except Exception:  # noqa: BLE001
                continue
            digits = re.findall(r"\d", text or "")
            if not digits:
                continue
            value = int("".join(digits))
            if 1 <= value <= 999:
                return value
    return None


def read_profile_ranks(frame: np.ndarray) -> dict:
    """Read both profile badges and their season counts.

    ``current`` and ``historical`` are either ``None`` or dictionaries with
    ``rank``, ``count``, ``score`` and ``bbox``.  ``confidence`` is useful in
    extraction reports; callers should still treat a missing rank as unknown.
    """
    if frame is None or not isinstance(frame, np.ndarray) or frame.size == 0:
        return {"current": None, "historical": None, "confidence": "low", "source": "template"}
    found: dict[str, dict | None] = {}
    margins: list[float] = []
    for key, historical in (("current", False), ("historical", True)):
        candidate = _candidate(frame, historical=historical)
        if candidate is None:
            found[key] = None
            continue
        rank, score, bbox, margin = candidate
        found[key] = {
            "rank": rank,
            "count": _badge_count(frame, bbox),
            "score": round(score, 4),
            "margin": round(margin, 4),
            "bbox": list(bbox),
        }
        margins.append(margin)
    # Confidence tracks the MARGIN, not the raw score. Keying it on the score
    # made it meaningless: every badge scores well above any absolute floor,
    # so every read -- including the Sovereign that came out Silver -- was
    # reported "high".
    if len(margins) == 2 and min(margins) >= 2 * _MIN_MARGIN_HISTORICAL:
        confidence = "high"
    elif margins:
        confidence = "medium"
    else:
        confidence = "low"
    return {**found, "confidence": confidence, "source": "template"}
