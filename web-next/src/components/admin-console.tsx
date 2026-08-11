"use client";

import { useCallback, useEffect, useState } from "react";
import { Card } from "@/components/ui";
import { FEEDBACK_REASONS } from "@/lib/feedback-options";

interface AccessCodeRow {
  code: string;
  kind: "beta" | "referral";
  label: string;
  grantsBeta: boolean;
  unlimitedBuilds: boolean;
  active: boolean;
  maxUses: number | null;
  createdAt: string;
  clicks: number;
  activations: number;
  signIns: number;
}

interface BestBuildRow {
  championSlug: string;
  player: string;
  standing?: string;
  items: string[];
  boots?: string;
  runes: string[];
  note?: string;
  updatedAt: string;
}

interface CreatorAdminRow {
  id: string;
  name: string;
  tagline: string;
  categories: string[];
  languages?: string[];
  links: Record<string, string>;
  avatar?: string;
  lastChecked: string;
  updatedAt: string;
}

const CREATOR_CATEGORIES = [
  ["educational", "Educational"], ["guides", "Guides & builds"], ["high-elo", "High elo"],
  ["funny", "Funny"], ["montage", "Montages"], ["esports", "Esports"],
  ["news", "News & patches"], ["community", "Community"],
] as const;
const CREATOR_PLATFORMS = ["youtube", "twitch", "tiktok", "kick", "x", "instagram", "discord", "website"] as const;

const TOKEN_KEY = "wtm_admin_token";

/**
 * The admin console: invite links and hand-recorded best-player builds.
 *
 * The token lives in sessionStorage rather than a cookie or the URL, so it is
 * gone when the tab closes and never ends up in a shared link or a server log.
 * Everything it can do is already gated server-side; this is only the keyboard.
 */
