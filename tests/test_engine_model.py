"""Run the TypeScript engine's behavioural checks as part of the normal suite.

WHY A WRAPPER RATHER THAN A TS TEST RUNNER

    web-next has no test runner and adding one for a single file is a
    dependency the repo does not otherwise need. scripts/engine_parity.py
    already drives a TS script from Python for exactly this reason, so this
    follows it: `pytest tests/` runs everything, including the half of the
    engine that only exists in TypeScript.

WHAT IT GUARDS

    engine_parity covers what BOTH engines do, and covers it well. It cannot
    touch duel(), mutualDuel(), championTarget(), kitSustain(), supportValue()
    or the crowd-control and enemy model, because none of them has a Python
    twin to diff against. Those were verified by hand once and then had nothing
    holding them in place. web-next/scripts/engine_model_check.ts is that
    something; this makes it run.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web-next"
CHECK = WEB / "scripts" / "engine_model_check.ts"


@pytest.mark.skipif(not CHECK.exists(), reason="engine_model_check.ts is absent")
@pytest.mark.skipif(shutil.which("npx") is None, reason="npx is not on PATH")
@pytest.mark.skipif(not (WEB / "node_modules").is_dir(),
                    reason="web-next dependencies are not installed")
def test_engine_model_behaviour():
    """The TS-only engine model behaves the way it was built to behave."""
    # NO shell=True. With a LIST of arguments its behaviour is platform
    # specific: Windows joins the list, so this worked on the dev machine for
    # months, while POSIX runs only the first element and passes the rest as
    # $0, $1 -- so CI executed a bare `npx`, which prints usage and exits 0.
    # The test then saw returncode 0 with empty stdout and failed on every
    # push since 2026-09-10. shutil.which resolves npx.cmd on Windows, so
    # dropping the shell costs nothing there.
    result = subprocess.run(
        [shutil.which("npx"), "tsx", "scripts/engine_model_check.ts"],
        cwd=WEB, capture_output=True, text=True, timeout=600,
    )
    output = f"{result.stdout}\n{result.stderr}".strip()
    # The script prints one FAIL line per broken behaviour and exits non-zero,
    # so the whole readout is the failure message worth seeing.
    assert result.returncode == 0, f"engine model checks failed:\n{output}"
    assert "checks passed" in result.stdout, output
