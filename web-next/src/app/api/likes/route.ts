import { NextResponse } from "next/server";
import { addLike, likeCount, trackEvent } from "@/lib/stats";

/**
 * Likes on the curated recommended builds.
 *
 *   GET  /api/likes?id=aatrox:standard   -> { count }
 *   POST { id, liked }                   -> { count }
 *
 * Ids are `${championSlug}:${variant}`. There is no per-user like ledger: the
 * client remembers its own likes in localStorage, which is enough for a signal
 * this soft ("does anyone rate this build?") and keeps the store tiny.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ID_PATTERN = /^[a-z0-9-]+:[a-z0-9-]+$/i;

export async function GET(request: Request) {
  const id = new URL(request.url).searchParams.get("id") ?? "";
  if (!ID_PATTERN.test(id)) return NextResponse.json({ error: "bad id" }, { status: 400 });
  return NextResponse.json(
    { count: await likeCount(`build:${id}`) },
    {
      // Every recommended build asks for this on mount, so a browsing session
      // fires one request per build viewed. A minute of shared caching absorbs
      // that; the liker's own count updates optimistically either way.
      headers: { "Cache-Control": "public, s-maxage=60, stale-while-revalidate=300" },
    },
  );
}

export async function POST(request: Request) {
  let body: { id?: unknown; liked?: unknown };
  try {
    body = (await request.json()) as typeof body;
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }
  const id = typeof body.id === "string" ? body.id : "";
  if (!ID_PATTERN.test(id)) return NextResponse.json({ error: "bad id" }, { status: 400 });

  const liked = body.liked !== false;
  const count = await addLike(`build:${id}`, liked ? 1 : -1);
  if (liked) void trackEvent("build_liked");

  return NextResponse.json({ count });
}