export function AdminConsole() {
  const [token, setToken] = useState("");
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      try {
        const saved = sessionStorage.getItem(TOKEN_KEY);
        if (saved) {
          setToken(saved);
          setReady(true);
        }
      } catch {
        /* ignore */
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  const unlock = async () => {
    setError(null);
    try {
      const res = await fetch(`/api/admin/codes?token=${encodeURIComponent(token)}`);
      if (!res.ok) {
        setError("That token was rejected.");
        return;
      }
      try {
        sessionStorage.setItem(TOKEN_KEY, token);
      } catch {
        /* ignore */
      }
      setReady(true);
    } catch {
      setError("Could not reach the server.");
    }
  };

  if (!ready) {
    return (
      <Card className="mx-auto max-w-md p-6">
        <h2 className="font-semibold">Admin token</h2>
        <p className="mt-1 text-sm text-muted">
          The value of <code className="text-text">ADMIN_TOKEN</code>. Kept in this tab only.
        </p>
        <input
          type="password"
          value={token}
          onChange={(event) => setToken(event.target.value)}
          onKeyDown={(event) => event.key === "Enter" && void unlock()}
          className="mt-3 w-full rounded-lg border border-line bg-white/[0.04] px-3 py-2 text-sm text-text outline-none focus:border-accent/50"
        />
        <button
          onClick={unlock}
          disabled={!token.trim()}
          className="mt-3 w-full rounded-lg bg-accent px-4 py-2 text-sm font-bold text-black transition hover:opacity-90 disabled:opacity-40"
        >
          Unlock
        </button>
        {error && <p className="mt-2 text-xs text-bad">{error}</p>}
      </Card>
    );
  }

  return (
    <div className="space-y-8">
      <OperationsPanel token={token} />
      <UsagePanel token={token} />
      <UnlimitedAccessPanel token={token} />
      <CodesPanel token={token} />
      <BestBuildsPanel token={token} />
      <CreatorsPanel token={token} />
    </div>
  );
}

/* ── usage, feedback and accounts ────────────────────────────────────────── */

interface FeedbackEntry {
  verdict: "up" | "down";
  reasons?: string[];
  note?: string;
  champion?: string;
  at?: string;
}

interface SignInEntry { email?: string; name?: string; at?: string }

interface EngagementDay {
  day: string;
  unique: number;
  newUsers: number;
  returning: number;
  depth: number[];
}

interface CohortRow { week: string; size: number; d1: number; d7: number; d30: number }

interface ActorSummary {
  action: string;
  allTime: number;
  today: number;
  daily: { day: string; unique: number }[];
}

interface UsageData {
  events: Record<string, { total: number; today: number; last7Days: number }>;
  engagement?: EngagementDay[];
  cohorts?: CohortRow[];
  actors?: Record<string, ActorSummary>;
  feedback: {
    up: number;
    down: number;
    reasons: Record<string, number>;
    recent: FeedbackEntry[];
  };
  accounts: { unique: number; recentSignIns: SignInEntry[] };
}

const REASON_LABELS = Object.fromEntries(FEEDBACK_REASONS.map((r) => [r.key, r.label]));

// The counters people actually ask about, in plain words. Everything else the
// API returns still shows, below these, under its raw event name.
const EVENT_LABELS: Record<string, string> = {
  signed_in: "Google sign-ins",
  build_generated: "Builds generated",
  counter_generated: "Counter builds generated",
  build_saved: "Builds saved",
  build_shared: "Builds shared",
  build_liked: "Builds liked",
  build_feedback: "Feedback left",
  custom_opened: "Custom Lab opened",
  custom_edited: "Custom Lab edited",
  limit_reached_anon: "Hit the cap (could sign in)",
  limit_reached_signed_in: "Hit the cap (nothing left)",
};

function timeAgo(iso?: string): string {
  if (!iso) return "";
  const seconds = Math.round((Date.now() - Date.parse(iso)) / 1000);
  if (!Number.isFinite(seconds) || seconds < 0) return "";
  if (seconds < 3600) return `${Math.max(1, Math.round(seconds / 60))}m ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86400)}d ago`;
}

/**
 * What people are doing and saying: sign-in counts (events AND unique
 * accounts -- they differ, and the difference is repeat sign-ins), every
 * tracked usage counter, the thumbs tally with reasons, and the free-text
 * feedback log that until now was only reachable with curl.
 */
function UsagePanel({ token }: { token: string }) {
  const [data, setData] = useState<UsageData | null>(null);
  const [showAllFeedback, setShowAllFeedback] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`/api/admin/usage?token=${encodeURIComponent(token)}`);
      if (res.ok) setData(await res.json() as UsageData);
    } catch {
      /* transient */
    }
  }, [token]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  if (!data) {
    return (
      <section>
        <h2 className="text-xl font-semibold tracking-tight">Usage &amp; feedback</h2>
        <p className="mt-1 text-sm text-muted">Loading…</p>
      </section>
    );
  }

  const signIns = data.events.signed_in;
  const eventRows = Object.entries(data.events)
    .sort(([a], [b]) => (a in EVENT_LABELS ? 0 : 1) - (b in EVENT_LABELS ? 0 : 1) || a.localeCompare(b));
  const feedbackEntries = data.feedback.recent.filter((entry) => entry && typeof entry === "object");
  const shownFeedback = showAllFeedback ? feedbackEntries : feedbackEntries.slice(0, 10);
  const reasonRows = Object.entries(data.feedback.reasons)
    .filter(([, count]) => count > 0)
    .sort(([, a], [, b]) => b - a);

  return (
    <section>
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-xl font-semibold tracking-tight">Usage &amp; feedback</h2>
        <button
          onClick={() => void load()}
          className="rounded-lg border border-line px-3 py-1 text-xs font-medium text-muted transition hover:text-text"
        >
          Refresh
        </button>
      </div>
      <p className="mt-1 max-w-2xl text-sm text-muted">
        Who is signing in, what the tools are doing, and what people say about the builds.
      </p>

      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <Card className="p-4">
          <p className="text-[0.65rem] font-bold uppercase tracking-wide text-faint">Unique Google accounts</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums">{data.accounts.unique}</p>
          <p className="mt-1 text-xs text-muted">Counted per account since Aug 7, 2026.</p>
        </Card>
        <Card className="p-4">
          <p className="text-[0.65rem] font-bold uppercase tracking-wide text-faint">Sign-ins (all time)</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums">{signIns?.total ?? 0}</p>
          <p className="mt-1 text-xs text-muted">
            {signIns ? `${signIns.today} today · ${signIns.last7Days} in 7 days` : ""}
          </p>
        </Card>
        <Card className="p-4">
          <p className="text-[0.65rem] font-bold uppercase tracking-wide text-faint">Build feedback</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums">
            <span className="text-emerald-300">▲ {data.feedback.up}</span>
            <span className="mx-2 text-faint">/</span>
            <span className="text-bad">▼ {data.feedback.down}</span>
          </p>
          <p className="mt-1 text-xs text-muted">Thumbs on generated builds, lifetime.</p>
        </Card>
      </div>

      {(() => {
        const days = data.engagement ?? [];
        const today = days[0];
        const week = days.reduce((acc, d) => ({
          newUsers: acc.newUsers + d.newUsers,
          returning: acc.returning + d.returning,
          depth: acc.depth.map((v, i) => v + (d.depth[i] ?? 0)),
        }), { newUsers: 0, returning: 0, depth: [0, 0, 0, 0, 0, 0] });
        // depth[i] = people who REACHED generation i+1; exactly-N = reached N minus reached N+1
        const exactly = (depth: number[]) => depth.map((v, i) => i < depth.length - 1 ? v - (depth[i + 1] ?? 0) : v);
        const todayExact = exactly(today?.depth ?? [0, 0, 0, 0, 0, 0]);
        const weekExact = exactly(week.depth);
        const weekTotal = week.newUsers + week.returning;
        const depthLabel = ["1", "2", "3", "4", "5", "6+"];
        return (
          <Card className="mt-4 p-4">
            <h3 className="text-sm font-semibold">Generation engagement</h3>
            <p className="mt-1 text-xs text-muted">
              Who generates, whether they come back, and how deep into the daily 5 they go.
              Tracked from Aug 8, 2026 -- earlier days read as zero.
            </p>
            <div className="mt-3 grid gap-3 sm:grid-cols-3">
              <div>
                <p className="text-[0.65rem] font-bold uppercase tracking-wide text-faint">Generators today</p>
                <p className="mt-0.5 text-xl font-semibold tabular-nums">{today?.unique ?? 0}</p>
                <p className="text-xs text-muted">{today?.newUsers ?? 0} new · {today?.returning ?? 0} returning</p>
              </div>
              <div>
                <p className="text-[0.65rem] font-bold uppercase tracking-wide text-faint">Last 7 days</p>
                <p className="mt-0.5 text-xl font-semibold tabular-nums">{weekTotal}</p>
                <p className="text-xs text-muted">{week.newUsers} new · {week.returning} returning
                  {weekTotal > 0 ? ` (${Math.round(100 * week.returning / weekTotal)}% return)` : ""}</p>
              </div>
              <div>
                <p className="text-[0.65rem] font-bold uppercase tracking-wide text-faint">Used all 5 (7 days)</p>
                <p className="mt-0.5 text-xl font-semibold tabular-nums">{(week.depth[4] ?? 0) + (week.depth[5] ?? 0)}</p>
                <p className="text-xs text-muted">stopped at 1: {weekExact[0] ?? 0}</p>
              </div>
            </div>
            <table className="mt-3 w-full text-sm">
              <thead>
                <tr className="border-b border-line text-left text-[0.65rem] uppercase tracking-wide text-faint">
                  <th className="py-1.5">Generations used</th>
                  {depthLabel.map((l) => <th key={l} className="text-right">{l}</th>)}
                </tr>
              </thead>
              <tbody>
                <tr className="border-b border-line/40">
                  <td className="py-1.5 text-muted">People today</td>
                  {todayExact.map((v, i) => <td key={i} className="text-right tabular-nums">{v}</td>)}
                </tr>
                <tr>
                  <td className="py-1.5 text-muted">People, last 7 days</td>
                  {weekExact.map((v, i) => <td key={i} className="text-right tabular-nums text-text">{v}</td>)}
                </tr>
              </tbody>
            </table>
          </Card>
        );
      })()}

      {(data.cohorts?.length ?? 0) > 0 && (
        <Card className="mt-4 p-4">
          <h3 className="text-sm font-semibold">Retention by cohort</h3>
          <p className="mt-1 text-xs text-muted">
            Of the people who generated their FIRST build in a given week, how many came back.
            A cohort needs its window to elapse before its number means anything: this week&rsquo;s
            D30 will read 0 until 30 days have passed.
          </p>
          <table className="mt-3 w-full text-sm">
            <thead>
              <tr className="border-b border-line text-left text-[0.65rem] uppercase tracking-wide text-faint">
                <th className="py-1.5">Week</th>
                <th className="text-right">New</th>
                <th className="text-right">D1</th>
                <th className="text-right">D7</th>
                <th className="text-right">D30</th>
              </tr>
            </thead>
            <tbody>
              {data.cohorts!.map((c) => {
                const pct = (n: number) => (c.size ? `${Math.round((100 * n) / c.size)}%` : "--");
                return (
                  <tr key={c.week} className="border-b border-line/40">
                    <td className="py-1.5 font-mono text-xs text-muted">{c.week}</td>
                    <td className="text-right tabular-nums text-text">{c.size}</td>
                    <td className="text-right tabular-nums">{c.d1} <span className="text-faint">{pct(c.d1)}</span></td>
                    <td className="text-right tabular-nums">{c.d7} <span className="text-faint">{pct(c.d7)}</span></td>
                    <td className="text-right tabular-nums">{c.d30} <span className="text-faint">{pct(c.d30)}</span></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      )}

      {data.actors && (
        <Card className="mt-4 p-4">
          <h3 className="text-sm font-semibold">Savers and sharers</h3>
          <p className="mt-1 text-xs text-muted">
            Distinct PEOPLE, against the action totals above. One person sharing the same build
            into four group chats is four shares but one sharer, and only the second number says
            whether sharing is a channel worth building on. Counted from 2026-08-10; anything
            before that reads as zero because nobody was counting, not because nobody shared.
          </p>
          <table className="mt-3 w-full text-sm">
            <thead>
              <tr className="border-b border-line text-left text-[0.65rem] uppercase tracking-wide text-faint">
                <th className="py-1.5">Action</th>
                <th className="text-right">People (all time)</th>
                <th className="text-right">People today</th>
                <th className="text-right">Actions (all time)</th>
                <th className="text-right">Per person</th>
              </tr>
            </thead>
            <tbody>
              {(["saved", "shared"] as const).map((action) => {
                const actor = data.actors?.[action];
                if (!actor) return null;
                const actions = data.events[action === "saved" ? "build_saved" : "build_shared"]?.total ?? 0;
                return (
                  <tr key={action} className="border-b border-line/40">
                    <td className="py-1.5 capitalize text-muted">{action}</td>
                    <td className="text-right tabular-nums text-text">{actor.allTime}</td>
                    <td className="text-right tabular-nums">{actor.today}</td>
                    <td className="text-right tabular-nums text-faint">{actions}</td>
                    <td className="text-right tabular-nums text-faint">
                      {actor.allTime ? (actions / actor.allTime).toFixed(1) : "--"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      )}

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card className="p-4">
          <h3 className="text-sm font-semibold">Recent sign-ins</h3>
          <div className="mt-2 divide-y divide-line/60">
            {data.accounts.recentSignIns.slice(0, 12).map((entry, index) => (
              <div key={`${entry.email}-${index}`} className="flex items-center gap-3 py-1.5 text-sm">
                <span className="min-w-0 flex-1 truncate">{entry.name || entry.email || "(unknown)"}</span>
                <span className="truncate font-mono text-xs text-faint">{entry.email}</span>
                <span className="shrink-0 text-xs text-faint">{timeAgo(entry.at)}</span>
              </div>
            ))}
            {data.accounts.recentSignIns.length === 0 && (
              <p className="py-4 text-center text-sm text-faint">
                No sign-ins recorded yet -- the log starts with the first sign-in after this deploy.
              </p>
            )}
          </div>
        </Card>

        <Card className="p-4">
          <h3 className="text-sm font-semibold">Activity counters</h3>
          <table className="mt-2 w-full text-sm">
            <thead>
              <tr className="border-b border-line text-left text-[0.65rem] uppercase tracking-wide text-faint">
                <th className="py-1.5">Event</th>
                <th className="text-right">Today</th>
                <th className="text-right">7 days</th>
                <th className="text-right">Total</th>
              </tr>
            </thead>
            <tbody>
              {eventRows.map(([event, counts]) => (
                <tr key={event} className="border-b border-line/40">
                  <td className="py-1.5 text-muted">{EVENT_LABELS[event] ?? event.replaceAll("_", " ")}</td>
                  <td className="text-right tabular-nums">{counts.today}</td>
                  <td className="text-right tabular-nums">{counts.last7Days}</td>
                  <td className="text-right tabular-nums text-text">{counts.total}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>

      <Card className="mt-4 p-4">
        <div className="flex flex-wrap items-center gap-3">
          <h3 className="text-sm font-semibold">What people said</h3>
          {reasonRows.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {reasonRows.map(([reason, count]) => (
                <span key={reason} className="rounded-full border border-line px-2 py-0.5 text-[0.65rem] text-muted">
                  {REASON_LABELS[reason] ?? reason} · {count}
                </span>
              ))}
            </div>
          )}
        </div>
        <div className="mt-2 divide-y divide-line/60">
          {shownFeedback.map((entry, index) => (
            <div key={`${entry.at}-${index}`} className="py-2.5">
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className={entry.verdict === "up" ? "font-bold text-emerald-300" : "font-bold text-bad"}>
                  {entry.verdict === "up" ? "▲" : "▼"}
                </span>
                {entry.champion && <span className="font-medium text-text">{entry.champion}</span>}
                {(entry.reasons ?? []).map((reason) => (
                  <span key={reason} className="rounded-full border border-line px-2 py-0.5 text-[0.65rem] text-muted">
                    {REASON_LABELS[reason] ?? reason}
                  </span>
                ))}
                <span className="ml-auto text-faint">{timeAgo(entry.at)}</span>
              </div>
              {entry.note && <p className="mt-1 text-sm leading-relaxed text-muted">{entry.note}</p>}
            </div>
          ))}
          {feedbackEntries.length === 0 && (
            <p className="py-4 text-center text-sm text-faint">No feedback yet.</p>
          )}
        </div>
        {feedbackEntries.length > 10 && (
          <button
            onClick={() => setShowAllFeedback((value) => !value)}
            className="mt-2 rounded-md border border-line px-3 py-1 text-xs text-muted transition hover:text-text"
          >
            {showAllFeedback ? "Show fewer" : `Show all ${feedbackEntries.length}`}
          </button>
        )}
      </Card>
    </section>
  );
}

/* ── operations ──────────────────────────────────────────────────────────── */

interface OpsJob {
  id: string;
  op: string;
  label?: string;
  args?: Record<string, unknown>;
  status?: string;
  startedAt?: number;
  finishedAt?: number;
  exitCode?: number | null;
  lines?: string[];
  queuedAt?: number;
}

interface OpsStatus {
  runnerOnline: boolean;
  runner: { at: number; host: string; job: { id: string; op: string } | null } | null;
  current: OpsJob | null;
  queue: OpsJob[];
  history: OpsJob[];
}

// What each button does, in the owner's words. The command lines these map to
// live in scripts/ops_runner.py -- this list is display only.
const OPS_BUTTONS: { op: string; label: string; description: string }[] = [
  {
    op: "scrape",
    label: "Scrape leaderboards",
    description: "Capture every champion board from the phone (skips ones already captured). Needs the phone plugged in with the game on the champion tab.",
  },
  {
    op: "extract-pending",
    label: "Extract pending captures",
    description: "Read win rates, names and builds out of any capture session that has not been extracted yet.",
  },
  {
    op: "refresh-data",
    label: "Refresh site data",
    description: "Merge finished captures and regenerate everything the site reads: leaderboards, tiers, pulse stats, champion details, engine data.",
  },
  {
    op: "fetch-patches",
    label: "Fetch patch notes",
    description: "Pull the official patch archive from Riot and rebuild the champion change history.",
  },
  {
    op: "publish",
    label: "Publish to the site",
    description: "Commit the regenerated data files and push, which deploys the site. Data paths only, never code.",
  },
  {
    op: "deploy-advisor",
    label: "Redeploy advisor",
    description: "Restage and deploy the build advisor so it serves the freshest data. Run after every refresh.",
  },
  {
    op: "export-analytics",
    label: "Export analytics",
    description: "Write every counter, cohort and feedback note to a dated Excel workbook. Reads with the read-only token and exports counts only, never identities. The file lands in data/ on the machine running the ops runner.",
  },
];

function opsDuration(job: OpsJob): string {
  if (!job.startedAt) return "";
  const end = job.finishedAt ?? Date.now() / 1000;
  const seconds = Math.max(0, Math.round(end - job.startedAt));
  if (seconds < 90) return `${seconds}s`;
  return `${Math.round(seconds / 60)}m`;
}

function OpsStatusBadge({ status }: { status?: string }) {
  const tone = status === "done" ? "bg-emerald-400/15 text-emerald-300"
    : status === "running" ? "bg-accent/15 text-accent"
    : status === "stopped" ? "bg-amber-400/15 text-amber-300"
    : "bg-bad/15 text-bad";
  return (
    <span className={`rounded-md px-2 py-0.5 text-[0.65rem] font-bold uppercase tracking-wide ${tone}`}>
      {status ?? "?"}
    </span>
  );
}

/**
 * One-click pipeline control. The buttons enqueue jobs into KV; the ops
 * runner on the collection machine executes them and streams the log tail
 * back. The panel is honest about the machine being off: every button still
 * works (the queue persists), but the offline banner says nothing will happen
 * until the runner is started.
 */
function OperationsPanel({ token }: { token: string }) {
  const [status, setStatus] = useState<OpsStatus | null>(null);
  const [only, setOnly] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`/api/admin/ops?token=${encodeURIComponent(token)}`);
      if (res.ok) setStatus(await res.json() as OpsStatus);
    } catch {
      /* transient -- next poll wins */
    }
  }, [token]);

  // Poll faster while a job is live so the log tail reads like a terminal.
  useEffect(() => {
    void load();
    const running = status?.current?.status === "running";
    const timer = window.setInterval(() => void load(), running ? 2500 : 6000);
    return () => window.clearInterval(timer);
  }, [load, status?.current?.status]);

  const post = async (body: Record<string, unknown>, message: string) => {
    setBusy(true);
    setNote(null);
    try {
      const res = await fetch(`/api/admin/ops?token=${encodeURIComponent(token)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json() as { error?: string };
      setNote(res.ok ? message : data.error ?? "The server rejected that.");
      await load();
    } catch {
      setNote("Could not reach the server.");
    } finally {
      setBusy(false);
    }
  };

  const enqueue = (op: string, extra: Record<string, unknown> = {}) =>
    void post({ action: "enqueue", op, ...extra },
      status?.runnerOnline ? "Queued." : "Queued. It will run once the runner is started.");

  const current = status?.current ?? null;
  const running = current?.status === "running";

  return (
    <section>
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-xl font-semibold tracking-tight">Operations</h2>
        {status && (
          <span className={`rounded-md px-2 py-1 text-[0.65rem] font-bold uppercase tracking-wide ${
            status.runnerOnline ? "bg-emerald-400/15 text-emerald-300" : "bg-bad/15 text-bad"}`}>
            {status.runnerOnline ? `Runner online · ${status.runner?.host ?? ""}` : "Runner offline"}
          </span>
        )}
        {running && (
          <button
            onClick={() => void post({ action: "stop" }, "Stop signal sent.")}
            disabled={busy}
            className="rounded-lg bg-bad/85 px-3 py-1.5 text-xs font-bold text-white transition hover:bg-bad disabled:opacity-40"
          >
            Stop current job
          </button>
        )}
      </div>
      <p className="mt-1 max-w-2xl text-sm text-muted">
        One-click pipeline control. Jobs run on the collection machine through{" "}
        <code className="text-text">python -m scripts.ops_runner</code>; buttons queue up if it is offline.
      </p>

      {status && !status.runnerOnline && (
        <p className="mt-3 rounded-lg border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-xs text-amber-200">
          The runner is not reporting. Start it on the collection machine -- queued jobs wait, nothing is lost.
        </p>
      )}

      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {OPS_BUTTONS.map((entry) => (
          <Card key={entry.op} className="flex flex-col p-4">
            <h3 className="text-sm font-semibold">{entry.label}</h3>
            <p className="mt-1 flex-1 text-xs leading-relaxed text-muted">{entry.description}</p>
            {entry.op === "scrape" && (
              <input
                value={only}
                onChange={(event) => setOnly(event.target.value)}
                placeholder="Only these champions (optional): Veigar, Shen"
                className="mt-3 w-full rounded-lg border border-line bg-white/[0.04] px-3 py-2 text-xs text-text outline-none focus:border-accent/50"
              />
            )}
            <button
              onClick={() => enqueue(entry.op, entry.op === "scrape" && only.trim() ? { only: only.trim() } : {})}
              disabled={busy}
              className="mt-3 rounded-lg bg-accent px-3 py-2 text-xs font-bold text-black transition hover:opacity-90 disabled:opacity-40"
            >
              {entry.op === "scrape" && only.trim() ? "Queue targeted scrape" : "Run"}
            </button>
          </Card>
        ))}
      </div>

      {note && <p className="mt-3 text-xs text-accent">{note}</p>}

      {(current || (status?.queue.length ?? 0) > 0) && (
        <Card className="mt-4 p-4">
          {current && (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <OpsStatusBadge status={current.status} />
                <span className="text-sm font-semibold">{current.label ?? current.op}</span>
                <span className="text-xs text-faint">
                  {opsDuration(current)}
                  {typeof current.exitCode === "number" && current.status !== "done"
                    ? ` · exit ${current.exitCode}` : ""}
                </span>
                {current.status !== "running" && (
                  <button
                    onClick={() => void post({ action: "reset" }, "Cleared.")}
                    className="ml-auto rounded-md px-2 py-1 text-xs text-faint transition hover:text-text"
                  >
                    Clear
                  </button>
                )}
              </div>
              {(current.lines?.length ?? 0) > 0 && (
                <pre className="mt-3 max-h-64 overflow-y-auto whitespace-pre-wrap rounded-lg bg-black/40 p-3 font-mono text-[0.7rem] leading-relaxed text-muted">
                  {current.lines!.join("\n")}
                </pre>
              )}
            </>
          )}
          {(status?.queue.length ?? 0) > 0 && (
            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted">
              <span className="font-semibold uppercase tracking-wide text-faint">Queued:</span>
              {status!.queue.map((job) => (
                <span key={job.id} className="rounded-md border border-line px-2 py-0.5">{job.op}</span>
              ))}
              <button
                onClick={() => void post({ action: "clear-queue" }, "Queue cleared.")}
                className="rounded-md px-2 py-1 text-faint transition hover:text-bad"
              >
                Clear queue
              </button>
            </div>
          )}
        </Card>
      )}

      {(status?.history.length ?? 0) > 0 && (
        <div className="mt-4 divide-y divide-line/60">
          {status!.history.slice(0, 8).map((job) => (
            <div key={`${job.id}-${job.finishedAt}`} className="flex flex-wrap items-center gap-3 py-2 text-sm">
              <OpsStatusBadge status={job.status} />
              <span className="font-medium">{job.label ?? job.op}</span>
              <span className="text-xs text-faint">{opsDuration(job)}</span>
              <span className="ml-auto text-xs text-faint">
                {job.finishedAt ? new Date(job.finishedAt * 1000).toLocaleString() : ""}
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

/**
 * Why this browser's account is, or is not, exempt from the generation cap.
 *
 * First panel on the page on purpose: it answers the question that has no other
 * answer. `unlimited: false` is indistinguishable from the outside whether the
 * email mismatched, ADMIN_EMAILS never reached the deployment, or the session
 * is stale, and working that out by elimination took a full round of checking
 * the project, the deploy time and the session shape.
 */
function UnlimitedAccessPanel({ token }: { token: string }) {
  const [state, setState] = useState<{
    matched: boolean; reason: string; sessionEmail: string | null;
    signedIn: boolean; configured: string[]; adminEmailsSet: boolean;
  } | null>(null);
  const [busy, setBusy] = useState(false);

  const fetchState = useCallback(async () => {
    const res = await fetch(`/api/admin/whoami?token=${encodeURIComponent(token)}`);
    return res.ok ? await res.json() : null;
  }, [token]);

  // The initial load deliberately does NOT flip `busy` first: setting state
  // synchronously inside an effect triggers a cascading render, and every
  // setState here lands after the fetch has already suspended.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const next = await fetchState();
      if (!cancelled) setState(next);
    })();
    return () => { cancelled = true; };
  }, [fetchState]);

  // The button is an event handler, so the spinner can be set eagerly there.
  const check = async () => {
    setBusy(true);
    try {
      setState(await fetchState());
    } finally {
      setBusy(false);
    }
  };

  return (
    <section>
      <h2 className="text-xl font-semibold tracking-tight">Unlimited generations</h2>
      <p className="mt-1 max-w-2xl text-sm text-muted">
        Whether the account signed in on <em>this</em> browser is exempt from the daily
        build cap, and if not, exactly which part of the chain is failing.
      </p>

      <Card className="mt-4 p-4">
        {!state ? (
          <p className="text-sm text-muted">{busy ? "Checking…" : "No result."}</p>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <span className={`rounded-md px-2 py-1 text-xs font-bold uppercase tracking-wide ${
                state.matched ? "bg-emerald-400/15 text-emerald-300" : "bg-bad/15 text-bad"}`}>
                {state.matched ? "Unlimited" : "Capped"}
              </span>
              <button onClick={() => void check()} disabled={busy}
                className="rounded-lg border border-line px-3 py-1 text-xs font-medium text-muted transition hover:text-text disabled:opacity-40">
                {busy ? "Checking…" : "Re-check"}
              </button>
            </div>

            <p className="mt-3 text-sm leading-relaxed text-muted">{state.reason}</p>

            <dl className="mt-4 grid gap-2 text-xs sm:grid-cols-2">
              <div>
                <dt className="font-semibold uppercase tracking-wide text-faint">Signed in as</dt>
                <dd className="mt-0.5 font-mono text-text">{state.sessionEmail ?? "(nobody)"}</dd>
              </div>
              <div>
                <dt className="font-semibold uppercase tracking-wide text-faint">
                  ADMIN_EMAILS ({state.configured.length})
                </dt>
                <dd className="mt-0.5 font-mono text-text">
                  {state.adminEmailsSet
                    ? (state.configured.join(", ") || "(set, but parses to nothing)")
                    : "(not set on this deployment)"}
                </dd>
              </div>
            </dl>

            {!state.matched && state.signedIn && state.configured.length > 0 && (
              <p className="mt-3 text-xs leading-relaxed text-faint">
                Compare the two lines above character for character. A different Google
                account and a one-letter typo look the same from the outside. Changing the
                variable needs a redeploy: Vercel applies environment variables at deploy
                time, not on save.
              </p>
            )}
          </>
        )}
      </Card>
    </section>
  );
}

function CreatorsPanel({ token }: { token: string }) {
  const emptyForm = {
    id: "", name: "", tagline: "", categories: [] as string[], languages: "", avatar: "",
    lastChecked: "", links: Object.fromEntries(CREATOR_PLATFORMS.map((platform) => [platform, ""])) as Record<string, string>,
  };
  const [creators, setCreators] = useState<CreatorAdminRow[]>([]);
  const [form, setForm] = useState(emptyForm);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await fetch(`/api/admin/creators?token=${encodeURIComponent(token)}`);
    if (!res.ok) return;
    const data = await res.json() as { creators: CreatorAdminRow[] };
    setCreators(data.creators);
  }, [token]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const setField = (key: "name" | "tagline" | "languages" | "avatar" | "lastChecked", value: string) =>
    setForm((current) => ({ ...current, [key]: value }));
  const toggleCategory = (category: string) => setForm((current) => ({
    ...current,
    categories: current.categories.includes(category)
      ? current.categories.filter((entry) => entry !== category)
      : [...current.categories, category],
  }));

  const save = async () => {
    if (!form.name.trim() || !form.tagline.trim() || busy) return;
    setBusy(true);
    setNote(null);
    try {
      const res = await fetch(`/api/admin/creators?token=${encodeURIComponent(token)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...form,
          languages: form.languages.split(",").map((entry) => entry.trim()).filter(Boolean),
        }),
      });
      const data = await res.json() as { creator?: CreatorAdminRow; error?: string };
      setNote(res.ok ? `Saved ${data.creator?.name ?? form.name}.` : data.error ?? "Could not save creator.");
      if (res.ok) {
        setForm(emptyForm);
        await load();
      }
    } finally {
      setBusy(false);
    }
  };

  const edit = (creator: CreatorAdminRow) => {
    setForm({
      id: creator.id,
      name: creator.name,
      tagline: creator.tagline,
      categories: [...creator.categories],
      languages: creator.languages?.join(", ") ?? "",
      avatar: creator.avatar ?? "",
      lastChecked: creator.lastChecked,
      links: Object.fromEntries(CREATOR_PLATFORMS.map((platform) => [platform, creator.links[platform] ?? ""])),
    });
    setNote(`Editing ${creator.name}.`);
  };

  const inputClass = "w-full rounded-lg border border-line bg-white/[0.04] px-3 py-2 text-sm text-text outline-none focus:border-accent/50";
  return (
    <section>
      <h2 className="text-xl font-semibold tracking-tight">Content creators</h2>
      <p className="mt-1 max-w-2xl text-sm text-muted">
        Add or update verified creators shown in the public creator directory. Include at least one category
        and one full platform URL. The verification date defaults to today when left blank.
      </p>

      <Card className="mt-4 p-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-xs font-semibold uppercase tracking-wide text-faint">
            Name
            <input value={form.name} onChange={(event) => setField("name", event.target.value)} placeholder="Creator or channel name" className={`mt-1 ${inputClass}`} />
          </label>
          <label className="text-xs font-semibold uppercase tracking-wide text-faint">
            Tagline
            <input value={form.tagline} onChange={(event) => setField("tagline", event.target.value)} placeholder="What their content is known for" className={`mt-1 ${inputClass}`} />
          </label>
          <label className="text-xs font-semibold uppercase tracking-wide text-faint">
            Languages
            <input value={form.languages} onChange={(event) => setField("languages", event.target.value)} placeholder="English, Spanish" className={`mt-1 ${inputClass}`} />
          </label>
          <label className="text-xs font-semibold uppercase tracking-wide text-faint">
            Last checked
            <input type="date" value={form.lastChecked} onChange={(event) => setField("lastChecked", event.target.value)} className={`mt-1 ${inputClass}`} />
          </label>
          <label className="text-xs font-semibold uppercase tracking-wide text-faint sm:col-span-2">
            Avatar URL (optional)
            <input value={form.avatar} onChange={(event) => setField("avatar", event.target.value)} placeholder="https://…" className={`mt-1 ${inputClass}`} />
          </label>
        </div>

        <div className="mt-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-faint">Categories</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {CREATOR_CATEGORIES.map(([key, label]) => (
              <button key={key} type="button" onClick={() => toggleCategory(key)} className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${form.categories.includes(key) ? "bg-accent text-black" : "border border-line text-muted hover:text-text"}`}>
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {CREATOR_PLATFORMS.map((platform) => (
            <label key={platform} className="text-xs font-semibold uppercase tracking-wide text-faint">
              {platform}
              <input
                value={form.links[platform]}
                onChange={(event) => setForm((current) => ({ ...current, links: { ...current.links, [platform]: event.target.value } }))}
                placeholder={`https://${platform === "x" ? "x.com" : `${platform}.com`}/…`}
                className={`mt-1 ${inputClass}`}
              />
            </label>
          ))}
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <button type="button" onClick={save} disabled={!form.name.trim() || !form.tagline.trim() || busy} className="rounded-lg bg-accent px-4 py-2 text-sm font-bold text-black transition hover:opacity-90 disabled:opacity-40">
            {form.id ? "Update creator" : "Add creator"}
          </button>
          {form.id && (
            <button type="button" onClick={() => { setForm(emptyForm); setNote(null); }} className="rounded-lg border border-line px-4 py-2 text-sm text-muted transition hover:text-text">
              Cancel edit
            </button>
          )}
          {note && <p className="text-xs text-accent">{note}</p>}
        </div>
      </Card>

      <div className="mt-4 divide-y divide-line/60">
        {creators.map((creator) => (
          <div key={creator.id} className="flex flex-wrap items-center gap-3 py-3">
            <span className="min-w-40 flex-1 font-medium">{creator.name}</span>
            <span className="text-xs text-faint">{creator.categories.join(" · ")}</span>
            <span className="text-xs text-muted">Checked {creator.lastChecked}</span>
            <button type="button" onClick={() => edit(creator)} className="rounded-md border border-line px-3 py-1 text-xs text-muted transition hover:text-text">Edit</button>
          </div>
        ))}
        {creators.length === 0 && <p className="py-6 text-center text-sm text-faint">No creators added in Admin yet.</p>}
      </div>
    </section>
  );
}

function CodesPanel({ token }: { token: string }) {
  const [codes, setCodes] = useState<AccessCodeRow[]>([]);
  const [label, setLabel] = useState("");
  const [kind, setKind] = useState<"beta" | "referral">("beta");
  const [unlimited, setUnlimited] = useState(true);
  const [maxUses, setMaxUses] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await fetch(`/api/admin/codes?token=${encodeURIComponent(token)}`);
    if (!res.ok) return;
    const data = (await res.json()) as { codes: AccessCodeRow[] };
    setCodes(data.codes);
  }, [token]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const create = async () => {
    if (!label.trim() || busy) return;
    setBusy(true);
    setNote(null);
    try {
      const res = await fetch(`/api/admin/codes?token=${encodeURIComponent(token)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind,
          label,
          unlimitedBuilds: unlimited,
          maxUses: maxUses ? Number(maxUses) : null,
        }),
      });
      const data = (await res.json()) as { url?: string; error?: string };
      setNote(res.ok ? `Created: ${data.url}` : data.error ?? "Could not create that code.");
      if (res.ok) {
        setLabel("");
        await load();
      }
    } finally {
      setBusy(false);
    }
  };

  const toggle = async (code: string, active: boolean) => {
    await fetch(`/api/admin/codes?token=${encodeURIComponent(token)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, active }),
    });
    await load();
  };

  return (
    <section>
      <h2 className="text-xl font-semibold tracking-tight">Invite &amp; referral links</h2>
      <p className="mt-1 max-w-2xl text-sm text-muted">
        A <span className="text-text">beta</span> link opens the build tools before launch. A{" "}
        <span className="text-text">referral</span> link grants nothing but counts the traffic it sends,
        which is what a sponsored creator needs. Either can carry unlimited generations.
      </p>

      <Card className="mt-4 p-4">
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-52 flex-1">
            <label className="mb-1 block text-[0.65rem] font-bold uppercase tracking-wide text-faint">
              Label
            </label>
            <input
              value={label}
              onChange={(event) => setLabel(event.target.value)}
              placeholder="Beta wave 1, or a creator's name"
              className="w-full rounded-lg border border-line bg-white/[0.04] px-3 py-2 text-sm text-text outline-none focus:border-accent/50"
            />
          </div>
          <div>
            <label className="mb-1 block text-[0.65rem] font-bold uppercase tracking-wide text-faint">Kind</label>
            <select
              value={kind}
              onChange={(event) => setKind(event.target.value as "beta" | "referral")}
              className="rounded-lg border border-line bg-[#0e1322] px-2 py-2 text-sm text-text outline-none"
            >
              <option value="beta">Beta access</option>
              <option value="referral">Referral only</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-[0.65rem] font-bold uppercase tracking-wide text-faint">Max uses</label>
            <input
              value={maxUses}
              onChange={(event) => setMaxUses(event.target.value.replace(/\D/g, ""))}
              placeholder="∞"
              className="w-20 rounded-lg border border-line bg-white/[0.04] px-3 py-2 text-sm text-text outline-none focus:border-accent/50"
            />
          </div>
          <label className="flex items-center gap-2 py-2 text-sm text-muted">
            <input type="checkbox" checked={unlimited} onChange={(event) => setUnlimited(event.target.checked)} />
            Unlimited builds
          </label>
          <button
            onClick={create}
            disabled={!label.trim() || busy}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-bold text-black transition hover:opacity-90 disabled:opacity-40"
          >
            Create link
          </button>
        </div>
        {note && <p className="mt-2 break-all text-xs text-accent">{note}</p>}
      </Card>

      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[42rem] text-sm">
          <thead>
            <tr className="border-b border-line text-left text-[0.65rem] uppercase tracking-wide text-faint">
              <th className="py-2">Link</th>
              <th>Label</th>
              <th>Grants</th>
              <th className="text-right">Clicks</th>
              <th className="text-right">Claimed</th>
              <th className="text-right">Sign-ins</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {codes.map((row) => (
              <tr key={row.code} className={`border-b border-line/50 ${row.active ? "" : "opacity-45"}`}>
                <td className="py-2 font-mono text-xs text-text">/i/{row.code}</td>
                <td className="text-muted">{row.label}</td>
                <td className="text-xs text-muted">
                  {[row.grantsBeta ? "beta" : null, row.unlimitedBuilds ? "unlimited" : null]
                    .filter(Boolean).join(" · ") || "tracking only"}
                  {row.maxUses ? ` · max ${row.maxUses}` : ""}
                </td>
                <td className="text-right tabular-nums">{row.clicks}</td>
                <td className="text-right tabular-nums">{row.activations}</td>
                <td className="text-right tabular-nums">{row.signIns}</td>
                <td className="py-2 text-right">
                  <button
                    onClick={() => toggle(row.code, !row.active)}
                    className="rounded-md px-2 py-1 text-xs text-faint transition hover:text-text"
                  >
                    {row.active ? "Disable" : "Enable"}
                  </button>
                </td>
              </tr>
            ))}
            {codes.length === 0 && (
              <tr><td colSpan={7} className="py-6 text-center text-faint">No links yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function BestBuildsPanel({ token }: { token: string }) {
  const [builds, setBuilds] = useState<BestBuildRow[]>([]);
  const [form, setForm] = useState({
    championSlug: "", player: "", standing: "", items: "", boots: "", runes: "", note: "",
  });
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await fetch(`/api/admin/best-builds?token=${encodeURIComponent(token)}`);
    if (!res.ok) return;
    const data = (await res.json()) as { builds: BestBuildRow[] };
    setBuilds(data.builds);
  }, [token]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const save = async () => {
    if (!form.championSlug.trim() || !form.player.trim() || busy) return;
    setBusy(true);
    setNote(null);
    try {
      const res = await fetch(`/api/admin/best-builds?token=${encodeURIComponent(token)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      const data = (await res.json()) as { error?: string };
      setNote(res.ok ? `Saved ${form.championSlug}.` : data.error ?? "Could not save that.");
      if (res.ok) {
        setForm({ championSlug: "", player: "", standing: "", items: "", boots: "", runes: "", note: "" });
        await load();
      }
    } finally {
      setBusy(false);
    }
  };

  const remove = async (slug: string) => {
    await fetch(`/api/admin/best-builds?token=${encodeURIComponent(token)}&slug=${encodeURIComponent(slug)}`, {
      method: "DELETE",
    });
    await load();
  };

  const field = (key: keyof typeof form, label: string, placeholder: string, wide = false) => (
    <div className={wide ? "min-w-64 flex-[2]" : "min-w-40 flex-1"}>
      <label className="mb-1 block text-[0.65rem] font-bold uppercase tracking-wide text-faint">{label}</label>
      <input
        value={form[key]}
        onChange={(event) => setForm((current) => ({ ...current, [key]: event.target.value }))}
        placeholder={placeholder}
        className="w-full rounded-lg border border-line bg-white/[0.04] px-3 py-2 text-sm text-text outline-none focus:border-accent/50"
      />
    </div>
  );

  return (
    <section>
      <h2 className="text-xl font-semibold tracking-tight">Best-player builds</h2>
      <p className="mt-1 max-w-2xl text-sm text-muted">
        What the top player on a champion actually runs, typed in by hand. Shows on the leaderboard under
        that champion. Items and runes are comma-separated; items use slugs, runes use their display names.
      </p>

      <Card className="mt-4 p-4">
        <div className="flex flex-wrap gap-2">
          {field("championSlug", "Champion slug", "graves")}
          {field("player", "Player", "in-game name")}
          {field("standing", "Standing", "Rank 1 EU")}
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          {field("items", "Items", "youmuus-ghostblade, infinity-edge, ...", true)}
          {field("boots", "Boots", "boots-of-dynamism")}
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          {field("runes", "Runes", "Conqueror, Brutal, ...", true)}
          {field("note", "Note", "how they play it", true)}
        </div>
        <button
          onClick={save}
          disabled={!form.championSlug.trim() || !form.player.trim() || busy}
          className="mt-3 rounded-lg bg-accent px-4 py-2 text-sm font-bold text-black transition hover:opacity-90 disabled:opacity-40"
        >
          Save build
        </button>
        {note && <p className="mt-2 text-xs text-accent">{note}</p>}
      </Card>

      <div className="mt-4 divide-y divide-line/60">
        {builds.map((build) => (
          <div key={build.championSlug} className="flex items-center gap-3 py-2.5">
            <span className="w-32 shrink-0 truncate text-sm font-medium">{build.championSlug}</span>
            <span className="w-40 shrink-0 truncate text-sm text-muted">{build.player}</span>
            <span className="min-w-0 flex-1 truncate text-xs text-faint">
              {[...build.items, build.boots].filter(Boolean).join(", ")}
            </span>
            <button
              onClick={() => remove(build.championSlug)}
              className="shrink-0 rounded-md px-2 py-1 text-xs text-faint transition hover:bg-bad/15 hover:text-bad"
            >
              Delete
            </button>
          </div>
        ))}
        {builds.length === 0 && <p className="py-6 text-center text-sm text-faint">Nothing recorded yet.</p>}
      </div>
    </section>
  );
}
