import { NextResponse } from "next/server";
import { KV_CONFIGURED, kvGetNumber, kvList } from "@/lib/kv";
import { FEEDBACK_REASON_KEYS } from "@/lib/feedback-options";
import { TRACKED_EVENTS, eventSummary } from "@/lib/stats";

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
      recent: notes.map((entry) => {
        try {
          return JSON.parse(entry) as unknown;
        } catch {
          return entry;
        }
      }),
    },
  });
}
