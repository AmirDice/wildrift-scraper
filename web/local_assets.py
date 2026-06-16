"""URLs for images bundled with the app.

Streamlit Cloud's built-in static file server (`enableStaticServing`) is
unreliable on hosted deploys behind a custom domain: the `/app/static/...`
path is intercepted before it reaches Streamlit, depending on the proxy
config. To sidestep that entirely we serve assets from jsDelivr's GitHub
CDN, which fronts the same files we've committed to GitHub.

We hit jsDelivr at @main (not the commit SHA). When Streamlit Cloud just
deployed a fresh commit, that commit's assets aren't yet replicated to
all jsDelivr edge nodes, so SHA-pinned URLs can 404 for a few minutes.
@main is jsDelivr's own moving pointer to whatever's current on main —
they handle the cache invalidation for us.
"""
from __future__ import annotations

from pathlib import Path


_GH_OWNER = "AmirDice"
_GH_REPO = "wildrift-scraper"
_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
_CDN_BASE = f"https://cdn.jsdelivr.net/gh/{_GH_OWNER}/{_GH_REPO}@main/static"


def static_url(filename: str) -> str:
    """Return the CDN URL for a file in `<project-root>/static/`.

    Resolves to `https://cdn.jsdelivr.net/gh/<owner>/<repo>@<ref>/static/<file>`
    which works identically locally, on Streamlit Cloud, and behind any
    custom-domain proxy. The pinned ref means caching is automatic — a new
    commit gets a new URL.
    """
    return f"{_CDN_BASE}/{filename}"


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
