"""Static per-champion metadata: combat CLASS and DIFFICULTY rating.

Used for:
  * the meta breakdown ("is it a tank meta / bruiser meta right now?") which
    aggregates win rate by class;
  * the difficulty rating shown on the Champions page.

Classes use a six-way taxonomy:
    Tank       - frontline / crowd control / durability
    Bruiser    - divers, juggernauts, skirmishers (sustained melee damage)
    Assassin   - burst single-target killers
    Mage       - ability-power casters
    Marksman   - ranged auto-attack carries (ADC)
    Enchanter  - supports built around buffing/healing allies

Difficulty is an approximate 1-10 mechanical-complexity rating (1 = point-
and-click simple, 10 = high execution ceiling). These are judgement calls,
not exact science — see the Methodology page.
"""
from __future__ import annotations

import math

CLASSES: tuple[str, ...] = (
    "Tank", "Bruiser", "Assassin", "Mage", "Marksman", "Enchanter",
)

# champion -> (class, difficulty 1-10)
_META: dict[str, tuple[str, int]] = {
    # --- Tanks ---
    "Alistar": ("Tank", 4), "Amumu": ("Tank", 3), "Blitzcrank": ("Tank", 4),
    "Braum": ("Tank", 4), "Cho'Gath": ("Tank", 4), "Dr. Mundo": ("Tank", 3),
    "Galio": ("Tank", 5), "Leona": ("Tank", 4), "Malphite": ("Tank", 3),
    "Maokai": ("Tank", 3), "Nautilus": ("Tank", 4), "Nunu & Willump": ("Tank", 3),
    "Ornn": ("Tank", 5), "Poppy": ("Tank", 4), "Rammus": ("Tank", 3),
    "Rell": ("Tank", 5), "Sejuani": ("Tank", 4), "Shen": ("Tank", 5),
    "Singed": ("Tank", 5), "Sion": ("Tank", 4), "Skarner": ("Tank", 5),
    "Taric": ("Tank", 5), "Zac": ("Tank", 5), "Garen": ("Tank", 2),
    "K'Sante": ("Tank", 9), "Volibear": ("Tank", 4),

    # --- Bruisers (fighters / divers / juggernauts / skirmishers) ---
    "Aatrox": ("Bruiser", 6), "Ambessa": ("Bruiser", 7), "Bel'Veth": ("Bruiser", 8),
    "Briar": ("Bruiser", 6), "Camille": ("Bruiser", 7), "Darius": ("Bruiser", 4),
    "Fiora": ("Bruiser", 8), "Gangplank": ("Bruiser", 9),
    "Gnar": ("Bruiser", 8), "Gwen": ("Bruiser", 6), "Hecarim": ("Bruiser", 5),
    "Illaoi": ("Bruiser", 6), "Irelia": ("Bruiser", 8), "Jarvan IV": ("Bruiser", 5),
    "Jax": ("Bruiser", 5), "Kled": ("Bruiser", 7),
    "Lee Sin": ("Bruiser", 10), "Lillia": ("Mage", 6),
    "Mordekaiser": ("Bruiser", 4), "Nasus": ("Bruiser", 3), "Olaf": ("Bruiser", 4),
    "Renekton": ("Bruiser", 5), "Riven": ("Bruiser", 9),
    "Sett": ("Bruiser", 4), "Trundle": ("Bruiser", 4), "Tryndamere": ("Bruiser", 4),
    "Udyr": ("Bruiser", 6), "Urgot": ("Bruiser", 7), "Vi": ("Bruiser", 3),
    "Wukong": ("Bruiser", 5), "Xin Zhao": ("Bruiser", 4), "Yasuo": ("Bruiser", 7),
    "Yorick": ("Bruiser", 5), "Yone": ("Bruiser", 8),

    # --- Assassins (AD assassins only; AP assassins are classed as Mages) ---
    "Akshan": ("Assassin", 7), "Kha'Zix": ("Assassin", 6),
    "Master Yi": ("Assassin", 4), "Naafiri": ("Assassin", 5),
    "Nocturne": ("Assassin", 5), "Pyke": ("Assassin", 7),
    "Qiyana": ("Assassin", 9), "Rengar": ("Assassin", 7), "Shaco": ("Assassin", 8),
    "Talon": ("Assassin", 7), "Zed": ("Assassin", 8),
    "Kayn": ("Assassin", 7), "Pantheon": ("Assassin", 4),
    "Viego": ("Assassin", 7), "Warwick": ("Assassin", 3),

    # --- Mages ---
    "Ahri": ("Mage", 5), "Anivia": ("Mage", 7), "Annie": ("Mage", 2),
    "Aurelion Sol": ("Mage", 5), "Aurora": ("Mage", 6), "Brand": ("Mage", 3),
    "Cassiopeia": ("Mage", 7), "Fiddlesticks": ("Mage", 5), "Heimerdinger": ("Mage", 7),
    "Hwei": ("Mage", 9), "Karma": ("Mage", 5), "Karthus": ("Mage", 6),
    "Kennen": ("Mage", 6), "Lissandra": ("Mage", 6), "Lux": ("Mage", 4),
    "Malzahar": ("Mage", 4), "Mel": ("Mage", 6), "Morgana": ("Mage", 4),
    "Neeko": ("Mage", 6), "Norra": ("Mage", 6), "Orianna": ("Mage", 8),
    "Ryze": ("Mage", 5), "Swain": ("Mage", 5), "Syndra": ("Mage", 3),
    "Taliyah": ("Mage", 5), "Twisted Fate": ("Mage", 6), "Veigar": ("Mage", 4),
    "Vel'Koz": ("Mage", 6), "Vex": ("Mage", 5), "Viktor": ("Mage", 7),
    "Vladimir": ("Mage", 6), "Xerath": ("Mage", 6), "Ziggs": ("Mage", 5),
    "Zoe": ("Mage", 8), "Zyra": ("Mage", 5),
    # AP assassins classed as Mages
    "Akali": ("Mage", 8), "Diana": ("Mage", 5), "Ekko": ("Mage", 8),
    "Evelynn": ("Mage", 5), "Fizz": ("Mage", 6), "Gragas": ("Mage", 5),
    "Kassadin": ("Mage", 7), "Katarina": ("Mage", 8), "LeBlanc": ("Mage", 9),
    "Nidalee": ("Mage", 7), "Rumble": ("Mage", 6), "Teemo": ("Mage", 4),

    # --- Marksmen (ADC) ---
    # Difficulty per project owner's spec: Draven Very Hard; Vayne / Lucian /
    # Kalista Hard; Zeri / Samira / Xayah Moderate; everyone else Easy.
    # Graves / Kindred / Nilah / Senna kept at prior values — they're marksman
    # class but assigned to Jungle/Support roles, not part of the ADC pool.
    "Aphelios": ("Marksman", 10), "Ashe": ("Marksman", 3), "Caitlyn": ("Marksman", 3),
    "Corki": ("Marksman", 3), "Draven": ("Marksman", 10), "Ezreal": ("Marksman", 3),
    "Graves": ("Marksman", 7), "Jhin": ("Marksman", 3), "Jinx": ("Marksman", 3),
    "Kai'Sa": ("Marksman", 3), "Kalista": ("Marksman", 7), "Kindred": ("Marksman", 7),
    "Kog'Maw": ("Marksman", 3), "Lucian": ("Marksman", 7), "Miss Fortune": ("Marksman", 3),
    "Nilah": ("Marksman", 6), "Samira": ("Marksman", 5), "Senna": ("Marksman", 6),
    "Sivir": ("Marksman", 3), "Smolder": ("Marksman", 3), "Tristana": ("Marksman", 3),
    "Twitch": ("Marksman", 3), "Varus": ("Marksman", 3), "Vayne": ("Marksman", 7),
    "Xayah": ("Marksman", 5), "Zeri": ("Marksman", 5), "Kayle": ("Marksman", 6),

    # --- Enchanters / utility supports ---
    "Bard": ("Enchanter", 9), "Janna": ("Enchanter", 5), "Lulu": ("Enchanter", 5),
    "Milio": ("Enchanter", 3), "Nami": ("Enchanter", 5), "Rakan": ("Enchanter", 6),
    "Renata Glasc": ("Enchanter", 6), "Seraphine": ("Enchanter", 4), "Sona": ("Enchanter", 3),
    "Soraka": ("Enchanter", 3), "Thresh": ("Enchanter", 7), "Yuumi": ("Enchanter", 3),
    "Zilean": ("Enchanter", 6),
}

# Fallbacks for anything not explicitly mapped.
_DEFAULT_CLASS = "Bruiser"
_DEFAULT_DIFFICULTY = 5


def champion_class(name: str) -> str:
    """Combat class for a champion (defaults to Bruiser if unmapped)."""
    entry = _META.get(name)
    return entry[0] if entry else _DEFAULT_CLASS


def champion_difficulty(name: str) -> int:
    """Approximate 1-10 mechanical difficulty (defaults to 5 if unmapped)."""
    entry = _META.get(name)
    return entry[1] if entry else _DEFAULT_DIFFICULTY


def difficulty_label(d: int) -> str:
    """Bucket a 1-10 difficulty into a word."""
    if d <= 3:
        return "Easy"
    if d <= 6:
        return "Moderate"
    if d <= 8:
        return "Hard"
    return "Very Hard"


def difficulty_dots(d: int) -> int:
    """How many of 5 dots to fill for a 1-10 difficulty.

    Uses ceil(d/2) so the words map to distinct dot counts:
    Easy(3)=2, Moderate(5)=3, Hard(7)=4, Very Hard(10)=5.
    """
    return max(1, min(5, math.ceil(d / 2)))
