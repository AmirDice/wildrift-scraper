import { NextResponse } from "next/server";
import { isTrackedEvent, trackEvent } from "@/lib/stats";

/**
 * POST { event } -- records one product-usage event.
 *
 * Used to answer "is anyone actually generating and saving builds, or do they
 * only read the tier list?". Only names in TRACKED_EVENTS are accepted, and no
 * per-user identifier is written: these are plain counters.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  let event: unknown;
  try {
    ({ event } = (await request.json()) as { event?: unknown });
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }
  if (!isTrackedEvent(event)) {
    return NextResponse.json({ error: "unknown event" }, { status: 400 });
  }
  await trackEvent(event);
  return NextResponse.json({ ok: true });
}
