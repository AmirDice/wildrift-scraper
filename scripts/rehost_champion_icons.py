"""Bring the champion head icons onto our own domain.

They are served from game.gtimg.cn, a Tencent CDN, and measured from Europe
each one takes about 1.2 seconds. That is invisible when a page shows a handful
of them. It is fatal to the PC second screen, which has to load all 141 into
memory before it can match anything: sequentially that is nearly three minutes,
and even parallelised it runs into the browser's six-connections-per-host limit
and lands around thirty seconds. The reader simply never started.

Rehosting also drops a dependency on a third party for the CORS header the
whole approach needs -- the canvas cannot read pixels from an image that does
not send one, and that header is theirs to remove.

Writes `iconLocal` alongside the existing `icon` rather than replacing it: the
Android overlay resolves `icon` as an absolute URL and a relative path would
break it, so migration is a separate decision from rehosting.

    python -m scripts.rehost_champion_icons          # only what is missing
    python -m scripts.rehost_champion_icons --force  # re-download everything
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROSTER = ROOT / "web-next" / "src" / "data" / "roster.json"
OUT_DIR = ROOT / "web-next" / "public" / "champions"
PUBLIC_PREFIX = "/champions"


def fetch(url: str, dest: Path, attempts: int = 3) -> int:
    last: Exception | None = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=30).read()
            if len(data) < 200:
                raise ValueError("suspiciously small: %d bytes" % len(data))
            dest.write_bytes(data)
            return len(data)
        except Exception as exc:                       # noqa: BLE001
            last = exc
            time.sleep(1.5 * (i + 1))
    raise RuntimeError("%s: %s" % (url, str(last)[:120]))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    roster = json.loads(ROSTER.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    jobs, skipped = [], 0
    for name, row in roster.items():
        url = row.get("icon") or ""
        slug = row.get("slug") or ""
        if not url.startswith("http") or not slug:
            continue
        ext = ".png" if ".png" in url.lower() else ".jpg"
        dest = OUT_DIR / (slug + ext)
        if dest.exists() and not args.force:
            skipped += 1
            continue
        jobs.append((name, url, dest))

    print("%d to fetch, %d already present" % (len(jobs), skipped))
    failed = []
    if jobs:
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(fetch, u, d): n for n, u, d in jobs}
            for i, fut in enumerate(as_completed(futures), 1):
                name = futures[fut]
                try:
                    fut.result()
                except Exception as exc:               # noqa: BLE001
                    failed.append(name)
                    print("  FAILED %s: %s" % (name, str(exc)[:90]))
                if i % 25 == 0:
                    print("  %d/%d" % (i, len(jobs)))
        print("fetched in %.0fs" % (time.time() - t0))

    total = 0
    for name, row in roster.items():
        slug = row.get("slug") or ""
        for ext in (".png", ".jpg"):
            if (OUT_DIR / (slug + ext)).exists():
                row["iconLocal"] = "%s/%s%s" % (PUBLIC_PREFIX, slug, ext)
                total += 1
                break
    ROSTER.write_text(json.dumps(roster, ensure_ascii=False), encoding="utf-8")
    size = sum(p.stat().st_size for p in OUT_DIR.iterdir() if p.is_file())
    print("iconLocal set on %d of %d champions (%.1f MB on disk)"
          % (total, len(roster), size / 1024 / 1024))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
