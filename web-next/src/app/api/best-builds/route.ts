import { NextResponse } from "next/server";
import { getBestBuild } from "@/lib/best-builds";

/**
 * GET ?slug=graves -- the hand-recorded build of the best player on a champion,
 * or null when none has been recorded yet.
 *
 * Public and cacheable: these change only when someone types a new one in, so
 * a long shared cache costs nothing and the leaderboard asks for it on every
 * champion switch.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const slug = (new URL(request.url).searchParams.get("slug") ?? "").toLowerCase();
  if (!/^[a-z0-9-]{1,40}$/.test(slug)) {
    return NextResponse.json({ error: "bad slug" }, { status: 400 });
  }
  return NextResponse.json(
    { build: await getBestBuild(slug) },
    { headers: { "Cache-Control": "public, s-maxage=600, stale-while-revalidate=3600" } },
  );
}
