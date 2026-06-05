"""Vision-LLM OCR for the leaderboard screen, using Google Gemini.

Tesseract struggles with the stylized rank badges and can't read non-ASCII
player names (Chinese / Korean / etc. — common at the top of Wild Rift's
global leaderboards). Gemini 1.5 Flash handles both, fast and cheap
(~$0.0001 per screenshot at current pricing).

Setup:
    pip install google-generativeai
    set GEMINI_API_KEY=<your key>     (PowerShell: $env:GEMINI_API_KEY = "...")

Run as a CLI to sanity-check before wiring it into the scraper:
    python -m src.gemini_ocr data/2_aatrox_leaderboard.png
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


PROMPT = """\
This is a screenshot of a Wild Rift leaderboard screen.

For each player row that's visible (the rows with rank numbers 1, 2, 3, etc.
on the left), extract:
  - rank: the rank number (integer)
  - player_name: the full player name as displayed (preserve any non-ASCII
    characters exactly)
  - score: the numeric score on the right, as an integer (strip commas)

Do NOT include the user's own bottom self-row (the one without a numeric rank).

Respond ONLY with a JSON array. No prose, no markdown fences. Example:
[{"rank": 1, "player_name": "对家亡Akaza", "score": 21302},
 {"rank": 2, "player_name": "代池加诚LuxXingyu", "score": 20697}]
"""


@dataclass
class LeaderboardRow:
    rank: int
    player_name: str
    score: int | None


def _extract_json(text: str) -> str:
    """Strip markdown code fences if Gemini wraps the JSON anyway."""
    text = text.strip()
    if text.startswith("```"):
        # Strip fenced block
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def read_leaderboard(image: np.ndarray, model: str = "gemini-1.5-flash") -> list[LeaderboardRow]:
    """Send `image` to Gemini and return the parsed rows.

    Raises RuntimeError if the API key is missing or the response can't be
    parsed as JSON.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY env var not set. "
            "Get a key at https://aistudio.google.com/app/apikey"
        )

    try:
        import google.generativeai as genai
    except ImportError as e:
        raise RuntimeError(
            "google-generativeai not installed. Run: pip install google-generativeai"
        ) from e

    genai.configure(api_key=api_key)

    # Encode the BGR image as JPEG (smaller payload than PNG)
    ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise RuntimeError("Failed to JPEG-encode image")

    model_obj = genai.GenerativeModel(model)
    response = model_obj.generate_content([
        PROMPT,
        {"mime_type": "image/jpeg", "data": bytes(buf)},
    ])

    raw = _extract_json(response.text or "")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Gemini returned non-JSON: {raw[:200]!r}") from e
    if not isinstance(data, list):
        raise RuntimeError(f"Expected JSON array, got {type(data).__name__}: {raw[:200]!r}")

    rows: list[LeaderboardRow] = []
    for item in data:
        try:
            rows.append(LeaderboardRow(
                rank=int(item["rank"]),
                player_name=str(item["player_name"]),
                score=int(item["score"]) if item.get("score") is not None else None,
            ))
        except (KeyError, ValueError, TypeError):
            # Skip malformed entries silently — Gemini is usually consistent
            continue
    rows.sort(key=lambda r: r.rank)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("image", type=Path)
    parser.add_argument("--model", default="gemini-1.5-flash", help="Gemini model name")
    args = parser.parse_args()

    img = cv2.imread(str(args.image))
    if img is None:
        print(f"error: could not read {args.image}", file=sys.stderr)
        return 1

    try:
        rows = read_leaderboard(img, model=args.model)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print(f"{len(rows)} row(s) returned:")
    for r in rows:
        score_str = f"{r.score:,}" if r.score is not None else "—"
        print(f"  rank {r.rank:>3}: {r.player_name!s:<30} score: {score_str}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
