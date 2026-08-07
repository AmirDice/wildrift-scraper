"""The local half of the admin Operations panel.

The site runs on Vercel; the pipeline (phone scraping over ADB, frame
extraction, exports, git publish, advisor deploys) can only run HERE, on the
machine with the phone and the repo. This runner closes that gap through the
KV store both sides already share: the admin page enqueues a job, this process
picks it up, runs the corresponding WHITELISTED command, and streams the log
tail back so the page can show it live.

Nothing arbitrary crosses the wire. A job is an op NAME plus narrowly
validated arguments; the mapping from name to command line lives only in this
file, and both the API route and this runner validate independently. Someone
with the admin token can run the pipeline, not shell commands.

KV contract (all under ops:):
    ops:queue    RPUSH by the site, LPOP here -- FIFO job list (JSON per entry)
    ops:current  JSON of the running/last job incl. the last ~80 log lines
    ops:stop     "1" -> kill the current job's process tree, then clear
    ops:runner   heartbeat JSON, 15s TTL -- absence means this process is down
    ops:history  LPUSH-capped list of finished jobs

Run it in a spare terminal and leave it:
    python -m scripts.ops_runner
    python -m scripts.ops_runner --once   # drain the queue, then exit (testing)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
ENV_LOCAL = ROOT / "web-next" / ".env.local"
CAPTURES = ROOT / "data" / "captures"

HEARTBEAT_EVERY = 4.0     # seconds; TTL is 15, so 3 missed beats = offline
PUSH_STATE_EVERY = 2.0    # log-tail update cadence while a job runs
LOG_TAIL = 80             # lines kept in ops:current

# ---------------------------------------------------------------------------
# environment: the same .env.local the site uses locally
# ---------------------------------------------------------------------------

def _load_env_local() -> dict[str, str]:
    out: dict[str, str] = {}
    if not ENV_LOCAL.exists():
        return out
    for line in ENV_LOCAL.read_text(encoding="utf-8").splitlines():
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

# ---------------------------------------------------------------------------
# Upstash REST: one command per request, ["CMD", arg, ...]
# ---------------------------------------------------------------------------

def kv(*command: str) -> object:
    r = requests.post(KV_URL, json=list(command),
                      headers={"Authorization": f"Bearer {KV_TOKEN}"}, timeout=15)
    r.raise_for_status()
    return r.json().get("result")


def kv_safe(*command: str) -> object:
    """A KV hiccup must not kill the runner or the child it supervises."""
    try:
        return kv(*command)
    except Exception as error:  # noqa: BLE001
        print(f"  [kv] {error}", file=sys.stderr)
        return None

# ---------------------------------------------------------------------------
# the whitelist: op name -> command sequence
# ---------------------------------------------------------------------------

PY = sys.executable or "python"
_ONLY_OK = re.compile(r"^[A-Za-z'&.\- ,]{0,400}$")


def _plan_scrape(args: dict) -> list[list[str]]:
    cmd = [PY, "-m", "src.scrape_timed", "--capture-only", "--auto-scroll",
           "--unattended", "--auto-extract", "--champions", "141"]
    only = str(args.get("only") or "").strip()
    if only:
        if not _ONLY_OK.match(only):
            raise ValueError("champion list contains characters that are not names")
        cmd += ["--only", only]
    if args.get("skipExisting", not only):
        cmd += ["--skip-existing"]
    return [cmd]


def _plan_extract_pending(args: dict) -> list[list[str]]:
    pending = []
    if CAPTURES.exists():
        for session in sorted(CAPTURES.iterdir()):
            if not session.is_dir():
                continue
            has_manifest = any(session.glob("manifest*.json"))
            if has_manifest and not (session / "extracted.csv").exists():
                pending.append(session)
    if not pending:
        return [["cmd", "/c", "echo no pending capture sessions - nothing to extract"]]
    return [[PY, "-m", "src.extract_frames", str(p)] for p in pending]


def _plan_refresh(args: dict) -> list[list[str]]:
    plan = [[PY, "-m", "scripts.export_captures"]]
    if args.get("fresh"):
        plan[0].append("--fresh")
    plan += [
        [PY, "-m", "scripts.export_json"],
        [PY, "-m", "scripts.build_ladder_pulse"],
        [PY, "-m", "scripts.export_champion_details"],
        [PY, "-m", "scripts.export_engine_data"],
    ]
    return plan


# Publishing commits ONLY generated data outputs, never code. The paths are a
# fixed allowlist so a stray edit elsewhere in the tree cannot ride along.
PUBLISH_PATHS = ["data", "web-next/src/data", "web-next/public/players"]
# Owner-triggered automation, so no Claude co-author trailer on these commits.
PUBLISH_MESSAGE = "Data refresh via admin ops"


def _plan_publish(args: dict) -> list[list[str]]:
    return [
        ["git", "add", "--", *PUBLISH_PATHS],
        # --allow-empty-message is NOT used; commit fails cleanly when nothing
        # is staged and the sequence stops there, which is the right outcome.
        ["git", "commit", "-m", PUBLISH_MESSAGE],
        # The CN collector pushes on its own schedule, so pull --rebase first.
        ["git", "pull", "--rebase", "--autostash", "origin", "main"],
        ["git", "push", "origin", "main"],
    ]


OPS: dict[str, dict] = {
    "scrape": {
        "label": "Scrape leaderboards",
        "plan": _plan_scrape,
        "note": "phone must be connected with the game on the champion tab",
    },
    "extract-pending": {
        "label": "Extract pending captures",
        "plan": _plan_extract_pending,
    },
    "refresh-data": {
        "label": "Refresh site data",
        "plan": _plan_refresh,
    },
    "fetch-patches": {
        "label": "Fetch official patch notes",
        "plan": lambda args: [["node", str(ROOT / "scripts" / "fetch_riot_patch_history.mjs")]],
    },
    "publish": {
        "label": "Publish data to the site",
        "plan": _plan_publish,
    },
    "deploy-advisor": {
        "label": "Redeploy the build advisor",
        "plan": lambda args: [[PY, str(ROOT / "scripts" / "deploy_advisor.py"), "--deploy"]],
    },
}

# ---------------------------------------------------------------------------
# job execution
# ---------------------------------------------------------------------------

def _child_env() -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    for key in ("GEMINI_API_KEY", "DEEPSEEK_API_KEY"):
        if not env.get(key) and _ENV.get(key):
            env[key] = _ENV[key]
    return env


def _kill_tree(process: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)],
                       capture_output=True)
    else:
        process.terminate()


class Job:
    def __init__(self, record: dict):
        self.record = record
        self.id = record.get("id") or uuid.uuid4().hex[:10]
        self.op = str(record.get("op") or "")
        self.args = record.get("args") or {}
        self.lines: deque[str] = deque(maxlen=LOG_TAIL)
        self.status = "running"
        self.started = time.time()
        self.finished: float | None = None
        self.exit_code: int | None = None

    def state(self) -> dict:
        return {
            "id": self.id, "op": self.op, "args": self.args,
            "label": OPS.get(self.op, {}).get("label", self.op),
            "status": self.status,
            "startedAt": self.started, "finishedAt": self.finished,
            "exitCode": self.exit_code,
            "lines": list(self.lines),
        }


def push_state(job: Job) -> None:
    kv_safe("SET", "ops:current", json.dumps(job.state()))


def run_job(job: Job) -> None:
    try:
        plan = OPS[job.op]["plan"](job.args)
    except Exception as error:  # noqa: BLE001 — bad args must not kill the runner
        job.lines.append(f"rejected: {error}")
        job.status = "failed"
        job.finished = time.time()
        push_state(job)
        return

    stopped = False
    for index, cmd in enumerate(plan, start=1):
        job.lines.append(f"$ {' '.join(cmd)}  [{index}/{len(plan)}]")
        push_state(job)
        process = subprocess.Popen(
            cmd, cwd=ROOT, env=_child_env(),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
        )

        def _pump() -> None:
            for line in process.stdout or []:
                job.lines.append(line.rstrip()[:400])

        reader = threading.Thread(target=_pump, daemon=True)
        reader.start()

        last_push = 0.0
        last_beat = 0.0
        while process.poll() is None:
            time.sleep(0.5)
            now = time.time()
            if now - last_push >= PUSH_STATE_EVERY:
                push_state(job)
                last_push = now
            if now - last_beat >= HEARTBEAT_EVERY:
                heartbeat(job)
                last_beat = now
            if kv_safe("GET", "ops:stop") == "1":
                job.lines.append("stop requested -- killing the process tree")
                _kill_tree(process)
                kv_safe("DEL", "ops:stop")
                stopped = True
        reader.join(timeout=5)
        job.exit_code = process.returncode

        if stopped:
            job.status = "stopped"
            break
        if process.returncode != 0:
            job.lines.append(f"exit code {process.returncode} -- aborting the sequence")
            job.status = "failed"
            break
    else:
        job.status = "done"

    job.finished = time.time()
    push_state(job)
    summary = job.state()
    summary.pop("lines", None)
    kv_safe("LPUSH", "ops:history", json.dumps(summary))
    kv_safe("LTRIM", "ops:history", "0", "29")


def heartbeat(job: Job | None) -> None:
    kv_safe("SET", "ops:runner", json.dumps({
        "at": time.time(),
        "host": os.environ.get("COMPUTERNAME") or "local",
        "job": {"id": job.id, "op": job.op} if job else None,
    }), "EX", "15")

# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true",
                        help="drain the queue, then exit (for testing)")
    args = parser.parse_args()

    if not KV_URL or not KV_TOKEN:
        raise SystemExit("error: KV_REST_API_URL / KV_REST_API_TOKEN not found "
                         "(web-next/.env.local or the environment)")

    print(f"ops runner up | repo {ROOT} | ops: {', '.join(OPS)}")
    # A stop flag left over from a previous run must not kill the next job.
    kv_safe("DEL", "ops:stop")

    idle_beat = 0.0
    while True:
        now = time.time()
        if now - idle_beat >= HEARTBEAT_EVERY:
            heartbeat(None)
            idle_beat = now

        raw = kv_safe("LPOP", "ops:queue")
        if raw is None:
            if args.once:
                print("queue empty -- exiting (--once)")
                return 0
            time.sleep(2)
            continue

        try:
            record = json.loads(str(raw))
        except json.JSONDecodeError:
            print(f"dropping unparseable job: {raw!r}", file=sys.stderr)
            continue
        if record.get("op") not in OPS:
            print(f"dropping unknown op: {record.get('op')!r}", file=sys.stderr)
            continue

        job = Job(record)
        print(f"job {job.id}: {job.op} {job.args or ''}")
        heartbeat(job)
        run_job(job)
        print(f"job {job.id}: {job.status}"
              + (f" (exit {job.exit_code})" if job.exit_code else ""))


if __name__ == "__main__":
    raise SystemExit(main())
