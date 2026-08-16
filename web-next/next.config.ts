import type { NextConfig } from "next";

/**
 * Caching policy for everything Next does not fingerprint itself.
 *
 * Next hashes its own build output (/_next/static) and caches it forever. What
 * it does NOT hash is /public, and that is where almost all of this site's
 * bytes live: 235 item icons and 705 ability icons, requested on nearly every
 * page of the build tools. Served with the default policy they are revalidated
 * on every navigation, which is a round trip per icon for no reason.
 *
 * These files are content-stable between deploys but are NOT immutable (an item
 * icon can be replaced when Riot reworks an item), so the rule is: let the CDN
 * hold them for a long time, let browsers hold them for a day, and allow stale
 * responses while a fresh copy is fetched. A deploy that changes an icon shows
 * the new one within a day, and nothing ever serves a permanently wrong asset.
 */
const IMAGE_CACHE = "public, max-age=86400, s-maxage=31536000, stale-while-revalidate=86400";

const nextConfig: NextConfig = {
  // Pin the workspace root so Next doesn't pick up the stray lockfile in the
  // user's home directory when inferring the project root.
  turbopack: {
    root: __dirname,
  },

  async redirects() {
    return [
      {
        // www and the apex both served a full 200 copy of the site, so Google
        // was crawling two complete duplicates of every page and splitting the
        // ranking signals between them. The apex wins because every canonical,
        // the sitemap and metadataBase already point there.
        //
        // Vercel's domain settings can do this too; keeping it in code means it
        // survives a project being re-created or a domain being re-added.
        source: "/:path*",
        has: [{ type: "host", value: "www.wrtruemeta.com" }],
        destination: "https://wrtruemeta.com/:path*",
        permanent: true,
      },
      {
        // The Patch 7.2 slides and the Season 22 recap were removed
        // 2026-08-16; both were indexed and linked from the nav, so their
        // URLs land on the Balance Report -- the surviving page that answers
        // the same question (what changed, who won, who lost).
        source: "/patch",
        destination: "/champion-changes",
        permanent: true,
      },
      {
        source: "/recap",
        destination: "/movers",
        permanent: true,
      },
    ];
  },

  async headers() {
    return [
      {
        // Champion, item, rune and ability art.
        source: "/:dir(items|abilities)/:path*",
        headers: [{ key: "Cache-Control", value: IMAGE_CACHE }],
      },
      {
        source: "/:file(ionia.jpg|ionia1.jpg|ionia2.jpg|season_bg.jpg|logo.png|ashensamira.png)",
        headers: [{ key: "Cache-Control", value: IMAGE_CACHE }],
      },
      {
        // The leaderboard payload changes only when the scraper runs, which is
        // twice a month; an hour of CDN caching costs nothing and saves a
        // full re-download on every leaderboard visit.
        source: "/players.json",
        headers: [{ key: "Cache-Control", value: "public, max-age=0, s-maxage=3600, stale-while-revalidate=86400" }],
      },
    ];
  },
};

export default nextConfig;
