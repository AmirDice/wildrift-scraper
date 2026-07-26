import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { SESSION_COOKIE, readSession } from "@/lib/session";
import { createAlbum, listAlbums } from "@/lib/albums";

/**
 * GET  -> the signed-in player's albums.
 * POST { title, description } -> creates one.
 *
 * Albums belong to a Google account, so both halves require a session.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const store = await cookies();
  const user = readSession(store.get(SESSION_COOKIE)?.value);
  if (!user) return NextResponse.json({ error: "sign in first" }, { status: 401 });
  return NextResponse.json(
    { albums: await listAlbums(user.sub) },
    // Per-account content: must never sit in a shared cache.
    { headers: { "Cache-Control": "private, no-store, max-age=0" } },
  );
}

export async function POST(request: Request) {
  const store = await cookies();
  const user = readSession(store.get(SESSION_COOKIE)?.value);
  if (!user) return NextResponse.json({ error: "sign in first" }, { status: 401 });

  let body: { title?: unknown; description?: unknown };
  try {
    body = (await request.json()) as typeof body;
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }
  const title = typeof body.title === "string" ? body.title : "";
  const description = typeof body.description === "string" ? body.description : undefined;

  const result = await createAlbum(user, title, description);
  if ("error" in result) return NextResponse.json(result, { status: 409 });
  return NextResponse.json({ album: result });
}
