"""URLs for images bundled with the app (served by Streamlit's built-in
static file server).

Requires `.streamlit/config.toml`:
    [server]
    enableStaticServing = true

Files placed in `<project-root>/static/` are served at `app/static/<name>`.
"""
from __future__ import annotations

from pathlib import Path


_STATIC_BASE = "/app/static"
_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def static_url(filename: str) -> str:
    """Return the served URL for a file in `<project-root>/static/`.

    Uses a leading slash so the URL resolves the same way from the landing
    page `/` and from sub-pages like `/Leaderboard`.

    Appends `?v=<mtime>` as a cache-buster so swapping out an asset (e.g.
    a new logo with the same filename) actually picks up in the browser
    instead of being served from disk cache for hours.
    """
    file_path = _STATIC_DIR / filename
    version = ""
    try:
        version = f"?v={int(file_path.stat().st_mtime)}"
    except FileNotFoundError:
        pass
    return f"{_STATIC_BASE}/{filename}{version}"


# --- Named backgrounds (filenames in <project-root>/static/) -----------
LANDING_BG_FILE = "landing_bg.jpg"     # Spirit Blossom waterfall scene (landing page top)
SEASON_BG_FILE = "season_bg.jpg"       # Kai'Sa season-card background
MECHA_AATROX_FILE = "mecha_aatrox.png" # Square icon for the NEW SKIN feature block
ASHEN_SAMIRA_FILE = "ashensamira.png"  # Square icon for the NEW SKIN feature block
LOGO_FILE = "logo.png"                 # WrTrueMeta.com horizontal brand logo (transparent)
PAGE_BG_FILE = "page_bg.jpg"           # Pre-blurred ambient background for sub-pages


def landing_bg() -> str:
    return static_url(LANDING_BG_FILE)


def season_bg() -> str:
    return static_url(SEASON_BG_FILE)


def mecha_aatrox() -> str:
    return static_url(MECHA_AATROX_FILE)


def ashen_samira() -> str:
    return static_url(ASHEN_SAMIRA_FILE)


def logo() -> str:
    return static_url(LOGO_FILE)


def page_bg() -> str:
    return static_url(PAGE_BG_FILE)
