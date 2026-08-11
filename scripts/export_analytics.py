"""
Export every product analytics counter to a multi-sheet .xlsx.

The admin page answers "how are we doing today". This answers "show me the
whole history in something I can sort, chart and keep", which the admin page
deliberately does not try to be.

Run:
    python scripts/export_analytics.py                    # last 90 days
    python scripts/export_analytics.py --days 30
    python scripts/export_analytics.py --out reports/aug.xlsx

Reads production KV over the Upstash REST API using the READ-ONLY token, so
this script cannot alter a single counter no matter what goes wrong in it.

PRIVACY: the identity sets (gen:users, cohort:*, actor:*) hold Google subs and
hashed IPs. This exporter only ever asks for their CARDINALITY. It never calls
SMEMBERS, and it skips the per-identity gen:first:* keys entirely, so no
identifier of any kind reaches the spreadsheet.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / "web-next" / ".env.local"

# Mirrors TRACKED_EVENTS in web-next/src/lib/stats.ts. If that list grows and
# this one does not, the --audit sheet still catches the new key, so a stale
# copy here degrades to "less tidy", never to "silently missing".
TRACKED_EVENTS = [
    "build_generated", "build_saved", "build_shared", "build_liked",
    "build_feedback", "counter_generated", "tour_started", "tour_completed",
    "tour_skipped", "signed_in", "nudge_shown", "nudge_clicked",
    "nudge_dismissed", "custom_opened", "custom_edited",
    "limit_reached_anon", "limit_reached_signed_in",
]

DEPTH_CAP = 6
ACTOR_ACTIONS = ["saved", "shared"]

# Key families that name an identity in the key itself. Never exported.
IDENTITY_BEARING = ("gen:first:", "quota:build:")


def load_env() -> tuple[str, str]:
    if not ENV_FILE.exists():
        sys.exit(f"missing {ENV_FILE}; run this from the repo with web-next/.env.local in place")
    env: dict[str, str] = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    url = env.get("KV_REST_API_URL")
    # Prefer the read-only token: an export must not be able to write.
    token = env.get("KV_REST_API_READ_ONLY_TOKEN") or env.get("KV_REST_API_TOKEN")
    if not url or not token:
        sys.exit("KV_REST_API_URL / KV_REST_API_READ_ONLY_TOKEN not found in web-next/.env.local")
    return url.rstrip("/"), token


class Kv:
    """Thin Upstash REST client that batches through the pipeline endpoint."""

    def __init__(self, url: str, token: str) -> None:
        self.url = url
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"

    def pipeline(self, commands: list[list], chunk: int = 500) -> list:
        out: list = []
        for start in range(0, len(commands), chunk):
            batch = commands[start:start + chunk]
            resp = self.session.post(f"{self.url}/pipeline", json=batch, timeout=60)
            resp.raise_for_status()
            for entry in resp.json():
                if "error" in entry:
                    out.append(None)
                else:
                    out.append(entry.get("result"))
        return out

    def scan(self, match: str, count: int = 1000) -> list[str]:
        keys: list[str] = []
        cursor = "0"
        while True:
            resp = self.session.post(
                self.url, json=["SCAN", cursor, "MATCH", match, "COUNT", count], timeout=60
            )
            resp.raise_for_status()
            cursor, found = resp.json()["result"]
            keys.extend(found)
            if cursor == "0":
                break
        return sorted(set(keys))


def as_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def day_keys(days: int) -> list[str]:
    """UTC day strings, oldest first, matching dayKey() in lib/kv.ts."""
    today = datetime.now(timezone.utc).date()
    return [(today - timedelta(days=n)).isoformat() for n in range(days - 1, -1, -1)]


def iso_week(d: date) -> str:
    """Matches weekKey() in lib/stats.ts (ISO week, Monday start)."""
    year, week, _ = d.isocalendar()
    return f"{year}-W{week:02d}"


def week_keys(weeks: int) -> list[str]:
    today = datetime.now(timezone.utc).date()
    seen: list[str] = []
    for n in range(weeks - 1, -1, -1):
        key = iso_week(today - timedelta(weeks=n))
        if key not in seen:
            seen.append(key)
    return seen


def build_frames(kv: Kv, days: int, weeks: int) -> dict[str, pd.DataFrame]:
    dates = day_keys(days)
    wks = week_keys(weeks)
    frames: dict[str, pd.DataFrame] = {}

    # ── events: lifetime totals + one row per day ────────────────────────────
    totals = kv.pipeline([["GET", f"stat:{e}:total"] for e in TRACKED_EVENTS])
    daily = kv.pipeline(
        [["GET", f"stat:{e}:day:{d}"] for e in TRACKED_EVENTS for d in dates]
    )
    frames["Event totals"] = pd.DataFrame(
        {"event": TRACKED_EVENTS, "lifetime": [as_int(v) for v in totals]}
    ).sort_values("lifetime", ascending=False)

    per_event = {
        event: [as_int(v) for v in daily[i * len(dates):(i + 1) * len(dates)]]
        for i, event in enumerate(TRACKED_EVENTS)
    }
    events_daily = pd.DataFrame({"date": dates, **per_event})
    frames["Events daily"] = events_daily

    # ── engagement: people, new vs returning, allowance depth ────────────────
    eng_cmds: list[list] = []
    for d in dates:
        eng_cmds.append(["SCARD", f"gen:users:{d}"])
        eng_cmds.append(["GET", f"stat:gen_new:day:{d}"])
        eng_cmds.append(["GET", f"stat:gen_returning:day:{d}"])
        for n in range(1, DEPTH_CAP + 1):
            eng_cmds.append(["GET", f"stat:gen_depth:{d}:{n}"])
    stride = 3 + DEPTH_CAP
    raw = kv.pipeline(eng_cmds)

    rows = []
    for i, d in enumerate(dates):
        chunk = raw[i * stride:(i + 1) * stride]
        unique = as_int(chunk[0])
        new_users = as_int(chunk[1])
        returning = as_int(chunk[2])
        depth = [as_int(v) for v in chunk[3:]]
        generations = per_event["build_generated"][i] + per_event["counter_generated"][i]
        row = {
            "date": d,
            "generators": unique,
            "new": new_users,
            "returning": returning,
            # Set count minus the two counters. Should be 0. It is not, because
            # engagement recording is fire-and-forget and the serverless
            # instance can be frozen after the response, losing the counter
            # write after the set write landed. Surfaced as a column so the
            # gap is visible rather than mysterious.
            "unattributed": unique - (new_users + returning),
            "generations": generations,
            "per_generator": round(generations / unique, 2) if unique else 0,
        }
        for n in range(1, DEPTH_CAP + 1):
            row[f"reached_{n}" if n < DEPTH_CAP else f"reached_{n}_plus"] = depth[n - 1]
        rows.append(row)
    frames["Engagement"] = pd.DataFrame(rows)

    # ── weekly retention cohorts ─────────────────────────────────────────────
    cohort_raw = kv.pipeline(
        [["SCARD", f"cohort:{w}:{b}"] for w in wks for b in ("new", "d1", "d7", "d30")]
    )
    cohort_rows = []
    for i, w in enumerate(wks):
        size, d1, d7, d30 = (as_int(v) for v in cohort_raw[i * 4:(i + 1) * 4])
        pct = lambda v: round(100 * v / size, 1) if size else 0  # noqa: E731
        cohort_rows.append({
            "cohort_week": w, "new_generators": size,
            "d1": d1, "d7": d7, "d30": d30,
            "d1_%": pct(d1), "d7_%": pct(d7), "d30_%": pct(d30),
        })
    frames["Cohorts"] = pd.DataFrame(cohort_rows)

    # ── savers and sharers, as people ────────────────────────────────────────
    actor_daily = kv.pipeline(
        [["SCARD", f"actor:{a}:day:{d}"] for a in ACTOR_ACTIONS for d in dates]
    )
    actor_all = kv.pipeline([["SCARD", f"actor:{a}:all"] for a in ACTOR_ACTIONS])
    actor_cols = {
        f"{a}_people": [as_int(v) for v in actor_daily[i * len(dates):(i + 1) * len(dates)]]
        for i, a in enumerate(ACTOR_ACTIONS)
    }
    actors = pd.DataFrame({"date": dates, **actor_cols})
    actors["save_actions"] = per_event["build_saved"]
    actors["share_actions"] = per_event["build_shared"]
    frames["Savers and sharers"] = actors

    # ── feedback: verdicts, reasons, and the note log ────────────────────────
    verdicts = kv.pipeline([["GET", "feedback:build:up"], ["GET", "feedback:build:down"]])
    reason_keys = kv.scan("feedback:build:reason:*")
    reason_vals = kv.pipeline([["GET", k] for k in reason_keys]) if reason_keys else []
    fb_rows = [
        {"metric": "thumbs up", "count": as_int(verdicts[0])},
        {"metric": "thumbs down", "count": as_int(verdicts[1])},
    ] + [
        {"metric": f"reason: {k.rsplit(':', 1)[-1]}", "count": as_int(v)}
        for k, v in zip(reason_keys, reason_vals)
    ]
    frames["Feedback summary"] = pd.DataFrame(fb_rows)

    log_raw = kv.pipeline([["LRANGE", "feedback:build:log", 0, -1]])
    entries = []
    for item in (log_raw[0] or []):
        try:
            entries.append(json.loads(item) if isinstance(item, str) else item)
        except json.JSONDecodeError:
            continue
    if entries:
        log = pd.DataFrame(entries)
        if "reasons" in log.columns:
            log["reasons"] = log["reasons"].apply(
                lambda v: ", ".join(v) if isinstance(v, list) else v
            )
        frames["Feedback log"] = log
    else:
        frames["Feedback log"] = pd.DataFrame(columns=["at", "verdict", "champion", "reasons", "note"])

    # ── audit: every analytics key, so a new counter is never invisible ──────
    audit_keys: list[str] = []
    for pattern in ("stat:*", "gen:*", "cohort:*", "actor:*", "feedback:*"):
        audit_keys.extend(kv.scan(pattern))
    audit_keys = sorted(k for k in set(audit_keys) if not k.startswith(IDENTITY_BEARING))
    types = kv.pipeline([["TYPE", k] for k in audit_keys])
    value_cmds = []
    for key, kind in zip(audit_keys, types):
        if kind == "set":
            value_cmds.append(["SCARD", key])
        elif kind == "list":
            value_cmds.append(["LLEN", key])
        elif kind == "string":
            value_cmds.append(["GET", key])
        else:
            value_cmds.append(["EXISTS", key])
    values = kv.pipeline(value_cmds) if value_cmds else []
    frames["All keys"] = pd.DataFrame({
        "key": audit_keys,
        "type": types,
        "value": [as_int(v) for v in values],
    })

    # ── summary, written last because it reads the frames above ──────────────
    lifetime_generators = as_int(kv.pipeline([["SCARD", "gen:users:all"]])[0])
    eng = frames["Engagement"]
    today_row = eng.iloc[-1] if not eng.empty else None
    totals_map = dict(zip(frames["Event totals"]["event"], frames["Event totals"]["lifetime"]))
    summary = [
        ("Exported at (UTC)", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")),
        ("Window", f"{dates[0]} to {dates[-1]} ({days} days)"),
        ("", ""),
        ("Builds generated (lifetime)", totals_map.get("build_generated", 0)),
        ("Counter builds (lifetime)", totals_map.get("counter_generated", 0)),
        ("Distinct generators (lifetime)", lifetime_generators),
        ("People who saved (lifetime)", as_int(actor_all[0])),
        ("People who shared (lifetime)", as_int(actor_all[1])),
        ("", ""),
        ("Generators today", int(today_row["generators"]) if today_row is not None else 0),
        ("Generations today", int(today_row["generations"]) if today_row is not None else 0),
        ("Hit the cap today", per_event["limit_reached_anon"][-1] + per_event["limit_reached_signed_in"][-1]),
        ("", ""),
        (f"Generations in last {days}d", int(eng["generations"].sum())),
        (f"Peak generators in a day", int(eng["generators"].max()) if not eng.empty else 0),
    ]
    frames["Summary"] = pd.DataFrame(summary, columns=["metric", "value"])
    return frames


def write_workbook(frames: dict[str, pd.DataFrame], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    order = [
        "Summary", "Engagement", "Cohorts", "Events daily", "Event totals",
        "Savers and sharers", "Feedback summary", "Feedback log", "All keys",
    ]
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        for name in order:
            frame = frames.get(name)
            if frame is None:
                continue
            frame.to_excel(writer, sheet_name=name[:31], index=False)
            sheet = writer.sheets[name[:31]]
            # Freeze the header, filter every table, and size columns to fit so
            # the file is usable the moment it opens rather than after ten
            # minutes of dragging column borders.
            sheet.freeze_panes = "A2"
            if len(frame) and name != "Summary":
                sheet.auto_filter.ref = sheet.dimensions
            for column in sheet.columns:
                letter = column[0].column_letter
                longest = max(
                    (len(str(cell.value)) for cell in column if cell.value is not None),
                    default=8,
                )
                sheet.column_dimensions[letter].width = min(max(longest + 2, 10), 48)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=90,
                        help="days of history (per-day buckets expire after 100)")
    parser.add_argument("--weeks", type=int, default=12, help="weekly cohorts to include")
    parser.add_argument("--out", type=Path, default=None, help="output .xlsx path")
    args = parser.parse_args()

    if args.days > 100:
        print("note: per-day buckets have a 100 day TTL, so older days read as 0")

    url, token = load_env()
    kv = Kv(url, token)
    print(f"reading {url} (read-only), {args.days} days, {args.weeks} weekly cohorts...")
    frames = build_frames(kv, args.days, args.weeks)

    out = args.out or ROOT / "data" / f"wrtruemeta_analytics_{date.today().isoformat()}.xlsx"
    write_workbook(frames, out)

    print(f"\nwrote {out}")
    for name, frame in frames.items():
        print(f"  {name:<22} {len(frame):>5} rows")


if __name__ == "__main__":
    main()
