"""API keys, read from the environment or from web-next/.env.local.

Next.js loads .env.local for the web app, so anything spawned by the API route
inherits the key. A script run from a terminal inherits nothing, which meant the
generators failed with "DEEPSEEK_API_KEY is not set" while the key sat in the
repo the whole time. Both generators read through here so the two cannot drift:
the live advisor gained this fallback first and the curated one did not, and the
next run failed for exactly that reason.

The environment always wins. This is a convenience for local runs, not a
configuration source that can override a deliberate deployment setting.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE = ROOT / "web-next" / ".env.local"


def _from_file(name: str) -> str:
    if not ENV_FILE.exists():
        return ""
    for line in ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() == name:
            return value.strip().strip('"').strip("'")
    return ""


def api_key(name: str = "DEEPSEEK_API_KEY") -> str:
    """The key, from the environment first and web-next/.env.local second."""
    return os.environ.get(name, "").strip() or _from_file(name)


def missing_key_message(name: str = "DEEPSEEK_API_KEY") -> str:
    return (f"{name} is not set. Either export it in this shell, or put it in "
            f"{ENV_FILE.relative_to(ROOT).as_posix()} (where the web app reads it from).")
