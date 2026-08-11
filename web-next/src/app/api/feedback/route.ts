import { NextResponse, after } from "next/server";
import { FEEDBACK_REASON_KEYS } from "@/lib/feedback-options";
import { recordFeedback, trackEvent, type BuildFeedback } from "@/lib/stats";

/**
 * POST { verdict, reasons[], note, champion } -- "was this build helpful?" on a
 * generated build. Reasons come from a fixed list so they aggregate; the note
 * is free text, trimmed hard and kept in a capped log.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const REASONS = new Set<string>(FEEDBACK_REASON_KEYS);

export async function POST(request: Request) {
  let body: { verdict?: unknown; reasons?: unknown; note?: unknown; champion?: unknown };
  try {
    body = (await request.json()) as typeof body;
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }

  const verdict = body.verdict === "up" ? "up" : body.verdict === "down" ? "down" : null;
  if (!verdict) return NextResponse.json({ error: "verdict must be up or down" }, { status: 400 });

  const reasons = Array.isArray(body.reasons)
    ? body.reasons.filter((reason): reason is string => typeof reason === "string" && REASONS.has(reason)).slice(0, 4)
    : [];
  const note = typeof body.note === "string" ? body.note.trim().slice(0, 500) : "";
  const champion = typeof body.champion === "string" ? body.champion.slice(0, 40) : "";

  const feedback: BuildFeedback = {
    verdict,
    reasons,
    ...(note ? { note } : {}),
    ...(champion ? { champion } : {}),
    at: new Date().toISOString(),
  };
  await recordFeedback(feedback);
  after(() => trackEvent("build_feedback"));

  return NextResponse.json({ ok: true });
}
