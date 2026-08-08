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

# Official Wild Rift head icons (slug -> url), preferred over ddragon's PC art
# which is often out of date vs Wild Rift. Built by scripts/scrape_wr_icons.py.
import json as _json
from pathlib import Path as _Path

_WR_ICONS: dict[str, str] = {}
try:
    _p = _Path(__file__).resolve().parent.parent / "data" / "wr_icons.json"
    if _p.exists():
        _WR_ICONS = _json.loads(_p.read_text(encoding="utf-8"))
except Exception:  # pragma: no cover - icons just fall back to ddragon
    _WR_ICONS = {}


def _wr_slug(name: str) -> str:
    s = name.lower().replace("&", "and").replace("'", "")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")

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


# These two tables used to point at images bundled under static/champions/,
# served by web.local_assets. Both static/ and local_assets belonged to the
# retired Streamlit app and were removed in the 2026-08-07 cleanup, so the
# overrides now have nothing to resolve to and every champion falls back to
# the CDN chain (Wild Rift head icons first, then DDragon). Kept as empty
# tables rather than deleted: the mechanism is the right place to hang a
# local asset if one is ever bundled for web-next, and the fallback is what
# the site has actually been serving since the cleanup either way.
_LOCAL_ICON_KEYS: frozenset[str] = frozenset()

_LOCAL_SPLASH_KEYS: dict[str, str] = {}


def _local_champion_asset(filename: str) -> str:
    """Placeholder for a locally-bundled champion asset. Unreachable while
    both override tables are empty; raises rather than importing the deleted
    Streamlit helper, so a future entry fails loudly instead of at render."""
    raise NotImplementedError(
        f"no local asset pipeline for {filename}: static/ was removed with the "
        "Streamlit app; add the file under web-next/public/ and serve it from there")


def icon_url(name: str, version: str = DDRAGON_VERSION) -> str:
    """Square face icon (PNG). ~120x120, good for circle avatars and table cells.

    Falls back to a locally-bundled icon (served from static/champions/) for
    champions DDragon doesn't host yet — see `_LOCAL_ICON_KEYS`.
    """
    wr = _WR_ICONS.get(_wr_slug(name))
    if wr:
        return wr
    key = to_ddragon_key(name)
    if key in _LOCAL_ICON_KEYS:
        return _local_champion_asset(f"{key}.png")
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
        return _local_champion_asset(_LOCAL_SPLASH_KEYS[key])
    if key in _LOCAL_ICON_KEYS:
        return _local_champion_asset(f"{key}.png")
    return f"{_CDN_BASE}/img/champion/loading/{key}_{skin_id}.jpg"
