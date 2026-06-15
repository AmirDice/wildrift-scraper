"""URLs for images bundled with the app.

Streamlit Cloud's built-in static file server (`enableStaticServing`) is
unreliable on hosted deploys behind a custom domain: the `/app/static/...`
path is intercepted before it reaches Streamlit, depending on the proxy
config. To sidestep that entirely we serve assets from jsDelivr's GitHub
CDN, which fronts the same files we've committed to GitHub. Pros:
  - Works locally and on every Streamlit Cloud config
  - CDN-cached globally
  - Cache-busted via the git commit SHA so updates propagate quickly
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


# Public GitHub repo serving as the asset source.
_GH_OWNER = "AmirDice"
_GH_REPO = "wildrift-scraper"
_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def _current_ref() -> str:
    """Return a ref jsDelivr will accept: the current commit SHA when running
    from a git checkout, or the `main` branch as a fallback.

    Every failure mode (no git binary, no .git dir, sandbox blocked, slow
    subprocess, anything else) silently falls back to `main` so import of
    this module can never crash the app boot."""
    sha = os.environ.get("STREAMLIT_COMMIT_HASH") or os.environ.get("GIT_COMMIT")
    if sha:
        return sha
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_STATIC_DIR.parent,
            capture_output=True, text=True, timeout=2, check=False,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:  # noqa: BLE001 — import-time helper, must not raise
        pass
    return "main"


_REF = _current_ref()
_CDN_BASE = f"https://cdn.jsdelivr.net/gh/{_GH_OWNER}/{_GH_REPO}@{_REF}/static"


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
