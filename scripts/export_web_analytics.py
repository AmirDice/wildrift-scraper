"""
Export Vercel Web Analytics to a multi-sheet .xlsx.

The companion to export_analytics.py. That one exports the product counters we
keep ourselves in KV (builds generated, saves, feedback); this one exports what
Vercel measures about the site: visitors, page views, routes, referrers,
countries, devices, browsers and any custom events sent with track().

Run:
    python scripts/export_web_analytics.py                 # last 30 days
    python scripts/export_web_analytics.py --days 90
    python scripts/export_web_analytics.py --out reports/traffic.xlsx
    python scripts/export_web_analytics.py --project wrtruemeta-advisor

Auth, in the order tried:
  1. VERCEL_TOKEN in the environment
  2. VERCEL_TOKEN in web-next/.env.local
  3. the Vercel CLI's own stored login (~AppData/.../com.vercel.cli/auth.json)

The third is what makes this work with no setup on a machine where `vercel` is
already signed in, which is the normal case here. Every call is a GET against
the documented query API, so this cannot change anything in the account.

REPORTING WINDOW. Aggregate queries only reach back as far as the plan's
retention (Pro is 12 months, Hobby 30 days); asking for more silently returns
less. The Summary sheet records the window the API actually answered with, so
a short export is visible rather than assumed.

Docs: https://vercel.com/docs/analytics/web-analytics-api
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / "web-next" / ".env.local"
API = "https://api.vercel.com/v1/query/web-analytics"

#: Where the Vercel CLI keeps its login on each platform.
CLI_AUTH = [
    Path(os.environ.get("APPDATA", "")) / "xdg.data" / "com.vercel.cli" / "auth.json",
    Path(os.environ.get("LOCALAPPDATA", "")) / "com.vercel.cli" / "auth.json",
    Path.home() / ".local" / "share" / "com.vercel.cli" / "auth.json",
    Path.home() / "Library" / "Application Support" / "com.vercel.cli" / "auth.json",
]
CLI_CONFIG = [p.with_name("config.json") for p in CLI_AUTH]

#: One sheet per dimension. The name on the left is the API dimension; the
#: right is what the sheet is called. `day` is handled separately because it is
#: a time series rather than a top-N list.
DIMENSIONS = [
    ("route", "Routes"),
    ("requestPath", "Paths"),
    ("referrerHostname", "Referrers"),
    ("country", "Countries"),
    ("deviceType", "Devices"),
    ("browserName", "Browsers"),
    ("osName", "Operating systems"),
]

#: Valid dimensions that this account cannot query. The API answers 402
#: "UTM dimensions require an Enterprise plan or the Web Analytics Plus
#: add-on", so asking every run would spend two calls to be told no twice.
#: Listed rather than deleted so the reason survives the next plan change.
PAID_DIMENSIONS = ["utmSource", "utmMedium", "utmCampaign", "utmContent", "utmTerm"]


def _read_env(path: Path) -> dict:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def load_token() -> tuple[str, str | None]:
    """(token, team from the CLI config if we found one)."""
    env = _read_env(ENV_FILE)
    token = os.environ.get("VERCEL_TOKEN") or env.get("VERCEL_TOKEN")
    if token:
        return token, None
    for auth in CLI_AUTH:
        try:
            data = json.loads(auth.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("token"):
            team = None
            for cfg in CLI_CONFIG:
                try:
                    team = json.loads(cfg.read_text(encoding="utf-8")).get("currentTeam")
                except (OSError, ValueError):
                    continue
                if team:
                    break
            return data["token"], team
    sys.exit("No Vercel token. Set VERCEL_TOKEN, add it to web-next/.env.local, "
             "or run `vercel login`.")


def get(path: str, token: str, **params) -> dict:
    """One GET against the query API, with a retry for rate limiting."""
    url = f"{API}/{path}?" + urllib.parse.urlencode(
        {k: v for k, v in params.items() if v is not None})
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode()[:200]
            if exc.code == 429 and attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
            # A dimension the plan or project does not support should cost that
            # one sheet, not the whole export.
            return {"_error": f"HTTP {exc.code}: {body}"}
        except Exception as exc:  # noqa: BLE001
            return {"_error": str(exc)[:200]}
    return {"_error": "unreachable"}


def resolve_project(token: str, team: str | None, name: str) -> tuple[str, str | None]:
    url = "https://api.vercel.com/v9/projects?limit=100" + (f"&teamId={team}" if team else "")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=45) as resp:
        projects = json.loads(resp.read().decode()).get("projects", [])
    for project in projects:
        if project["name"] == name or project["id"] == name:
            return project["id"], team
    sys.exit(f"Project {name!r} not found. Available: "
             f"{', '.join(p['name'] for p in projects) or '(none)'}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30, help="window to export (default 30)")
    ap.add_argument("--project", default="wildrift-scraper")
    ap.add_argument("--limit", type=int, default=100, help="rows per dimension sheet")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    token, team = load_token()
    project_id, team = resolve_project(token, team, args.project)
    until = date.today() + timedelta(days=1)      # inclusive of today
    since = until - timedelta(days=args.days + 1)
    base = dict(teamId=team, projectId=project_id,
                since=since.isoformat(), until=until.isoformat())
    print(f"reading Vercel Web Analytics for {args.project}, "
          f"{since} to {until} ({args.days} days)...")

    sheets: dict[str, pd.DataFrame] = {}
    notes: list[tuple[str, str]] = []

    # Lifetime-ish totals (the API answers with the plan's own window).
    total = get("visits/count", token, teamId=team, projectId=project_id)
    window = total.get("query", {}) if isinstance(total, dict) else {}
    totals = total.get("data", {}) if "_error" not in total else {}
    if "_error" in total:
        notes.append(("visits/count", total["_error"]))

    # Daily trend.
    daily = get("visits/aggregate", token, by="day", limit=args.days + 2, **base)
    if "_error" in daily:
        notes.append(("visits by day", daily["_error"]))
    else:
        rows = [{"date": r.get("timestamp", "")[:10],
                 "visitors": r.get("visitors"), "pageviews": r.get("pageviews")}
                for r in daily.get("data", [])]
        if rows:
            frame = pd.DataFrame(rows)
            frame["pageviews per visitor"] = (
                frame["pageviews"] / frame["visitors"].replace(0, pd.NA)).round(2)
            sheets["Daily"] = frame

    # One sheet per dimension.
    for dimension, sheet in DIMENSIONS:
        payload = get("visits/aggregate", token, by=dimension, limit=args.limit, **base)
        if "_error" in payload:
            notes.append((sheet, payload["_error"]))
            continue
        rows = payload.get("data", [])
        if not rows:
            continue
        frame = pd.DataFrame([{dimension: r.get(dimension),
                               "visitors": r.get("visitors"),
                               "pageviews": r.get("pageviews")} for r in rows])
        sheets[sheet] = frame.sort_values("pageviews", ascending=False)

    # Custom events, which only exist if track() is being called.
    events = get("events/aggregate", token, by="eventName", limit=args.limit, **base)
    if "_error" in events:
        notes.append(("Custom events", events["_error"]))
    elif events.get("data"):
        sheets["Custom events"] = pd.DataFrame(
            [{"event": r.get("eventName"), "count": r.get("count"),
              "visitors": r.get("visitors")} for r in events["data"]])

    if not sheets:
        print("no data returned; nothing written")
        for where, why in notes:
            print(f"  {where}: {why}")
        return 1

    daily_frame = sheets.get("Daily")
    summary = [
        ("Exported at (UTC)", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")),
        ("Project", args.project),
        ("Requested window", f"{since} to {until} ({args.days} days)"),
        ("API answered from", f"{window.get('since', '?')[:10]} to {window.get('until', '?')[:10]}"),
        ("", ""),
        ("Visitors (API window)", totals.get("visitors")),
        ("Page views (API window)", totals.get("pageviews")),
    ]
    if daily_frame is not None and not daily_frame.empty:
        busiest = daily_frame.loc[daily_frame["pageviews"].idxmax()]
        summary += [
            ("", ""),
            (f"Visitors in last {args.days}d", int(daily_frame["visitors"].sum())),
            (f"Page views in last {args.days}d", int(daily_frame["pageviews"].sum())),
            ("Busiest day", f"{busiest['date']} ({int(busiest['pageviews'])} views)"),
            ("Median daily visitors", int(daily_frame["visitors"].median())),
        ]
    for where, why in notes:
        summary.append((f"NOTE {where}", why))

    out = args.out or (ROOT / "data" / f"wrtruemeta_web_analytics_{date.today()}.xlsx")
    out.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        pd.DataFrame(summary, columns=["metric", "value"]).to_excel(
            writer, sheet_name="Summary", index=False)
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name[:31], index=False)

    print(f"\nwrote {out}")
    print(f"  {'Summary':<24} {len(summary)} rows")
    for name, frame in sheets.items():
        print(f"  {name:<24} {len(frame)} rows")
    for where, why in notes:
        print(f"  note: {where}: {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
