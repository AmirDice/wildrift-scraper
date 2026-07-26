import { NextResponse } from "next/server";
import { eventSummary } from "@/lib/stats";

/**
 * GET -- public usage counters for the home page.
 *
 * Deliberately cached at the edge for an hour: the "builds generated" number is
 * a live figure, but it does not need to be live to the second, and hitting KV
 * on every home-page view would be a needless cost on the busiest route.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const [builds, counters, saved] = await Promise.all([
    eventSummary("build_generated"),
    eventSummary("counter_generated"),
    eventSummary("build_saved"),
  ]);

  return NextResponse.json(
    {
      buildsGenerated: builds.total + counters.total,
      buildsGeneratedToday: builds.today + counters.today,
      buildsGeneratedThisWeek: builds.windowTotal + counters.windowTotal,
      buildsSaved: saved.total,
    },
    {
      headers: {
        "Cache-Control": "public, s-maxage=3600, stale-while-revalidate=86400",
      },
    },
  );
}
