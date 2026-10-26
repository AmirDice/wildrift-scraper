"""Where captures live: one dated folder per collection run, and an archive.

    data/captures/<kind>/<YYYY-MM-DD>/<sessions>   the current run, one per kind
    data/archive/<kind>/<YYYY-MM-DD>/<sessions>    every earlier run

kind is eu, na or cn (leaderboard captures), loadouts or partners. A run is
named after the day it started and holds every session of that collection,
however many days it takes.

Why (owner, 2026-10-26): every new collection used to start with moving the
last one aside by hand (captures_loadouts/old, old2 ... old5, captures_eu/old),
and the past lived in half a dozen differently named places. Now a capture
asks for its run here and gets one of two answers:

* RESUME the current run while it is unfinished, so an interrupted overnight
  walk, or the recapture of the few champions that failed, lands in the same
  collection instead of starting a new date;
* or, once it is finished, ARCHIVE it and start a new dated run.

"Finished" is measured, never assumed. A leaderboard run is finished when
every champion on the roster reached the requested rank, which is the same
test scrape_timed --skip-existing uses to resume. A loadout run is finished
when its walk ended without failures (walk_loadouts writes _run.json), or
when it is more than STALE_DAYS old: a champion the app never loads must not
hold next week's collection hostage. --new-run on any capture forces a new
run regardless.

Readers: exports read the current run (current_run); the loadout export also
reads the archive, newest capture per champion and lane, which is how a lane
missed this week keeps last week's data (all_runs).
"""
from __future__ import annotations

import json
import shutil
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CAPTURES = DATA / "captures"
ARCHIVE = DATA / "archive"
KINDS = ("eu", "na", "cn", "loadouts", "partners")
RUN_FILE = "_run.json"
#: A loadout run this old is treated as finished even with failures left.
STALE_DAYS = 4


def _check(kind: str) -> str:
    kind = kind.lower()
    if kind not in KINDS:
        raise ValueError(f"unknown capture kind {kind!r}; expected one of {KINDS}")
    return kind


def _is_run(path: Path) -> bool:
    try:
        datetime.strptime(path.name[:10], "%Y-%m-%d")
    except ValueError:
        return False
    return path.is_dir()


def kind_dir(kind: str) -> Path:
    """data/captures/<kind>, for per-kind files that outlive a run (_no_data.json)."""
    return CAPTURES / _check(kind)


def current_run(kind: str) -> Path | None:
    """The newest run in data/captures/<kind>, or None."""
    base = kind_dir(kind)
    runs = sorted(p for p in base.iterdir() if _is_run(p)) if base.exists() else []
    return runs[-1] if runs else None


def archived_runs(kind: str) -> list[Path]:
    base = ARCHIVE / _check(kind)
    return sorted(p for p in base.iterdir() if _is_run(p)) if base.exists() else []


def all_runs(kind: str) -> list[Path]:
    """Every run of this kind, oldest first: the archive, then the current one."""
    current = current_run(kind)
    return archived_runs(kind) + ([current] if current else [])


