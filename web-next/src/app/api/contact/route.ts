import crypto from "node:crypto";
import { NextResponse } from "next/server";
import { clientIp } from "@/lib/quota";
import { kvIncr, kvPushCapped } from "@/lib/kv";

/**
 * POST /api/contact -- the contact form.
 *
 * Messages land in KV (`contact:messages`) and are read in the admin console,
 * so the site never has to publish an email address. A hidden field catches
 * form-filling bots, and each hashed IP may send five messages an hour.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const CONTACT_TOPICS = ["data", "builds", "business", "other"] as const;
const LIMIT_PER_HOUR = 5;

const clip = (value: unknown, max: number) =>
  typeof value === "string" ? value.trim().slice(0, max) : "";

export async function POST(request: Request) {
  let body: Record<string, unknown>;
  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "Could not read the message." }, { status: 400 });
  }

  // Honeypot: a field people never see. Pretend success so bots move on.
  if (clip(body.website, 200)) return NextResponse.json({ ok: true });

  const message = clip(body.message, 4000);
  const email = clip(body.email, 200);
  const name = clip(body.name, 100);
  const topic = CONTACT_TOPICS.includes(body.topic as (typeof CONTACT_TOPICS)[number])
    ? (body.topic as string) : "other";
  if (message.length < 10) {
    return NextResponse.json({ error: "Please write a little more so we can help." }, { status: 400 });
  }
  if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return NextResponse.json({ error: "That email address does not look right." }, { status: 400 });
  }

  const ipHash = crypto.createHash("sha256").update(clientIp(request)).digest("hex").slice(0, 20);
  const sent = await kvIncr(`contact:rate:${ipHash}`, 1, 3600);
  if (sent > LIMIT_PER_HOUR) {
    return NextResponse.json({ error: "Too many messages from this connection. Please try again in an hour." }, { status: 429 });
  }

  await kvPushCapped("contact:messages", JSON.stringify({
    at: new Date().toISOString(), topic, name, email, message,
  }), 500);
  return NextResponse.json({ ok: true });
}
