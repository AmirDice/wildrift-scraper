"""Canonical list of Wild Rift champion names.

Used by the OCR finder to identify which words in a screenshot are champion
names. Stored as a Python list rather than a JSON file so it's importable and
diff-friendly. Extend as new champions release.

Names are stored in their canonical (display) form. The OCR finder matches
case-insensitively after stripping punctuation, so "Kai'Sa" matches "KAISA"
and "Master Yi" matches "MASTER YI".
"""
from __future__ import annotations

import re


CHAMPIONS: list[str] = [
    "Aatrox", "Ahri", "Akali", "Akshan", "Alistar", "Amumu", "Annie", "Aphelios",
    "Ambessa", "Ashe", "Aurelion Sol", "Aurora",
    "Bard", "Bel'Veth", "Blitzcrank", "Brand", "Braum", "Briar",
    "Caitlyn", "Camille", "Cassiopeia", "Cho'Gath", "Corki",
    "Darius", "Diana", "Dr. Mundo", "Draven",
    "Ekko", "Evelynn", "Ezreal",
    "Fiddlesticks", "Fiora", "Fizz",
    "Galio", "Gangplank", "Garen", "Gnar", "Gragas", "Graves", "Gwen",
    "Hecarim", "Heimerdinger", "Hwei",
    "Illaoi", "Irelia", "Ivern",
    "Janna", "Jarvan IV", "Jax", "Jayce", "Jhin", "Jinx",
    "K'Sante", "Kai'Sa", "Kalista", "Karma", "Karthus", "Kassadin", "Katarina", "Kayle",
    "Kayn", "Kennen", "Kha'Zix", "Kindred", "Kled", "Kog'Maw",
    "LeBlanc", "Lee Sin", "Leona", "Lillia", "Lissandra", "Lucian", "Lulu", "Lux",
    "Malphite", "Malzahar", "Maokai", "Master Yi", "Mel", "Milio", "Miss Fortune",
    "Mordekaiser", "Morgana",
    "Naafiri", "Nami", "Nasus", "Nautilus", "Neeko", "Nidalee", "Nilah", "Nocturne",
    "Norra", "Nunu & Willump",
    "Olaf", "Orianna", "Ornn",
    "Pantheon", "Poppy", "Pyke",
    "Qiyana",
    "Rakan", "Rammus", "Renekton", "Rell", "Renata Glasc", "Rengar", "Riven",
    "Rumble", "Ryze",
    "Samira", "Senna", "Seraphine", "Sett", "Shen", "Shyvana", "Singed", "Sion",
    "Sivir", "Skarner", "Smolder", "Sona", "Soraka", "Swain", "Sylas", "Syndra",
    "Taliyah", "Talon", "Taric", "Teemo", "Thresh", "Tristana", "Trundle", "Tryndamere",
    "Twisted Fate", "Twitch",
    "Udyr", "Urgot",
    "Varus", "Vayne", "Veigar", "Vel'Koz", "Vex", "Vi", "Viego", "Viktor", "Vladimir",
    "Volibear",
    "Warwick", "Wukong",
    "Xayah", "Xerath", "Xin Zhao",
    "Yasuo", "Yone", "Yorick", "Yuumi",
    "Zac", "Zed", "Zeri", "Ziggs", "Zilean", "Zoe", "Zyra",
]


def _normalize(name: str) -> str:
    """Lowercase + strip everything that is not a letter. Champion names
    contain no digits, and OCR loves turning '&' into '8' ("NUNU 8 WILLUMP"),
    so digits are noise here, never signal."""
    return re.sub(r"[^a-z]", "", name.lower())


# name (normalized) -> canonical display name
NORMALIZED_TO_CANONICAL: dict[str, str] = {_normalize(c): c for c in CHAMPIONS}

# Number of words in the canonical name, by canonical name. Used to handle
# multi-word names ("Master Yi") that OCR splits into separate tokens.
WORD_COUNT: dict[str, int] = {c: len(c.split()) for c in CHAMPIONS}
MAX_WORD_COUNT: int = max(WORD_COUNT.values())


def match(tokens: list[str]) -> str | None:
    """If `tokens` (a sequence of 1+ OCR words) joined matches a champion name,
    return the canonical name. Otherwise None.

    Second try drops single-character tokens: no champion name contains a
    one-letter word, but OCR renders '&' as a lone junk character ('S', '@')
    that poisons the join for "Nunu & Willump"."""
    joined = _normalize("".join(tokens))
    hit = NORMALIZED_TO_CANONICAL.get(joined)
    if hit:
        return hit
    cleaned = _normalize("".join(t for t in tokens if len(t.strip()) > 1))
    if cleaned != joined:
        return NORMALIZED_TO_CANONICAL.get(cleaned)
    return None
