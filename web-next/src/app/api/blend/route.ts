import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { SESSION_COOKIE, readSession } from "@/lib/session";
import { createBlend, listBlends } from "@/lib/albums";

/**
 * GET  -> blends this player is part of.
 * POST -> starts a new one and returns its code, which is the invite.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const store = await cookies();
  const user = readSession(store.get(SESSION_COOKIE)?.value);
  if (!user) return NextResponse.json({ error: "sign in first" }, { status: 401 });
  return NextResponse.json(
    { blends: await listBlends(user.sub) },
    { headers: { "Cache-Control": "private, no-store, max-age=0" } },
  );
}

export async function POST() {
  const store = await cookies();
  const user = readSession(store.get(SESSION_COOKIE)?.value);
  if (!user) return NextResponse.json({ error: "sign in first" }, { status: 401 });
  return NextResponse.json({ blend: await createBlend(user) });
}
