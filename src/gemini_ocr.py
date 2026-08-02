"""Vision-LLM OCR for the leaderboard screen, using Google Gemini.

Tesseract struggles with the stylized rank badges and can't read non-ASCII
player names (Chinese / Korean / etc. — common at the top of Wild Rift's
global leaderboards). Gemini 1.5 Flash handles both, fast and cheap
(~$0.0001 per screenshot at current pricing).

Setup:
    pip install google-genai
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
This is a screenshot of a Wild Rift screen. Only extract player data if
you can confirm ALL of the following:

1. There is a SINGLE champion's name and large portrait/bust prominently
   shown at the BOTTOM-LEFT of the screen (e.g. "AATROX" with the
   champion's artwork).
2. The list shows ranked PLAYER rows (different player avatars per row,
   with numeric ranks 1, 2, 3, ...).
3. Every visible ranked row is for the SAME champion (the one shown at
   bottom-left). The list is NOT a list of different champions.

If ANY of these fails — for example each row shows a DIFFERENT champion
icon (that's the global champion list, NOT a per-champion leaderboard),
or it's a player's profile page, main menu, champion select, etc. —
respond with an empty JSON array: []

If the conditions are met, for each ranked PLAYER row, extract:
  - rank: the rank number (integer)
  - player_name: ONLY the player's main display name on the first line.
    Do NOT include any server tag, region code, or text on a separate
    line. Preserve non-ASCII characters exactly. No newlines.
  - score: the numeric score on the right, as an integer (strip commas)

Do NOT include the user's own self-row at the bottom (no numeric rank).

Respond ONLY with a JSON array. No prose, no markdown fences. Example:
[{"rank": 1, "player_name": "对家亡Akaza", "score": 21302},
 {"rank": 2, "player_name": "代池加诚LuxXingyu", "score": 20697}]
"""


STRIP_PROMPT = """\
This is a cropped horizontal strip of champion tiles from a Wild Rift player
profile ("CHAMPION AND LANE" page). Each fully visible tile shows, top to
bottom: the champion's name, a label ("Highest Achieved" or "Season highest"),
a large score number, "Games" with a count, and "Win Rate" with a percentage.

For every FULLY visible tile (skip tiles cut off at the left or right edge),
return:
  - champion: the champion name exactly as printed
  - score: the large score as an integer (strip commas), or null if unreadable
  - games: the games count as an integer, or null
  - win_rate: the win-rate as a number 0-100 without the % sign, or null

Respond ONLY with a JSON array, no prose, no markdown fences. Example:
[{"champion": "Aatrox", "score": 19076, "games": 523, "win_rate": 57.8}]
"""


@dataclass
class LeaderboardRow:
    rank: int
    player_name: str
    score: int | None


@dataclass
class StripTile:
    champion: str
    score: int | None
    games: int | None
    win_rate: float | None


_CLIENT = None  # cached google-genai client (one TLS handshake per run, not per call)


def _client():
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY env var not set. "
            "Get a key at https://aistudio.google.com/app/apikey"
        )
    try:
        from google import genai
    except ImportError as e:
        raise RuntimeError(
            "google-genai not installed. Run: pip install google-genai"
        ) from e
    try:
        # Bound the HTTP round trip so a network stall can't hang the scraper.
        _CLIENT = genai.Client(api_key=api_key, http_options={"timeout": 15_000})
    except TypeError:  # older SDK without http_options
        _CLIENT = genai.Client(api_key=api_key)
    return _CLIENT


def _extract_json(text: str) -> str:
    """Strip markdown code fences if Gemini wraps the JSON anyway."""
    text = text.strip()
    if text.startswith("```"):
        # Strip fenced block
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _generate_json(image: np.ndarray, prompt: str, model: str) -> list:
    """Send one image + prompt, expect a JSON array back."""
    from google.genai import types

    # Encode the BGR image as JPEG (smaller payload than PNG)
    ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise RuntimeError("Failed to JPEG-encode image")

    response = _client().models.generate_content(
        model=model,
        contents=[
            prompt,
            types.Part.from_bytes(data=bytes(buf), mime_type="image/jpeg"),
        ],
        # Server-side JSON mode: the model cannot emit prose or fences.
        # Temperature 0: extraction must be repeatable -- sampling variance
        # made the same frame's tiles appear and vanish between runs.
        config=types.GenerateContentConfig(
            response_mime_type="application/json", temperature=0.0),
    )
    raw = _extract_json(response.text or "")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        # Observed in the wild: a malformed \u escape inside a non-ASCII name
        # ("\u0ۂeriaatrox" for a Turkish S-cedilla) poisons the whole
        # array. Neutralize invalid \uXXXX sequences and salvage the rest.
        repaired = re.sub(r"\\u(?![0-9a-fA-F]{4})", r"\\\\u", raw)
        try:
            data = json.loads(repaired)
        except json.JSONDecodeError:
            raise RuntimeError(f"Gemini returned non-JSON: {raw[:200]!r}") from e
    if not isinstance(data, list):
        raise RuntimeError(f"Expected JSON array, got {type(data).__name__}: {raw[:200]!r}")
    return data


def read_strip(image: np.ndarray, model: str = "gemini-3.5-flash-lite") -> list[StripTile]:
    """Read every fully-visible champion tile from a screen-5 strip crop.
    One structured call replaces ~4 Tesseract passes over the same crop."""
    tiles: list[StripTile] = []
    for item in _generate_json(image, STRIP_PROMPT, model):
        try:
            wr = item.get("win_rate")
            wr_f = float(wr) if wr is not None else None
            if wr_f is not None and not (0.0 <= wr_f <= 100.0):
                wr_f = None
            tiles.append(StripTile(
                champion=str(item["champion"]).strip(),
                score=int(item["score"]) if item.get("score") is not None else None,
                games=int(item["games"]) if item.get("games") is not None else None,
                win_rate=wr_f,
            ))
        except (KeyError, ValueError, TypeError):
            continue
    return tiles


def read_leaderboard(image: np.ndarray, model: str = "gemini-3.5-flash-lite") -> list[LeaderboardRow]:
    """Send `image` to Gemini and return the parsed rows.

    Raises RuntimeError if the API key is missing or the response can't be
    parsed as JSON.
    """
    data = _generate_json(image, PROMPT, model)

    rows: list[LeaderboardRow] = []
    for item in data:
        try:
            # Strip any newlines / extra whitespace — Gemini sometimes
            # concatenates the server tag onto the name with a \n.
            name = str(item["player_name"]).split("\n", 1)[0].strip()
            rows.append(LeaderboardRow(
                rank=int(item["rank"]),
                player_name=name,
                score=int(item["score"]) if item.get("score") is not None else None,
            ))
        except (KeyError, ValueError, TypeError):
            continue
    rows.sort(key=lambda r: r.rank)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("image", type=Path)
    parser.add_argument("--model", default="gemini-3.5-flash-lite", help="Gemini model name")
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
