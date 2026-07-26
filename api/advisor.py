"""Vercel Python function wrapping the build advisor.

Why this exists
---------------
web-next/src/app/api/build/route.ts used to `spawn()` a Python process. That
works locally and cannot work on Vercel, which was the launch blocker for the
build tools. Vercel does run Python (python3.12+) with a 300-second ceiling on
every plan, and the advisor needs 30-60 seconds, so the fix is to deploy it as a
function rather than to rewrite it in TypeScript. Rewriting would have produced
a second implementation of ~2,000 lines of build rules; this project has already
watched two implementations drift apart twice.

This file is deliberately thin. It does NOT own quota, caching, sessions or
event tracking -- those stay in the TypeScript route, which already does them
well and has the KV and cookie access to do them. All this does is turn an HTTP
request into an `advise()` call.

Deployment shape
----------------
It lives at the REPO ROOT, not inside web-next/, because the advisor reads data
files (champions_wr.json, ability_formulas.json, ...) that live at the repo root.
vercel.json therefore sets the build to run inside web-next while the deployment
root stays here, so both the Next.js app and this function see what they need.
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler
from pathlib import Path

# The advisor imports as `web.advisor.*`, so the repo root has to be importable
# regardless of where the function is invoked from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from web.build_advisor import advise  # noqa: E402

# Shared secret so only our own Next.js route can spend DeepSeek credit. Without
# it this endpoint is an open, billable API.
ADVISOR_SECRET = os.environ.get("ADVISOR_SECRET", "")

MAX_BODY_BYTES = 16_384


def _clean(value, limit: int = 40) -> str:
    """Mirror the sanitising the TS route already does, so a direct call to this
    function cannot get looser validation than a call through the route."""
    if not isinstance(value, str):
        return ""
    allowed = [c for c in value if c.isalnum() or c in " .'&-"]
    # Strip after filtering, so an input of only spaces (or only stripped
    # characters) collapses to "" and gets dropped rather than surviving as a
    # truthy blank that reaches the advisor as a champion name.
    return "".join(allowed)[:limit].strip()


def _clean_list(value, limit: int = 5) -> list[str]:
    if not isinstance(value, list):
        return []
    return [c for c in (_clean(v) for v in value) if c][:limit]


def build_from_request(body: dict) -> tuple[int, dict]:
    """Validate the request and run the advisor. Returns (status, payload)."""
    champion = _clean(body.get("champion"))
    if not champion:
        return 400, {"error": "champion is required"}

    mode = "counter" if _clean(body.get("mode")) == "counter" else "studio"
    enemies = _clean_list(body.get("enemies"))
    if mode == "counter" and not enemies:
        return 400, {"error": "at least one enemy is required for a counter build"}

    try:
        result = advise(
            champion=champion,
            role=_clean(body.get("role")),
            enemies=enemies,
            allies=_clean_list(body.get("allies")),
            playstyle=_clean(body.get("playstyle")) or "standard",
            objective=_clean(body.get("objective")) or "balanced",
            mode=mode,
            game_phase=_clean(body.get("gamePhase")) or "balanced",
            damage_path=_clean(body.get("damagePath")) or "standard",
            champion_form=_clean(body.get("championForm")),
            ahead_enemy=_clean(body.get("aheadEnemy")),
            risk_tolerance=_clean(body.get("riskTolerance")) or "medium",
            locked_items=_clean_list(body.get("lockedItems"), limit=3),
            locked_runes=_clean_list(body.get("lockedRunes"), limit=2),
        )
    except SystemExit as exc:               # missing API key, unknown champion
        return 500, {"error": str(exc)}
    except Exception as exc:                # noqa: BLE001
        # The traceback goes to the function log, never to the caller: it can
        # carry file paths and request detail.
        traceback.print_exc(file=sys.stderr)
        return 502, {"error": f"advisor failed: {type(exc).__name__}: {exc}"}

    if isinstance(result, dict) and result.get("error"):
        return 400, result
    return 200, result


class handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802  (Vercel/BaseHTTPRequestHandler contract)
        if ADVISOR_SECRET and self.headers.get("x-advisor-secret") != ADVISOR_SECRET:
            self._send(401, {"error": "unauthorized"})
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._send(400, {"error": "invalid Content-Length"})
            return
        if length > MAX_BODY_BYTES:
            self._send(413, {"error": "request body too large"})
            return

        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send(400, {"error": "invalid JSON body"})
            return
        if not isinstance(body, dict):
            self._send(400, {"error": "body must be a JSON object"})
            return

        status, payload = build_from_request(body)
        self._send(status, payload)

    def do_GET(self) -> None:  # noqa: N802
        """Health check: confirms the function booted and found its data."""
        from web import build_advisor as advisor
        self._send(200, {
            "ok": True,
            "champions": len(advisor.CHAMPS),
            "items": len(advisor.ITEMS),
            "hasApiKey": bool(advisor._api_key()),
        })
