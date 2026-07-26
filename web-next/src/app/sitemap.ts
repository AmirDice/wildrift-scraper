import type { MetadataRoute } from "next";
import { getChampions, site } from "@/lib/data";
import { getPosts } from "@/lib/blog";
import { BUILD_TOOLS_LIVE } from "@/lib/flags";

const BASE = "https://wrtruemeta.com";

/**
 * When the champion data was actually collected.
 *
 * This used to be `new Date()` for every URL, which told Google that all 138
 * champion pages changed on every deploy. A crawler that has been lied to about
 * lastmod starts ignoring lastmod, and these pages need Google to believe it:
 * 135 of them sit in "Discovered - currently not indexed", which is a crawl
 * priority problem, not a markup problem.
 */
function dataDate(): Date {
  const parsed = site.collectedOn ? new Date(site.collectedOn) : null;
  return parsed && !Number.isNaN(parsed.getTime()) ? parsed : new Date();
}

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  const collected = dataDate();
  const staticPages: MetadataRoute.Sitemap = [
    { url: `${BASE}/`, lastModified: now, changeFrequency: "weekly", priority: 1 },
    { url: `${BASE}/tier-list`, lastModified: now, changeFrequency: "weekly", priority: 0.95 },
    { url: `${BASE}/tier-list/china`, lastModified: collected, changeFrequency: "weekly", priority: 0.85 },
    { url: `${BASE}/champions`, lastModified: now, changeFrequency: "weekly", priority: 0.9 },
    { url: `${BASE}/meta`, lastModified: now, changeFrequency: "weekly", priority: 0.88 },
    { url: `${BASE}/global`, lastModified: now, changeFrequency: "weekly", priority: 0.85 },
    { url: `${BASE}/rising`, lastModified: now, changeFrequency: "weekly", priority: 0.85 },
    { url: `${BASE}/ranks`, lastModified: now, changeFrequency: "weekly", priority: 0.85 },
    { url: `${BASE}/compare`, lastModified: now, changeFrequency: "weekly", priority: 0.7 },
    { url: `${BASE}/consistency`, lastModified: now, changeFrequency: "weekly", priority: 0.7 },
    // /build and /counter are only listed once the Build Optimizer launches.
    ...(BUILD_TOOLS_LIVE
      ? ([
          { url: `${BASE}/build`, lastModified: now, changeFrequency: "weekly" as const, priority: 0.9 },
          { url: `${BASE}/counter`, lastModified: now, changeFrequency: "weekly" as const, priority: 0.9 },
        ])
      : []),
    { url: `${BASE}/items`, lastModified: now, changeFrequency: "monthly", priority: 0.7 },
    { url: `${BASE}/runes-spells`, lastModified: now, changeFrequency: "monthly", priority: 0.7 },
    { url: `${BASE}/news`, lastModified: now, changeFrequency: "daily", priority: 0.75 },
    { url: `${BASE}/blog`, lastModified: now, changeFrequency: "weekly", priority: 0.8 },
    { url: `${BASE}/albums`, lastModified: now, changeFrequency: "monthly", priority: 0.5 },
    { url: `${BASE}/creators`, lastModified: now, changeFrequency: "monthly", priority: 0.6 },
    { url: `${BASE}/champion-changes`, lastModified: now, changeFrequency: "weekly", priority: 0.7 },
    { url: `${BASE}/changes-report`, lastModified: now, changeFrequency: "weekly", priority: 0.75 },
    { url: `${BASE}/leaderboard`, lastModified: now, changeFrequency: "weekly", priority: 0.7 },
    { url: `${BASE}/methodology`, lastModified: now, changeFrequency: "monthly", priority: 0.6 },
  ];
  // Champion pages change when the scrape does, roughly twice a month, and
  // they are the pages Google has not got round to crawling yet: an honest
  // lastmod and a priority above the secondary tools is the signal we have.
  const championPages: MetadataRoute.Sitemap = getChampions().map((c) => ({
    url: `${BASE}/champions/${c.slug}`,
    lastModified: collected,
    changeFrequency: "monthly",
    priority: 0.8,
  }));
  const blogPages: MetadataRoute.Sitemap = getPosts().map((post) => ({
    url: `${BASE}/blog/${post.slug}`,
    lastModified: new Date(post.date),
    changeFrequency: "monthly",
    priority: 0.65,
  }));
  // Per-champion build pages are omitted while the optimizer is "coming soon".
  return [...staticPages, ...championPages, ...blogPages];
}
