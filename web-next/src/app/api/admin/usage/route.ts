import { NextResponse } from "next/server";
import { KV_CONFIGURED, kvGetNumber, kvList, kvSetCount } from "@/lib/kv";
import { FEEDBACK_REASON_KEYS } from "@/lib/feedback-options";
import { ACTOR_ACTIONS, TRACKED_EVENTS, actorSummary, cohortSummary, engagementSummary, eventSummary } from "@/lib/stats";

/**
 * GET /api/admin/usage?token=... -- the internal read-out.
 *
 * Answers the question the counters exist for: are people using the build
 * tools, or only reading the tier list? Returns every tracked event with its
 * lifetime total, today, and the last 7 days, plus the feedback tally.
 *
 * Guarded by ADMIN_TOKEN. With no token configured the route stays closed
 * rather than defaulting to public, because it is a usage dashboard.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const expected = process.env.ADMIN_TOKEN ?? "";
  const provided = new URL(request.url).searchParams.get("token") ?? "";
  if (!expected || provided !== expected) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }

  const events = await Promise.all(TRACKED_EVENTS.map((event) => eventSummary(event)));
  const [up, down] = await Promise.all([
    kvGetNumber("feedback:build:up"),
    kvGetNumber("feedback:build:down"),
  ]);
  const reasonCounts = await Promise.all(
    FEEDBACK_REASON_KEYS.map(async (reason) => [reason, await kvGetNumber(`feedback:build:reason:${reason}`)] as const),
  );
  const notes = await kvList("feedback:build:log", 50);
  const [uniqueAccounts, signInsLog, engagement] = await Promise.all([
    kvSetCount("auth:google:subs"),
    kvList("auth:signins:log", 30),
    engagementSummary(7),
  ]);
  const cohorts = await cohortSummary(6);
  const actors = await Promise.all(ACTOR_ACTIONS.map((action) => actorSummary(action)));
  const parse = (entry: string) => {
    try { return JSON.parse(entry) as unknown; } catch { return entry; }
  };

  return NextResponse.json({
    storage: KV_CONFIGURED ? "kv" : "memory (not persistent)",
    events: Object.fromEntries(
      events.map((summary) => [
        summary.event,
        { total: summary.total, today: summary.today, last7Days: summary.windowTotal },
      ]),
    ),
    feedback: {
      up,
      down,
      reasons: Object.fromEntries(reasonCounts),
      recent: notes.map(parse),
    },
    accounts: {
      // Unique Google accounts ever signed in (tracked from 2026-08-07; the
      // signed_in EVENT total goes further back but counts repeat sign-ins).
      unique: uniqueAccounts,
      recentSignIns: signInsLog.map(parse),
    },
    // Per-day generation engagement (tracked from 2026-08-08): distinct
    // generators, new vs returning, and how deep into the daily allowance
    // each person went. Days before the deploy read as zeros, not as truth.
    engagement,
    // Weekly cohorts: of the people who first generated in week W, how many
    // came back within 1 / 7 / 30 days. The question retention actually asks.
    cohorts,
    // Distinct PEOPLE who saved / shared (tracked from 2026-08-10), against
    // the build_saved / build_shared event totals above which count actions.
    // The gap between the two is how much repeat behaviour there is.
    actors: Object.fromEntries(actors.map((summary) => [summary.action, summary])),
  });
}
