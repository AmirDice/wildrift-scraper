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

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from .ocr import read_text
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
_DIGITS = "--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789"


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


def _candidate(frame: np.ndarray, *, historical: bool) -> tuple[str, float, tuple[int, int, int, int]] | None:
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

    best: tuple[float, str, tuple[int, int, int, int]] | None = None
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
            candidate = (adjusted, rank, (left, top, right, bottom))
            if best is None or candidate[0] > best[0]:
                best = candidate
    # A blank is safer than assigning Challenger/Sovereign from a decorative
    # element.  Real badge matches in the supplied references are well above
    # this masked-correlation floor; low scores are deliberately declined.
    if best is None or best[0] < .50:
        return None
    return best[1], best[0], best[2]


def _badge_count(frame: np.ndarray, bbox: tuple[int, int, int, int]) -> int | None:
    left, top, right, bottom = bbox
    width, height = right - left, bottom - top
    # The count is painted on the lower centre of the badge. Keep the crop
    # tight enough that the adjacent small/large badge cannot be read instead.
    x0 = max(0, left + int(width * .25))
    x1 = min(frame.shape[1], left + int(width * .78))
    y0 = max(0, top + int(height * .58))
    y1 = min(frame.shape[0], bottom + int(height * .06))
    crop = frame[y0:y1, x0:x1]
    if crop.size == 0:
        return None
    try:
        result = read_text(crop, config=_DIGITS)
    except Exception:
        return None
    values = [int(value) for value in re.findall(r"\d{1,3}", result.text or "")]
    values = [value for value in values if 1 <= value <= 999]
    if not values:
        return None
    # A single tight badge crop should produce one token. If OCR split it,
    # joining the tokens is safer than choosing a random fragment.
    return int("".join(str(v) for v in values))


def read_profile_ranks(frame: np.ndarray) -> dict:
    """Read both profile badges and their season counts.

    ``current`` and ``historical`` are either ``None`` or dictionaries with
    ``rank``, ``count``, ``score`` and ``bbox``.  ``confidence`` is useful in
    extraction reports; callers should still treat a missing rank as unknown.
    """
    if frame is None or not isinstance(frame, np.ndarray) or frame.size == 0:
        return {"current": None, "historical": None, "confidence": "low", "source": "template"}
    found: dict[str, dict | None] = {}
    scores: list[float] = []
    for key, historical in (("current", False), ("historical", True)):
        candidate = _candidate(frame, historical=historical)
        if candidate is None:
            found[key] = None
            continue
        rank, score, bbox = candidate
        found[key] = {
            "rank": rank,
            "count": _badge_count(frame, bbox),
            "score": round(score, 4),
            "bbox": list(bbox),
        }
        scores.append(score)
    if len(scores) == 2 and min(scores) >= .58:
        confidence = "high"
    elif scores:
        confidence = "medium"
    else:
        confidence = "low"
    return {**found, "confidence": confidence, "source": "template"}
