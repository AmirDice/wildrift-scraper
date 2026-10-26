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

import argparse
import io
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# Rebound to the region's current run in main(); the log lives with the run.
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


#: The regions a batch can extract. Each one's sessions are its CURRENT run,
#: data/captures/<region>/<date>/ (src/capture_runs.py): the batch used to
#: hard-code one directory, so an NA collection sat un-extracted with the
#: runner cheerfully reporting "0 pending".
REGION_CAPTURES = ("eu", "na", "cn")


def _extract_in_process(session: Path, engine: str, extra: list[str]) -> tuple[int, str, str]:
    """Run one session's extraction inside THIS process.

    The point is the OCR models. Spawning `python -m src.extract_frames` per
    champion made every champion pay PaddleOCR's cold start -- about a minute
    each, so roughly 2.4 hours of pure model loading across a 142-champion
    batch, every time the batch was run. In-process they load once.

    What this gives up is crash isolation, which is why it was subprocesses in
    the first place. Python-level failures are caught here and the batch
    carries on; a hard native crash still takes the process down, but the
    batch skips any session that already has extracted.csv, so restarting
    resumes rather than redoing. That trade is worth 2.4 hours.
    """
    import contextlib
    from src import extract_frames

    out, err = io.StringIO(), io.StringIO()
    argv = sys.argv
    sys.argv = ["extract_frames", str(session), "--engine", engine, *extra]
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = extract_frames.main() or 0
    except SystemExit as exc:                     # argparse or an explicit exit
        code = int(exc.code or 0)
    except Exception as exc:                      # one bad session, not the batch
        code = 1
        err.write(f"{type(exc).__name__}: {exc}")
    finally:
        sys.argv = argv
    return code, out.getvalue(), err.getvalue()


def _extract_isolated(session: Path, engine: str, extra: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "src.extract_frames", str(session),
         "--engine", engine, *extra],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(ROOT))
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--region", default="eu", choices=sorted(REGION_CAPTURES),
                    help="which region's captures to extract (default: eu)")
    ap.add_argument("--engine", default="auto",
                    choices=("auto", "tesseract", "paddle", "gemini"),
                    help="OCR backend; auto uses Tesseract first and PaddleOCR only for low-confidence reads")
    ap.add_argument("--isolate", action="store_true",
                    help="run each session in its own subprocess, as this "
                         "used to. Survives a hard native crash, but every "
                         "session then pays the OCR model cold start again.")
    ap.add_argument("--no-ranks", action="store_true",
                    help="skip profile rank badges (see extract_frames --no-ranks)")
    args = ap.parse_args()
    extra = ["--no-ranks"] if args.no_ranks else []

    global CAPTURES, LOG
    from src.capture_runs import current_run
    run = current_run(args.region)
    if run is None:
        print(f"no {args.region.upper()} capture run yet under data/captures/{args.region}/")
        return 1
    CAPTURES = run
    LOG = CAPTURES / "_batch_log.txt"
    if not CAPTURES.exists():
        print(f"no capture directory for {args.region}: {CAPTURES}")
        return 1
    note(f"region: {args.region.upper()}  ({CAPTURES.relative_to(ROOT).as_posix()})")

    candidates = [d for d in sorted(CAPTURES.iterdir())
                  if d.is_dir() and (d / "manifest.jsonl").exists()
                  and not (d / "extracted.csv").exists()]
    pending, live = [], []
    for d in candidates:
        (live if _last_write(d) < STILL_WRITING_MINUTES else pending).append(d)
    for d in live:
        note(f"skipping {d.name}: written {_last_write(d):.1f} min ago, still capturing")
    note(f"batch start: {len(pending)} pending session(s), engine={args.engine}, "
         f"{'ranks SKIPPED, ' if args.no_ranks else ''}"
         f"{'isolated subprocesses' if args.isolate else 'in-process (models load once)'}")
    started = time.time()
    ok = failed = 0
    for i, session in enumerate(pending, 1):
        t0 = time.time()
        run = _extract_isolated if args.isolate else _extract_in_process
        code, stdout, stderr = run(session, args.engine, extra)
        dt = time.time() - t0
        tail = [ln for ln in stdout.splitlines() if ln.strip()]
        # The lines worth keeping: what each output file got, and the totals.
        summary = " | ".join(
            ln.strip() for ln in tail
            if ln.startswith(("extracted ", "tap-verified", "stats.csv",
                              "builds.jsonl", "players.csv")))
        fallbacks = sum(1 for ln in tail if "-> model" in ln)
        if code:
            failed += 1
            err = stderr.strip().splitlines()
            note(f"{i}/{len(pending)} {session.name}: FAILED rc={code} "
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
