import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { clientIp, quotaIdentity } from "@/lib/quota";
import { SESSION_COOKIE, readSession } from "@/lib/session";
import { isTrackedEvent, recordActor, trackEvent } from "@/lib/stats";

/**
 * POST { event } -- records one product-usage event.
 *
 * Used to answer "is anyone actually generating and saving builds, or do they
 * only read the tier list?". Only names in TRACKED_EVENTS are accepted.
 *
 * Saves and shares additionally file the actor into a set, because the plain
 * counter cannot distinguish ten people sharing once from one person sharing
 * ten times, and only the first of those is a growth signal. The identity is
 * the same person-ish unit the quota uses -- Google sub, else hashed IP -- so
 * no raw identifier is written here either.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ACTOR_EVENTS = {
  build_saved: "saved",
  build_shared: "shared",
} as const;

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

  const action = ACTOR_EVENTS[event as keyof typeof ACTOR_EVENTS];
  if (action) {
    const store = await cookies();
    const user = readSession(store.get(SESSION_COOKIE)?.value);
    void recordActor(action, quotaIdentity(user, clientIp(request)));
  }
  return NextResponse.json({ ok: true });
}
