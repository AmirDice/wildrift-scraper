"""Champion image URLs via Riot's DDragon CDN.

Square face icon:
    https://ddragon.leagueoflegends.com/cdn/<VER>/img/champion/Aatrox.png

Full-body loading-screen art:
    https://ddragon.leagueoflegends.com/cdn/img/champion/loading/Aatrox_<skin_id>.jpg

The display name in our CSV ("Master Yi", "Aatrox", "Kai'Sa", "Wukong" ...)
isn't always identical to DDragon's filename key. `to_ddragon_key()` handles
the normalisation, including the messy apostrophe edge cases.
"""
from __future__ import annotations

import re


# Bump this when DDragon publishes a new patch.
DDRAGON_VERSION = "16.11.1"

_CDN_BASE = "https://ddragon.leagueoflegends.com/cdn"

# Explicit overrides for names that don't follow the simple
# "strip non-alphanum + TitleCase each word" rule. Keys are lowercased
# display names; values are the DDragon filename keys.
_SPECIAL_KEYS: dict[str, str] = {
    # Apostrophe names — DDragon is annoyingly inconsistent here.
    "cho'gath": "Chogath",
    "kai'sa": "Kaisa",
    "kha'zix": "Khazix",
    "vel'koz": "Velkoz",
    "bel'veth": "Belveth",
    "k'sante": "KSante",
    "kog'maw": "KogMaw",
    "rek'sai": "RekSai",

    # Other irregulars.
    "wukong": "MonkeyKing",
    "leblanc": "Leblanc",
    "le blanc": "Leblanc",
    "dr. mundo": "DrMundo",
    "dr mundo": "DrMundo",
    "jarvan iv": "JarvanIV",
    "nunu & willump": "Nunu",
    "nunu and willump": "Nunu",
    "nunu": "Nunu",
    "renata glasc": "Renata",
}

_WORD_RE = re.compile(r"[A-Za-z0-9]+")


def to_ddragon_key(name: str) -> str:
    """Convert a human display name like 'Master Yi' into DDragon's
    filename key like 'MasterYi'.

    Falls back to TitleCase-each-word + concatenation if the name is not in
    the special-case map.
    """
    if not name:
        return ""
    key = name.strip().lower()
    if key in _SPECIAL_KEYS:
        return _SPECIAL_KEYS[key]
    # Default: TitleCase each alphanumeric run, then concatenate.
    return "".join(part[:1].upper() + part[1:].lower() for part in _WORD_RE.findall(name))


# Champions that don't (yet) exist on Riot's DDragon CDN. For these we ship
# our own square icon at static/champions/<Key>.png and serve it locally.
# Key is the to_ddragon_key() form so lookups stay consistent.
_LOCAL_ICON_KEYS: frozenset[str] = frozenset({"Norra"})

# Champions where we OVERRIDE the DDragon splash with a locally-bundled
# image at static/champions/<Key>_splash.<ext>. The icon still comes from
# DDragon unless the champion is also in _LOCAL_ICON_KEYS. Used to feature
# custom skins (e.g. Mecha Hecarim) on the spotlight card.
_LOCAL_SPLASH_KEYS: dict[str, str] = {
    "Hecarim": "Hecarim_splash.jpg",
}


def icon_url(name: str, version: str = DDRAGON_VERSION) -> str:
    """Square face icon (PNG). ~120x120, good for circle avatars and table cells.

    Falls back to a locally-bundled icon (served from static/champions/) for
    champions DDragon doesn't host yet — see `_LOCAL_ICON_KEYS`.
    """
    key = to_ddragon_key(name)
    if key in _LOCAL_ICON_KEYS:
        return f"/app/static/champions/{key}.png"
    return f"{_CDN_BASE}/{version}/img/champion/{key}.png"


def splash_url(name: str, skin_id: int = 0) -> str:
    """Full-body loading-screen art (JPG, portrait orientation). skin_id=0
    is the default skin; non-zero ids select specific skins where DDragon
    has the asset.

    Resolution order:
      1. `_LOCAL_SPLASH_KEYS` override (custom local image, e.g. featured
         skin art for the spotlight card);
      2. icon fallback for icon-only champs that have no DDragon entry;
      3. DDragon loading-screen art.
    """
    key = to_ddragon_key(name)
    if key in _LOCAL_SPLASH_KEYS:
        return f"/app/static/champions/{_LOCAL_SPLASH_KEYS[key]}"
    if key in _LOCAL_ICON_KEYS:
        return f"/app/static/champions/{key}.png"
    return f"{_CDN_BASE}/img/champion/loading/{key}_{skin_id}.jpg"
