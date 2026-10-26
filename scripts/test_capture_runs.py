"""Tests for src/capture_runs.py: resume vs new run, archiving, staleness.

    python -m pytest scripts/test_capture_runs.py -q

Runs against a temporary data directory; the real captures are never touched.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import capture_runs as cr  # noqa: E402


@pytest.fixture()
def runs(tmp_path, monkeypatch):
    monkeypatch.setattr(cr, "CAPTURES", tmp_path / "captures")
    monkeypatch.setattr(cr, "ARCHIVE", tmp_path / "archive")
    monkeypatch.setattr(cr, "ROOT", tmp_path)
    monkeypatch.setattr(cr, "roster_names", lambda: {"Aatrox", "Ahri", "Zed"})
    return tmp_path


def session(run: Path, champion: str, top: int) -> None:
    d = run / f"{champion.lower()}_20261026_0100"
    d.mkdir(parents=True)
    lines = [json.dumps({"champion": champion, "rank": r}) for r in range(1, top + 1)]
    (d / "manifest.jsonl").write_text("\n".join(lines), encoding="utf-8")


def test_first_capture_starts_a_dated_run(runs):
    run = cr.run_for_ladder("eu", 30)
    assert run.parent == runs / "captures" / "eu"
    assert run.name == datetime.now().date().isoformat()


def test_unfinished_run_is_resumed(runs):
    run = cr.run_for_ladder("eu", 30)
    session(run, "Aatrox", 30)
    session(run, "Ahri", 12)            # stopped part-way: not complete
    assert cr.run_for_ladder("eu", 30) == run
    assert cr.ladder_missing(run, 30) == ["Ahri", "Zed"]


def test_finished_run_is_archived_and_a_new_one_started(runs):
    first = cr.run_for_ladder("eu", 30)
    for c in ("Aatrox", "Ahri", "Zed"):
        session(first, c, 30)
    second = cr.run_for_ladder("eu", 30)
    assert second != first
    assert (runs / "archive" / "eu" / first.name).is_dir()
    assert not first.exists()
    assert cr.all_runs("eu") == [runs / "archive" / "eu" / first.name, second]


def test_new_run_flag_archives_an_unfinished_run(runs):
    first = cr.run_for_ladder("eu", 30)
    session(first, "Aatrox", 30)
    second = cr.run_for_ladder("eu", 30, new_run=True)
    assert second != first and (runs / "archive" / "eu" / first.name).is_dir()


def test_regions_are_separate(runs):
    eu = cr.run_for_ladder("eu", 30)
    na = cr.run_for_ladder("na", 30)
    assert eu.parent.name == "eu" and na.parent.name == "na"


def test_loadouts_resume_until_marked_complete(runs):
    run = cr.run_for_loadouts()
    assert cr.run_for_loadouts() == run
    cr.mark_run(run, complete=False, failures=["Nilah jungle: page never appeared"])
    assert cr.run_for_loadouts() == run
    cr.mark_run(run, complete=True)
    assert cr.run_for_loadouts() != run
    assert (runs / "archive" / "loadouts" / run.name).is_dir()


def test_stale_loadout_run_stops_blocking(runs):
    run = cr.run_for_loadouts()
    old = (datetime.now() - timedelta(days=cr.STALE_DAYS + 1)).isoformat(timespec="seconds")
    cr.mark_run(run, complete=False, startedAt=old)
    assert cr.run_for_loadouts() != run


def test_partners_one_run_per_day(runs, monkeypatch):
    today = cr.run_for_partners()
    assert cr.run_for_partners() == today


def test_unknown_kind_is_refused(runs):
    with pytest.raises(ValueError):
        cr.current_run("euw")
