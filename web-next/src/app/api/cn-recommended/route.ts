import { NextResponse } from "next/server";
import { getChampionLoadouts, recommendedLoadout, type LoadoutTab } from "@/lib/cn-loadouts";

/**
 * GET /api/cn-recommended?champion=riven
 *
 * The champion page's "Recommended" China loadout, per lane, for the Build
 * Studio: the core, rune page and boots with the best balance of win rate
 * and pick rate (lib/loadout-score.ts). The full loadout file is 1.4 MB, too
 * much to ship to a client component, so the studio asks for one champion.
 */
export const runtime = "nodejs";

type Entity = { name: string; icon: string; slug?: string };

function pick(tab: LoadoutTab | undefined) {
  // The weekly pick, and no boots while China's boots tab is stale.
  const row = recommendedLoadout(tab);
  if (!row) return null;
  return {
    winRate: row.winRate,
    pickRate: row.pickRate,
    entities: row.entities.map((entity): Entity => ({
      name: entity.name,
      icon: entity.icon,
      // Item links carry the slug ("/items#infinity-edge"); the Lab wants it.
      slug: entity.href?.startsWith("/items#") ? entity.href.slice("/items#".length) : undefined,
    })),
  };
}

export async function GET(request: Request) {
  const slug = new URL(request.url).searchParams.get("champion") ?? "";
  if (!/^[a-z0-9-]{1,40}$/.test(slug)) return NextResponse.json({ lanes: [] });
  const lanes = getChampionLoadouts(slug).map((lane) => ({
    lane: lane.lane,
    capturedAt: lane.capturedAt,
    core: pick(lane.tabs.items),
    runes: pick(lane.tabs.runes),
    boots: pick(lane.tabs.boots),
  })).filter((lane) => lane.core || lane.runes);
  return NextResponse.json({ lanes }, { headers: { "Cache-Control": "public, max-age=3600" } });
}
