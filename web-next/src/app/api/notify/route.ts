import { NextResponse, after } from "next/server";
import { clientIp } from "@/lib/quota";
import { kvIncr } from "@/lib/kv";
import { normaliseEmail, normaliseTopics, subscribe } from "@/lib/notify";
import { trackEvent } from "@/lib/stats";

/**
 * POST { email, topics[], source } -- join the notify list.
 *
 * Rate limited per IP rather than per address, because the address is the
 * thing being forged. Ten a day is far above any honest use (a person signs
 * up once) and far below what makes a scripted flood worth running.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const PER_IP_DAILY = 10;
const DAY_SECONDS = 86_400;

export async function POST(request: Request) {
  let body: { email?: unknown; topics?: unknown; source?: unknown };
  try {
    body = (await request.json()) as typeof body;
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }

  const email = normaliseEmail(body.email);
  if (!email) {
    return NextResponse.json({ error: "That does not look like an email address." }, { status: 400 });
  }

  const day = new Date().toISOString().slice(0, 10);
  const used = await kvIncr(`notify:ip:${day}:${clientIp(request)}`, 1, DAY_SECONDS);
  if (used > PER_IP_DAILY) {
    return NextResponse.json(
      { error: "Too many signups from this connection today." },
      { status: 429 },
    );
  }

  const topics = normaliseTopics(body.topics);
  const source = typeof body.source === "string" ? body.source : "unknown";
  const result = await subscribe(email, topics, source);

  // A storage failure is reported as one. The form's whole job is a promise to
  // come back to someone, and a green tick over a dropped write is a lie that
  // only surfaces months later when the mail never arrives.
  if (!result.ok) {
    return NextResponse.json(
      { error: "The list is not reachable right now. Try again later." },
      { status: 503 },
    );
  }

  after(() => trackEvent("notify_signup"));
  return NextResponse.json({ ok: true, existing: result.existing, topics });
}
