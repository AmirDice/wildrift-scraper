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
import functools
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


POPUP_PROMPT = """\
This is a Wild Rift player popup card (shown over a leaderboard). Extract:
  - player_name: the display name WITHOUT the #tag (preserve non-ASCII exactly)
  - riot_tag: the part after '#' if shown, else null
  - level: the account level number shown under/near the avatar, else null
  - tier: the ranked tier text (e.g. "Grandmaster III", "Challenger",
    "Sovereign" -- the LINE that names a competitive rank), else null
  - guild: the short guild/club tag on the dark chip if shown, else null
Respond ONLY with one JSON object, no prose:
{"player_name": "...", "riot_tag": "...", "level": 422, "tier": "Grandmaster III", "guild": "SLVF"}
"""

STATS_PROMPT = """\
This is a Wild Rift profile STATS page in list view. Extract exactly what is
printed (null for anything unreadable or absent):
  - player_name (preserve non-ASCII), tier (e.g. "Grandmaster I")
  - queue: the selected value of the middle dropdown at the top
    (e.g. "Ranked", "Legendary Ranked", "All matches", "Normal")
  - games, win_rate (number, no % sign)
  - mvp, s_rating, a_rating, legendary, pentakill, quadra_kill, triple_kill,
    first_blood  (the counters in the left panel)
  - kda, teamfight_participation (number, no %), gold_per_minute,
    damage_dealt_per_match, damage_taken_per_match, turret_damage_per_match
    (the list on the right; strip commas)
Respond ONLY with one JSON object, no prose.
"""

def _catalogues() -> tuple[str, str, str]:
    """The exact vocabulary a build popup can contain, as prompt text.

    Asking an open question ("name this icon") made the model answer from its
    League PC training data whenever an icon was unclear: 17.6% of captured
    rune slots came back as runes that do not exist in Wild Rift
    (Conditioning, Pathfinder, Press the Attack...), stated confidently. The
    lists below turn recognition into CLASSIFICATION over a closed set, which
    is both far easier and verifiable -- and lets the cheapest model do it.
    Runes carry their tree because the tree colours the icon frame (Domination
    red, Precision gold, Resolve green, Sorcery blue), which is the strongest
    visual cue for narrowing a guess.
    """
    root = Path(__file__).resolve().parent.parent
    runes = json.loads((root / "data" / "wrmeta_runes.json").read_text(encoding="utf-8"))
    by_tree: dict[str, list[str]] = {}
    for r in runes:
        by_tree.setdefault(r.get("tree") or r.get("type") or "Other", []).append(r["name"])
    rune_txt = "\n".join(f"  {tree}: " + ", ".join(sorted(names))
                         for tree, names in sorted(by_tree.items()))

    items = json.loads((root / "data" / "items.json").read_text(encoding="utf-8"))
    by_cat: dict[str, list[str]] = {}
    for it in items:
        by_cat.setdefault(it.get("category") or "Other", []).append(it["name"])
    item_txt = "\n".join(f"  {cat}: " + ", ".join(sorted(names))
                         for cat, names in sorted(by_cat.items()))

    spell_path = root / "web-next" / "src" / "data" / "spells.json"
    spells = json.loads(spell_path.read_text(encoding="utf-8")) if spell_path.exists() else []
    spell_txt = ", ".join(sorted(s["name"] for s in spells)) or "Flash, Ignite, Smite, Ghost"
    return rune_txt, item_txt, spell_txt


