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

from web.build_advisor import advise_runes, advise_best_of, why_not  # noqa: E402

# Shared secret so only our own Next.js route can spend DeepSeek credit. Without
# it this endpoint is an open, billable API.
ADVISOR_SECRET = os.environ.get("ADVISOR_SECRET", "")

# Deployed, an unset secret is not "no auth configured", it is a public endpoint
# that spends money on request. The per-IP daily cap lives in the Next route, so
# anyone calling this URL directly bypasses it completely. When Vercel is the
# host and no secret is set, refuse everything rather than serve openly.
#
# Locally there is no VERCEL variable and the site spawns the advisor as a
# subprocess instead of calling over HTTP, so this never affects development.
REQUIRE_SECRET = bool(os.environ.get("VERCEL"))

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


def _slug(value, limit: int = 60) -> str:
    if not isinstance(value, str):
        return ""
    return "".join(c for c in value if c.isalnum() or c == "-")[:limit]


def _rune(value, limit: int = 40) -> str:
    """Rune names carry colons ("Legend: Alacrity"); _clean would eat them."""
    if not isinstance(value, str):
        return ""
    return "".join(c for c in value if c.isalnum() or c in " .:'&-")[:limit].strip()


def _clean_text(value, limit: int = 160) -> str:
    """A CONDITION, not a name: "when the enemy stacks armour" is a sentence,
    so it keeps sentence punctuation and a sentence-sized budget."""
    if not isinstance(value, str):
        return ""
    # "+" and "=" survive: conditions read "2+ healers", "armour >= 100".
    kept = "".join(c for c in value if c.isalnum() or c in " .,:;'&%()/+=-")
    return " ".join(kept.split())[:limit]


def build_from_request(body: dict) -> tuple[int, dict]:
    """Validate the request and run the advisor. Returns (status, payload)."""
    champion = _clean(body.get("champion"))
    if not champion:
        return 400, {"error": "champion is required"}

    # "Why is CANDIDATE not in this build?" -- a different, deliberately small
    # call, handled before anything else. When this branch was missing the
    # unknown key was silently ignored and a why-not request fell through to a
    # FULL generation: the panel showed nothing (a build has no `answer`
    # field) and the caller paid full model time for it. Local dev never saw
    # the bug because the site spawns the CLI there instead of calling here.
    why = body.get("whyNot")
    if isinstance(why, dict):
        candidate = _slug(why.get("candidate"))
        if not candidate:
            return 400, {"error": "candidate item is required"}
        items = [s for s in (_slug(v) for v in (why.get("items") or [])[:6]) if s]
        runes = [r for r in (_rune(v) for v in (why.get("runes") or [])[:6]) if r]
        # The build's own conditional recommendations. Without these the answer
        # could argue down an item the same page already offers as a swap.
        swaps = [{"item": _slug(r.get("item")),
                  "replaces": _slug(r.get("replaces")),
                  "when": _clean_text(r.get("when"))}
                 for r in (why.get("situational") or [])[:6] if isinstance(r, dict)]
        swap_boots = [{"boots": _slug(r.get("boots")),
                       "when": _clean_text(r.get("when"))}
                      for r in (why.get("situationalBoots") or [])[:4] if isinstance(r, dict)]
        # Everything else the page knows: enemies, role, and the build's own
        # reasons and synergies, so the answer is argued from the same facts
        # the build was.
        enemies_q = [e for e in (_clean(v) for v in (why.get("enemies") or [])[:5]) if e]
        item_reasons = [{"item": _slug(r.get("item")),
                         "reason": _clean_text(r.get("reason")),
                         "synergyWith": [s for s in (_slug(v) for v in (r.get("synergyWith") or [])[:4]) if s]}
                        for r in (why.get("itemReasons") or [])[:6] if isinstance(r, dict)]
        rr = why.get("runeReasons") if isinstance(why.get("runeReasons"), dict) else {}
        rune_reasons = {"keystone": _clean_text(rr.get("keystone")),
                        "minors": [_clean_text(m) for m in (rr.get("minors") or [])[:4]],
                        "flex": _clean_text(rr.get("flex"))}
        cs = why.get("candidateScore") if isinstance(why.get("candidateScore"), dict) else None
        candidate_score = ({"score": cs.get("score"), "reason": _clean_text(cs.get("reason"))}
                           if cs else None)
        try:
            out = why_not(champion, items, _slug(why.get("boots")), runes, candidate,
                          playstyle=_clean(why.get("playstyle")) or "standard",
                          build_bias=_clean(why.get("buildBias")) or "balanced",
                          situational=[s for s in swaps if s["item"]],
                          situational_boots=[b for b in swap_boots if b["boots"]],
                          enemies=enemies_q, role=_clean(why.get("role")) or "",
                          item_reasons=[r for r in item_reasons if r["item"]],
                          rune_reasons=rune_reasons,
                          boots_reason=_clean_text(why.get("bootsReason")),
                          candidate_score=candidate_score)
        except SystemExit as exc:            # missing API key, unknown champion
            return 500, {"error": str(exc)}
        return 200, out

    mode = "counter" if _clean(body.get("mode")) == "counter" else "studio"
    enemies = _clean_list(body.get("enemies"))

    # Runes and summoners alone, for the caller that needs them before the
    # items: they are entered in champion select and cannot be changed once
    # the game starts, so they are the half of a build with a deadline.
    if _clean(body.get("only")) == "runes":
        try:
            return 200, advise_runes(
                champion=champion,
                role=_clean(body.get("role")),
                enemies=enemies,
                allies=_clean_list(body.get("allies")),
                playstyle=_clean(body.get("playstyle")) or "standard",
                objective=_clean(body.get("objective")) or "balanced",
                mode=mode,
                champion_form=_clean(body.get("championForm")),
                locked_runes=_clean_list(body.get("lockedRunes"), limit=2),
            )
        except SystemExit as exc:
            return 500, {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc(file=sys.stderr)
            return 502, {"error": f"advisor failed: {type(exc).__name__}: {exc}"}

    if mode == "counter" and not enemies:
        return 400, {"error": "at least one enemy is required for a counter build"}

    # How many times to sample the model before answering. The caller decides,
    # because only the caller knows whether this request is filling an empty
    # cache (worth several samples) or is a repeat (already answered). Clamped
    # here so a forged body cannot bill us for fifty generations.
    try:
        runs = max(1, min(5, int(body.get("runs") or 1)))
    except (TypeError, ValueError):
        runs = 1

    try:
        result = advise_best_of(
            champion=champion,
            role=_clean(body.get("role")),
            enemies=enemies,
            runs=runs,
            allies=_clean_list(body.get("allies")),
            playstyle=_clean(body.get("playstyle")) or "standard",
            objective=_clean(body.get("objective")) or "balanced",
            mode=mode,
            game_phase=_clean(body.get("gamePhase")) or "balanced",
            damage_path=_clean(body.get("damagePath")) or "standard",
            champion_form=_clean(body.get("championForm")),
            ahead_enemy=_clean(body.get("aheadEnemy")),
            risk_tolerance=_clean(body.get("riskTolerance")) or "medium",
            build_bias=_clean(body.get("buildBias")) or "balanced",
            skill_level=_clean(body.get("skillLevel")) or "average",
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
        if REQUIRE_SECRET and not ADVISOR_SECRET:
            print("ADVISOR_SECRET is not set; refusing to serve an open billable "
                  "endpoint", file=sys.stderr)
            self._send(503, {"error": "advisor is not configured"})
            return
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
            "hasApiKey": bool(advisor._api_key(advisor.KEY_NAME)),
        })
