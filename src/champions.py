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
    "Yasuo", "Yone", "Yorick", "Yunara", "Yuumi",
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


# Stylized capitals OCR as digits ('ZOE' -> '2OE' skipped Zoe on a live run).
# Champion names contain no digits, so mapping each digit to its lookalike
# letter BEFORE stripping can only help.
_DIGIT_LOOKALIKES = str.maketrans("01258", "olzsb")


def match(tokens: list[str]) -> str | None:
    """If `tokens` (a sequence of 1+ OCR words) joined matches a champion name,
    return the canonical name. Otherwise None.

    Fallbacks, each earned by a live miss: digit lookalikes are re-lettered
    ('2OE' -> Zoe), and single-character tokens are dropped (OCR renders the
    '&' of "Nunu & Willump" as lone junk that poisons the join)."""
    joined = _normalize("".join(tokens))
    hit = NORMALIZED_TO_CANONICAL.get(joined)
    if hit:
        return hit
    relettered = _normalize("".join(tokens).lower().translate(_DIGIT_LOOKALIKES))
    if relettered != joined:
        hit = NORMALIZED_TO_CANONICAL.get(relettered)
        if hit:
            return hit
    cleaned = _normalize("".join(t for t in tokens if len(t.strip()) > 1))
    if cleaned != joined:
        return NORMALIZED_TO_CANONICAL.get(cleaned)
    return None