def _build_prompt() -> str:
    rune_txt, item_txt, spell_txt = _catalogues()
    return f"""\
You are given TWO images of the same Wild Rift build popup:
  1. the whole popup -- read the champion name, player name and "Rank: N" here;
  2. a 3x CLOSE-UP of only the icon rows -- identify every Spell, Rune and
     Item from THIS image, where the art is large and clear.
The rows are, top to bottom: Spells (2), Runes (5, keystone first), Items (up to 6).

CLOSED VOCABULARY. Every icon in this screenshot is one of the entries below.
These are the ONLY valid answers. Copy a name EXACTLY as written here.

SUMMONER SPELLS: {spell_txt}

RUNES (grouped by tree; the tree tints the icon frame -- Domination red,
Precision gold, Resolve green, Sorcery blue, Keystones sit in a larger frame):
{rune_txt}

ITEMS (grouped by category):
{item_txt}

RULES, and the third one matters most:
  1. Answer only with names from the lists above, spelled exactly.
  2. Read the icon ART, not what a similar League of Legends PC rune or item
     would be called. Many PC names do not exist in Wild Rift.
  3. If an icon does not clearly match one of the listed entries, answer "?"
     for that slot. A "?" is CORRECT and useful; a plausible guess that is not
     in the lists is a serious error. Never invent a name.

Return:
  - champion: the champion name printed at the top
  - player_name: the name under the portrait (preserve non-ASCII)
  - position: the integer after "Rank:"
  - spells: array of the 2 summoner spell names, in order
  - runes: array of the rune names, in order (first is the keystone)
  - items: array of the item names, in order (ignore small overlay markers)
Respond ONLY with one JSON object, no prose:
{{"champion": "Aatrox", "player_name": "...", "position": 1,
 "spells": ["Flash", "Ignite"], "runes": ["Conqueror", "..."],
 "items": ["Eclipse", "..."]}}
"""


_BUILD_PROMPT_CACHE: str | None = None


def BUILD_PROMPT() -> str:  # noqa: N802 -- kept callable so the lists load lazily
    global _BUILD_PROMPT_CACHE
    if _BUILD_PROMPT_CACHE is None:
        _BUILD_PROMPT_CACHE = _build_prompt()
    return _BUILD_PROMPT_CACHE


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


def _generate_obj(image: np.ndarray, prompt: str, model: str,
                  extra: np.ndarray | None = None) -> dict:
    """Like _generate_json but for prompts that return ONE JSON object.
    Tolerates the model wrapping it in a single-element array.

    `extra` attaches a second image to the same call -- used to send an
    upscaled close-up of the icon rows alongside the full popup, so text and
    icons are each read from pixels that suit them.
    """
    from google.genai import types

    parts = [prompt]
    for im in (image, extra):
        if im is None:
            continue
        ok, buf = cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, 92])
        if not ok:
            raise RuntimeError("Failed to JPEG-encode image")
        parts.append(types.Part.from_bytes(data=bytes(buf), mime_type="image/jpeg"))
    response = _client().models.generate_content(
        model=model,
        contents=parts,
        config=types.GenerateContentConfig(
            response_mime_type="application/json", temperature=0.0),
    )
    raw = _extract_json(response.text or "")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        repaired = re.sub(r"\\u(?![0-9a-fA-F]{4})", r"\\\\u", raw)
        try:
            data = json.loads(repaired)
        except json.JSONDecodeError:
            raise RuntimeError(f"Gemini returned non-JSON: {raw[:200]!r}") from e
    if isinstance(data, list) and data and isinstance(data[0], dict):
        data = data[0]
    if not isinstance(data, dict):
        raise RuntimeError(f"Expected JSON object, got {type(data).__name__}: {raw[:200]!r}")
    return data


def read_rank_popup(image: np.ndarray, model: str = "gemini-3.5-flash-lite") -> dict:
    """Player popup card: name#tag, account level, ranked tier, guild tag."""
    return _generate_obj(image, POPUP_PROMPT, model)


def read_stats_page(image: np.ndarray, model: str = "gemini-3.5-flash-lite") -> dict:
    """Profile STATS page (list view): per-queue player statistics. The
    returned 'queue' field is what the dropdown actually shows, so callers
    can verify the frame matches the queue they intended to capture."""
    return _generate_obj(image, STATS_PROMPT, model)