def read_run(run: Path) -> dict:
    try:
        return json.loads((run / RUN_FILE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def mark_run(run: Path, **fields) -> None:
    """Merge fields into the run's _run.json (complete=True, notes, ...)."""
    state = read_run(run) | fields | {"updatedAt": datetime.now().isoformat(timespec="seconds")}
    (run / RUN_FILE).write_text(json.dumps(state, indent=2), encoding="utf-8")


def archive_run(run: Path) -> Path:
    """Move a finished run into data/archive/<kind>/. Same drive, so a rename."""
    kind = run.parent.name
    dest = ARCHIVE / _check(kind) / run.name
    if dest.exists():
        raise SystemExit(f"cannot archive {run}: {dest} already exists")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(run), str(dest))
    print(f"[runs] archived {kind} run {run.name} -> {dest.relative_to(ROOT)}")
    return dest


def _new_run(kind: str, today: date | None = None) -> Path:
    name = (today or date.today()).isoformat()
    # Unique across the archive too: a run that finished and was archived
    # today would otherwise share its name with the one starting now, and
    # archiving that one later would collide.
    taken = lambda n: (kind_dir(kind) / n).exists() or (ARCHIVE / kind / n).exists()  # noqa: E731
    if taken(name):
        i = 2
        while taken(f"{name}-{i}"):
            i += 1
        name = f"{name}-{i}"
    run = kind_dir(kind) / name
    run.mkdir(parents=True)
    mark_run(run, kind=kind, startedAt=datetime.now().isoformat(timespec="seconds"), complete=False)
    print(f"[runs] new {kind} run: {run.relative_to(ROOT)}")
    return run


# ---------------------------------------------------------------- leaderboard

def roster_names() -> set[str]:
    """Champion names a complete leaderboard collection covers (roster.json)."""
    path = ROOT / "web-next" / "src" / "data" / "roster.json"
    try:
        roster = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    if isinstance(roster, dict):
        return {str(v.get("name", k)) if isinstance(v, dict) else str(k) for k, v in roster.items()}
    return {str(c.get("name")) for c in roster if isinstance(c, dict) and c.get("name")}


def ladder_completed(run: Path, n: int) -> set[str]:
    """Champions whose capture in this run reached rank n (scrape_timed's test)."""
    found: set[str] = set()
    for manifest in run.glob("*/manifest.jsonl"):
        lines = [ln for ln in manifest.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if not lines:
            continue
        try:
            champion = json.loads(lines[0]).get("champion")
            top = max(int(json.loads(ln)["rank"]) for ln in lines)
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
        if champion and top >= n:
            found.add(champion)
    return found


def ladder_missing(run: Path, n: int) -> list[str]:
    if read_run(run).get("complete"):
        return []
    return sorted(roster_names() - ladder_completed(run, n))


def run_for_ladder(region: str, n: int, new_run: bool = False) -> Path:
    """The run a leaderboard capture of this region writes into."""
    kind = _check(region)
    run = current_run(kind)
    if run is None:
        return _new_run(kind)
    missing = ladder_missing(run, n)
    if new_run:
        if missing:
            print(f"[runs] --new-run: {kind} run {run.name} is archived with {len(missing)} champion(s) missing")
    elif missing:
        preview = ", ".join(missing[:8]) + (" ..." if len(missing) > 8 else "")
        print(f"[runs] resuming {kind} run {run.name}: {len(missing)} champion(s) still to capture ({preview})")
        return run
    archive_run(run)
    return _new_run(kind)


# ------------------------------------------------------------------- loadouts

def _age_days(run: Path) -> float:
    started = read_run(run).get("startedAt")
    try:
        when = datetime.fromisoformat(started) if started else datetime.strptime(run.name[:10], "%Y-%m-%d")
    except ValueError:
        return 0.0
    return (datetime.now() - when).total_seconds() / 86400


def run_for_loadouts(new_run: bool = False) -> Path:
    """The run a loadout walk writes into: resume until it finished cleanly."""
    run = current_run("loadouts")
    if run is None:
        return _new_run("loadouts")
    state = read_run(run)
    if not new_run and not state.get("complete") and _age_days(run) <= STALE_DAYS:
        print(f"[runs] resuming loadouts run {run.name} (unfinished; --new-run starts a fresh one)")
        return run
    if not state.get("complete") and not new_run:
        print(f"[runs] loadouts run {run.name} is over {STALE_DAYS} days old; treating it as finished")
    archive_run(run)
    return _new_run("loadouts")


# ------------------------------------------------------------------- partners

def run_for_partners() -> Path:
    """Partners are captured in one sitting: one run per day, earlier days archived."""
    run = current_run("partners")
    today = date.today().isoformat()
    if run is not None and run.name.startswith(today):
        return run
    if run is not None:
        archive_run(run)
    return _new_run("partners")


def status() -> str:
    """One line per kind, for `python -m src.capture_runs`."""
    lines = []
    for kind in KINDS:
        run = current_run(kind)
        archived = len(archived_runs(kind))
        if run is None:
            lines.append(f"{kind:9s} no current run ({archived} archived)")
            continue
        state = read_run(run)
        sessions = sum(1 for p in run.iterdir() if p.is_dir())
        lines.append(f"{kind:9s} {run.name}  {sessions} sessions  complete={bool(state.get('complete'))}  ({archived} archived)")
    return "\n".join(lines)


if __name__ == "__main__":
    print(status())
