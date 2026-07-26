import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { SESSION_COOKIE, readSession } from "@/lib/session";
import { deleteAlbum, getAlbum, updateAlbum } from "@/lib/albums";

/**
 * GET    -> one album. Unlisted, not private: anyone with the id can read it,
 *           which is what makes an album shareable.
 * PATCH  -> rename / re-describe (owner only).
 * DELETE -> remove it (owner only).
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(_request: Request, context: RouteContext<"/api/albums/[id]">) {
  const { id } = await context.params;
  const album = await getAlbum(id);
  if (!album) return NextResponse.json({ error: "album not found" }, { status: 404 });

  const store = await cookies();
  const user = readSession(store.get(SESSION_COOKIE)?.value);
  return NextResponse.json(
    { album, isOwner: user?.sub === album.ownerSub },
    // The album itself is shareable, but `isOwner` is viewer-specific, so the
    // response as a whole is not cacheable by anything shared.
    { headers: { "Cache-Control": "private, no-store, max-age=0" } },
  );
}

export async function PATCH(request: Request, context: RouteContext<"/api/albums/[id]">) {
  const { id } = await context.params;
  const store = await cookies();
  const user = readSession(store.get(SESSION_COOKIE)?.value);
  if (!user) return NextResponse.json({ error: "sign in first" }, { status: 401 });

  let body: { title?: unknown; description?: unknown };
  try {
    body = (await request.json()) as typeof body;
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }

  const album = await updateAlbum(id, user.sub, {
    title: typeof body.title === "string" ? body.title : undefined,
    description: typeof body.description === "string" ? body.description : undefined,
  });
  if (!album) return NextResponse.json({ error: "not your album" }, { status: 403 });
  return NextResponse.json({ album });
}

export async function DELETE(_request: Request, context: RouteContext<"/api/albums/[id]">) {
  const { id } = await context.params;
  const store = await cookies();
  const user = readSession(store.get(SESSION_COOKIE)?.value);
  if (!user) return NextResponse.json({ error: "sign in first" }, { status: 401 });

  const ok = await deleteAlbum(id, user.sub);
  if (!ok) return NextResponse.json({ error: "not your album" }, { status: 403 });
  return NextResponse.json({ ok: true });
}
