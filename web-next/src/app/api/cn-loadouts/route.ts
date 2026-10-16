import { NextResponse } from "next/server";
import { getChampionLoadouts } from "@/lib/cn-loadouts";

/**
 * GET /api/cn-loadouts?champion=riven
 *
 * One champion's China Legendary loadouts (every core, rune page, boots,
 * spell pair and matchup with win and pick rates), for the Build Studio's
 * Ranked Builds tab. The whole file is 1.4 MB; one champion is ~10 KB.
 */
export const runtime = "nodejs";

export async function GET(request: Request) {
  const slug = new URL(request.url).searchParams.get("champion") ?? "";
  if (!/^[a-z0-9-]{1,40}$/.test(slug)) return NextResponse.json({ lanes: [] });
  return NextResponse.json(
    { lanes: getChampionLoadouts(slug) },
    { headers: { "Cache-Control": "public, max-age=3600" } },
  );
}
