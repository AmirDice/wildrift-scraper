"""Extract every pending capture session, OCR-first, one champion at a time.

Sequential on purpose: each session already parallelises its own frames, and
running sessions concurrently would fight over the tesseract binary and the
model's rate limit at the same time.

Restartable. A session that already has extracted.csv is skipped, so if this
dies at champion 60 the next run picks up at 61. Per-session results append to
data/captures/_batch_log.txt as they finish, so progress survives a crash and
can be read while the batch is still going.
"""
from __future__ import annotations

import io
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
CAPTURES = ROOT / "data" / "captures"
LOG = CAPTURES / "_batch_log.txt"


def note(line: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    text = f"[{stamp}] {line}"
    print(text, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(text + "\n")


#: A session whose frames were touched more recently than this is assumed to be
#: mid-capture. Extracting one produces a partial extracted.csv AND marks it
#: done, so the missing ranks are never revisited -- the batch would quietly
#: bake in a half-scraped champion. Capturing and extracting run side by side
#: here, so this is the normal case, not an edge case.
STILL_WRITING_MINUTES = 5.0


def _last_write(session: Path) -> float:
    """Minutes since anything in this session was written."""
    newest = max((f.stat().st_mtime for f in session.glob("*")), default=0.0)
    return (time.time() - newest) / 60.0 if newest else 1e9


def main() -> int:
    candidates = [d for d in sorted(CAPTURES.iterdir())
                  if d.is_dir() and (d / "manifest.jsonl").exists()
                  and not (d / "extracted.csv").exists()]
    pending, live = [], []
    for d in candidates:
        (live if _last_write(d) < STILL_WRITING_MINUTES else pending).append(d)
    for d in live:
        note(f"skipping {d.name}: written {_last_write(d):.1f} min ago, still capturing")
    note(f"batch start: {len(pending)} pending session(s), engine=tesseract")
    started = time.time()
    ok = failed = 0
    for i, session in enumerate(pending, 1):
        t0 = time.time()
        proc = subprocess.run(
            [sys.executable, "-m", "src.extract_frames", str(session),
             "--engine", "tesseract"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(ROOT))
        dt = time.time() - t0
        tail = [ln for ln in (proc.stdout or "").splitlines() if ln.strip()]
        # The lines worth keeping: what each output file got, and the totals.
        summary = " | ".join(
            ln.strip() for ln in tail
            if ln.startswith(("extracted ", "tap-verified", "stats.csv",
                              "builds.jsonl", "players.csv")))
        fallbacks = sum(1 for ln in tail if "-> model" in ln)
        if proc.returncode:
            failed += 1
            err = (proc.stderr or "").strip().splitlines()
            note(f"{i}/{len(pending)} {session.name}: FAILED rc={proc.returncode} "
                 f"{err[-1][:160] if err else ''}")
        else:
            ok += 1
            note(f"{i}/{len(pending)} {session.name}: {dt:.0f}s  "
                 f"model-fallbacks={fallbacks}  {summary}")
    note(f"batch done: {ok} ok, {failed} failed, "
         f"{(time.time() - started) / 3600:.1f}h total")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
