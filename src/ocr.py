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