@functools.lru_cache(maxsize=1)
def _valid_names() -> tuple[frozenset[str], dict[str, str]]:
    """({normalised valid name}, {normalised: exact name}) for every spell,
    rune and item. Used to VERIFY what came back, because a closed vocabulary
    in the prompt only helps if something checks that the answer obeyed it."""
    rune_txt, item_txt, spell_txt = _catalogues()
    names: list[str] = [s.strip() for s in spell_txt.split(",")]
    for block in (rune_txt, item_txt):
        for line in block.splitlines():
            _, _, rest = line.partition(":")
            names += [n.strip() for n in rest.split(",") if n.strip()]
    norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())  # noqa: E731
    exact = {norm(n): n for n in names if n}
    return frozenset(exact), exact


def _verify_build(build: dict) -> tuple[dict, list[str]]:
    """Snap every returned name onto the catalogue; return (build, invalid).

    Near-misses (case, punctuation, "Legend Tenacity" for "Legend: Tenacity")
    are corrected silently. Anything with no catalogue match is replaced with
    "?" rather than kept: an invented name that reaches the data is worse than
    a hole, because it looks like evidence.
    """
    _, exact = _valid_names()
    norm = lambda s: re.sub(r"[^a-z0-9]", "", str(s).lower())  # noqa: E731
    invalid: list[str] = []
    for key in ("spells", "runes", "items"):
        cleaned = []
        for raw in (build.get(key) or []):
            if raw is None or str(raw).strip() in ("", "?"):
                cleaned.append("?")
                continue
            hit = exact.get(norm(raw))
            if hit:
                cleaned.append(hit)
            else:
                invalid.append(str(raw))
                cleaned.append("?")
        build[key] = cleaned
    return build, invalid


#: where the three icon rows sit inside a 2340x1080 build popup (y0,y1,x0,x1)
BUILD_ICON_REGION = (250, 780, 1180, 1960)


def _icon_closeup(image: np.ndarray, scale: float = 3.0) -> np.ndarray | None:
    """The three icon rows, cropped out and upscaled.

    The popup is 2340x1080 and each icon is about 50px, so a whole-screenshot
    read asks the model to identify 170-odd near-identical miniatures from a
    handful of pixels -- which is why it answered with confident guesses. The
    same icons at 3x fill the frame. Scaled by the frame's own size so a
    different device resolution still crops the right box.
    """
    h, w = image.shape[:2]
    y0, y1, x0, x1 = BUILD_ICON_REGION
    fy, fx = h / 1080, w / 2340
    crop = image[int(y0 * fy):int(y1 * fy), int(x0 * fx):int(x1 * fx)]
    if crop.size == 0 or crop.shape[0] < 40 or crop.shape[1] < 40:
        return None
    return cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)


def read_build_popup(image: np.ndarray, model: str = "gemini-3.5-flash-lite",
                     retries: int = 1) -> dict:
    """Build popup: champion, player, position, spell/rune/item names.

    Every name is verified against the closed catalogue. If the model returns
    something outside it, the popup is re-read once with the offending names
    called out, then anything still unmatched becomes "?" -- the extractor
    reports those rather than storing a guess. `_invalid` carries whatever was
    rejected so callers can log it.
    """
    closeup = _icon_closeup(image)
    build = _generate_obj(image, BUILD_PROMPT(), model, extra=closeup)
    build, invalid = _verify_build(build)
    for _ in range(max(0, retries)):
        if not invalid:
            break
        nudge = (BUILD_PROMPT() + "\nA previous attempt answered "
                 + ", ".join(f'"{n}"' for n in sorted(set(invalid))[:8])
                 + " -- none of those are in the lists above. Look at those icons"
                 " again and either pick the correct listed name or answer \"?\".")
        retry = _generate_obj(image, nudge, model, extra=closeup)
        retry, retry_invalid = _verify_build(retry)
        # keep the read that resolved more slots
        better = sum(1 for k in ("spells", "runes", "items")
                     for v in retry.get(k, []) if v != "?")
        current = sum(1 for k in ("spells", "runes", "items")
                      for v in build.get(k, []) if v != "?")
        if better > current:
            build, invalid = retry, retry_invalid
        else:
            break
    build["_invalid"] = sorted(set(invalid))
    return build


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
