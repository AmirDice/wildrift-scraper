import { NextResponse } from "next/server";
import itemsCatalogue from "@/data/items.json";
import { site, regionBoard } from "@/lib/data";
import { buildsByServer } from "@/lib/ladder-build";
import { toServerBuild } from "@/lib/server-build";

/**
 * What the top 50 build for one champion, per server.
 *
 * An endpoint rather than an import, because the caller is the Build Studio,
 * which is a Client Component that changes champion without a navigation. The
 * per-server records are ~100KB each and the studio needs one champion's worth
 * at a time, so they stay on the server and this hands over the six items it
 * actually renders.
 *
 * The champion pages do not use this: they are server-rendered and read the
 * same data directly.
 */

const ITEMS = new Map(
  (itemsCatalogue as { slug: string; name: string; icon: string }[]).map((i) => [i.slug, i]),
);

function item(slug: string) {
  const hit = ITEMS.get(slug);
  return {
    slug,
    name: hit?.name ?? slug.replace(/-/g, " "),
    icon: hit?.icon ?? `/items/${slug}.webp`,
  };
}

export function GET(request: Request) {
  const champion = new URL(request.url).searchParams.get("champion")?.trim();
  if (!champion) {
    return NextResponse.json({ error: "champion is required" }, { status: 400 });
  }
  const builds = buildsByServer(champion);
  return NextResponse.json(
    {
      champion,
      builds: {
        eu: toServerBuild(builds.eu, item),
        na: toServerBuild(builds.na, item),
        cn: toServerBuild(builds.cn, item),
      },
      collected: {
        eu: site.collectedOn ?? undefined,
        na: regionBoard("NA").collectedOn ?? undefined,
      },
    },
    // The boards move once a patch; an hour of caching costs nothing and keeps
    // champion-switching in the studio instant.
    { headers: { "cache-control": "public, max-age=3600, stale-while-revalidate=86400" } },
  );
}
