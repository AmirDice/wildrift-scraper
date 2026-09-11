"""Fill the champion build index the draft page and the overlay read from.

WHY THIS EXISTS

Both surfaces used to serve web-next/src/data/builds.json: LLM-authored builds
written once on 2026-07-27, frozen three weeks before the precomputed pipeline
was deprecated, and five patches behind by the time anyone noticed. Jinx's
stored build opened Phantom Dancer into Guardian Angel -- 15 and 2 of 49
captured top-50 Jinx players respectively -- and never bought Magnetic Blaster,
which 39 of them do.

They now read `latest:build:<champion>` from KV instead, which every live
studio generation writes. That index fills by itself as the site is used, but
it starts sparse -- 17 of 141 champions were reachable when it was written --
and a missing entry means the overlay shows "No standard build in the bundle"
for that champion. This bootstraps the rest.

WHAT IT COSTS

One advisor call per champion: a real model call, roughly 20-60 seconds each.
141 champions is an hour or two and real API spend, so it prints a plan and
requires --write to touch anything.

WHEN TO RE-RUN

After a patch. The entries carry a 45-day TTL and a newer generation always
overwrites, so a stale entry is replaced rather than merged.

    python -m scripts.warm_build_index --champions Jinx,Nami      # try a few
    python -m scripts.warm_build_index --write                    # the roster
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import web.fight_engine as fe  # noqa: E402

#: Must match latestBuildKey in web-next/src/lib/cached-build.ts.
def latest_key(champion: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", champion.lower())
    return f"latest:build:{slug}"


#: Must match LATEST_TTL_SECONDS in the same file.
TTL = 60 * 60 * 24 * 45


def env() -> dict:
    out = dict(os.environ)
    try:
        text = (ROOT / "web-next" / ".env.local").read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        m = re.match(r'([A-Z0-9_]+)="?([^"]*)"?$', line.strip())
        if m:
            out.setdefault(m.group(1), m.group(2))
            out[m.group(1)] = m.group(2)
    return out


def kv_has(cfg: dict, key: str) -> bool:
    """Whether the index already holds this champion."""
    url, token = cfg.get("KV_REST_API_URL"), cfg.get("KV_REST_API_TOKEN")
    if not url or not token:
        return False
    req = urllib.request.Request(
        f"{url}/exists/{urllib.parse.quote(key, safe='')}",
        headers={"Authorization": f"Bearer {token}"})
    try:
        return bool(json.load(urllib.request.urlopen(req, timeout=20)).get("result"))
    except urllib.error.URLError:
        return False


def kv_set(cfg: dict, key: str, value: str) -> bool:
    """One SET with an expiry, through the Upstash REST API.

    kvSetJson stores JSON.stringify(value) as a plain string, so this writes the
    same thing: a JSON document, not a hash or a list.
    """
    url, token = cfg.get("KV_REST_API_URL"), cfg.get("KV_REST_API_TOKEN")
    if not url or not token:
        print("  KV_REST_API_URL / KV_REST_API_TOKEN missing from web-next/.env.local",
              file=sys.stderr)
        return False
    req = urllib.request.Request(
        f"{url}/set/{urllib.parse.quote(key, safe='')}?EX={TTL}",
        data=value.encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "text/plain"},
        method="POST")
    try:
        urllib.request.urlopen(req, timeout=30).read()
        return True
    except urllib.error.URLError as exc:
        print(f"  KV write failed: {exc}", file=sys.stderr)
        return False


def generate(champion: str, role: str, cfg: dict) -> dict | None:
    """One studio build from the advisor, exactly as /api/v1/build asks for it."""
    proc = subprocess.run(
        [sys.executable, "-m", "web.build_advisor", "--champion", champion,
         "--role", role],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=600, cwd=str(ROOT), env=cfg)
    if proc.returncode:
        tail = (proc.stderr or "").strip().splitlines()[-1:] or ["no stderr"]
        print(f"  advisor failed ({proc.returncode}): {tail[0][:120]}")
        return None
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print("  advisor returned unparseable output")
        return None
    if not isinstance(data, dict) or not data.get("items"):
        print(f"  advisor returned no items: {str(data)[:120]}")
        return None
    return data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--champions", default="", help="comma-separated; default is the roster")
    ap.add_argument("--write", action="store_true", help="actually call the advisor and write")
    ap.add_argument("--skip-existing", action="store_true",
                    help="leave champions that already have an index entry alone")
    args = ap.parse_args()

    cfg = env()
    names = ([c.strip() for c in args.champions.split(",") if c.strip()]
             or sorted(fe.CHAMPS))
    names = [n for n in names if n in fe.CHAMPS]

    if not args.write:
        print(f"PLAN: {len(names)} champions, one advisor call each.")
        print("Nothing is called and nothing is written without --write.")
        print(f"first few: {', '.join(names[:8])}")
        return 0

    ok = failed = skipped = 0
    started = time.time()
    for i, champ in enumerate(names, 1):
        role = fe.CHAMP_ROLE.get(champ) or ""
        if args.skip_existing and kv_has(cfg, latest_key(champ)):
            skipped += 1
            print(f"[{i}/{len(names)}] {champ}: already indexed, skipped", flush=True)
            continue
        print(f"[{i}/{len(names)}] {champ} ({role or 'no role'})", flush=True)
        data = generate(champ, role, cfg)
        if not data:
            failed += 1
            continue
        if kv_set(cfg, latest_key(champ), json.dumps(data)):
            ok += 1
            print(f"  {len(data.get('items') or [])} items -> {latest_key(champ)}")
        else:
            failed += 1
    mins = (time.time() - started) / 60
    print(f"\nwrote {ok}, failed {failed}, skipped {skipped} in {mins:.1f} min")
    return 1 if failed and not ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
