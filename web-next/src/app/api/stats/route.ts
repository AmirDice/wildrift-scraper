import { NextResponse } from "next/server";
import { eventSummary } from "@/lib/stats";

/**
 * GET -- public usage counters for the home page.
 *
 * Cached at the edge for a minute. It was an hour, which was right when the
 * only caller was the home page and read it once on load -- but the build page
 * now refreshes the figure while someone sits on it, and a client polling a
 * value the edge holds for an hour is just asking the same question sixty times
 * for the same answer.
 *
 * The edge cache still does the real work: the KV read happens once a minute no
 * matter how many people are looking, so this scales with time rather than with
 * traffic.
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
        "Cache-Control": "public, s-maxage=60, stale-while-revalidate=86400",
      },
    },
  );
}
