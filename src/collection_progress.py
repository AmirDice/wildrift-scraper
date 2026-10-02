"""Publish how far a collection run has got, so the site can show it live.

The site is on Vercel and the scrape runs here, on the machine with the phone,
so the two halves talk through the KV store they already share (the same
channel the admin Operations panel uses). This module writes one key:

    collection:progress   {"regions": {"EU": {...}, "NA": {...}, "CN": {...}},
                           "updatedAt": "<iso>"}

Each region carries `status` ("running" or "complete"), `done`, `total`,
`startedAt` and `completedAt`. web-next/src/lib/collection.ts reads it and
falls back to the collection dates baked into the data files whenever a
region is absent, so a partial write never blanks out the other two.

EVERY failure here is swallowed. A scrape is a multi-hour unattended run on a
phone; losing it because a progress ping timed out would be absurd, and the
bar degrading to the baked date is a non-event. Nothing in this module is
allowed to raise.

The .env.local loading mirrors scripts/ops_runner.py rather than importing it:
`src` is the package and `scripts` depends on it, so the dependency cannot run
the other way. If a third caller appears it is worth hoisting properly.
"""
from __future__ import annotations

import json
import os
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_LOCAL = ROOT / "web-next" / ".env.local"
KEY = "collection:progress"
REGIONS = ("EU", "NA", "CN")
#: Don't hammer KV from a per-champion loop.
MIN_INTERVAL_SEC = 5.0


def _load_env_local() -> dict[str, str]:
    out: dict[str, str] = {}
    if not ENV_LOCAL.exists():
        return out
    try:
        lines = ENV_LOCAL.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


_ENV = _load_env_local()


def _cred(name: str) -> str:
    return os.environ.get(name) or _ENV.get(name) or ""


KV_URL = _cred("KV_REST_API_URL") or _cred("UPSTASH_REDIS_REST_URL")
KV_TOKEN = _cred("KV_REST_API_TOKEN") or _cred("UPSTASH_REDIS_REST_TOKEN")
ENABLED = bool(KV_URL and KV_TOKEN)

_session = None
_last_push = 0.0


def _kv(*command: str):
    """One Upstash REST command. Returns None on any problem."""
    global _session
    if not ENABLED:
        return None
    try:
        import requests
        if _session is None:
            _session = requests.Session()
        r = _session.post(KV_URL, json=list(command),
                          headers={"Authorization": f"Bearer {KV_TOKEN}"},
                          timeout=10)
        r.raise_for_status()
        return r.json().get("result")
    except Exception:            # noqa: BLE001 -- never break a scrape
        _session = None          # a poisoned session should not persist
        return None


def _read() -> dict:
    raw = _kv("GET", KEY)
    if not isinstance(raw, str):
        return {"regions": {}}
    try:
        doc = json.loads(raw)
    except (TypeError, ValueError):
        return {"regions": {}}
    if not isinstance(doc, dict) or not isinstance(doc.get("regions"), dict):
        return {"regions": {}}
    return doc


def _write(region: str, entry: dict) -> bool:
    """Read-modify-write so one region never clobbers the other two."""
    if region not in REGIONS:
        return False
    doc = _read()
    doc.setdefault("regions", {})[region] = entry
    doc["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return _kv("SET", KEY, json.dumps(doc)) is not None


def start(region: str, total: int) -> bool:
    """A run has begun: reset to 0 and clear the previous completion.

    Clearing completedAt is what makes the bar 'start again' rather than
    sitting at 'Completed' while a new run is already underway.
    """
    global _last_push
    _last_push = time.time()
    return _write(region, {
        "status": "running", "done": 0, "total": max(int(total or 0), 1),
        "startedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "completedAt": None,
    })


def advance(region: str, done: int, total: int, force: bool = False) -> bool:
    """One more champion finished. Throttled unless `force`."""
    global _last_push
    now = time.time()
    if not force and now - _last_push < MIN_INTERVAL_SEC:
        return False
    _last_push = now
    total = max(int(total or 0), 1)
    return _write(region, {
        "status": "running",
        "done": max(0, min(int(done or 0), total)),
        "total": total,
        "startedAt": _read().get("regions", {}).get(region, {}).get("startedAt"),
        "completedAt": None,
    })


def finish(region: str, total: int, collected_on: str | None = None) -> bool:
    """The run is done. The site shows 'Completed <date>' from here."""
    global _last_push
    _last_push = 0.0
    total = max(int(total or 0), 1)
    return _write(region, {
        "status": "complete", "done": total, "total": total,
        "startedAt": None,
        "completedAt": collected_on or date.today().isoformat(),
    })


def resolve_region(explicit: str | None = None) -> str | None:
    """Which server this run is collecting, or None if nobody said.

    There is no region flag on the device and no way to read it off the game,
    so this is declared rather than detected: --region on the command line, or
    WRTM_REGION in the environment. None means "do not publish", which is the
    right default: a run mislabelled EU would overwrite EU's real progress
    with another server's.
    """
    value = (explicit or os.environ.get("WRTM_REGION") or "").strip().upper()
    return value if value in REGIONS else None
