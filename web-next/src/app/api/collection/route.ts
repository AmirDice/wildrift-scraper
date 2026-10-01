import { NextResponse } from "next/server";
import { getCollectionState } from "@/lib/collection";

/**
 * Where each region's data collection has got to.
 *
 *   GET /api/collection  ->  { regions: [...], active: bool }
 *
 * Public and unauthenticated: it says when the numbers on the page were
 * measured, which is exactly the thing a visitor should be able to check
 * without asking. It exposes no player data and no credentials.
 *
 * Deliberately NOT cached at the edge. The whole point of the bar in the
 * navbar is that it moves while a run is in flight, and a 60 second CDN cache
 * would make it lurch in minute-long steps. The read is one KV GET plus three
 * dates from files already in the bundle, so the cost of being honest here is
 * negligible. `no-store` also stops a stale "running" state outliving the run
 * that produced it.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const state = await getCollectionState();
    return NextResponse.json(state, {
      headers: { "cache-control": "no-store" },
    });
  } catch {
    // A failure here must not surface as a broken navbar. An empty payload
    // makes the component render nothing at all, which is the right amount
    // of noise for a decorative-but-informative strip.
    return NextResponse.json({ regions: [], active: false }, {
      status: 200,
      headers: { "cache-control": "no-store" },
    });
  }
}
