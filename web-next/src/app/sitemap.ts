import type { MetadataRoute } from "next";
import { getChampions } from "@/lib/data";
import { buildChampions } from "@/lib/builds";

const BASE = "https://wrtruemeta.com";

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  const staticPages: MetadataRoute.Sitemap = [
    { url: `${BASE}/`, lastModified: now, changeFrequency: "weekly", priority: 1 },
    { url: `${BASE}/tier-list`, lastModified: now, changeFrequency: "weekly", priority: 0.95 },
    { url: `${BASE}/champions`, lastModified: now, changeFrequency: "weekly", priority: 0.9 },
    { url: `${BASE}/global`, lastModified: now, changeFrequency: "weekly", priority: 0.85 },
    { url: `${BASE}/compare`, lastModified: now, changeFrequency: "weekly", priority: 0.7 },
    { url: `${BASE}/consistency`, lastModified: now, changeFrequency: "weekly", priority: 0.7 },
    { url: `${BASE}/build`, lastModified: now, changeFrequency: "weekly", priority: 0.8 },
    { url: `${BASE}/news`, lastModified: now, changeFrequency: "daily", priority: 0.75 },
    { url: `${BASE}/leaderboard`, lastModified: now, changeFrequency: "weekly", priority: 0.7 },
    { url: `${BASE}/methodology`, lastModified: now, changeFrequency: "monthly", priority: 0.6 },
  ];
  const championPages: MetadataRoute.Sitemap = getChampions().map((c) => ({
    url: `${BASE}/champions/${c.slug}`,
    lastModified: now,
    changeFrequency: "weekly",
    priority: 0.7,
  }));
  const buildPages: MetadataRoute.Sitemap = buildChampions().map((b) => ({
    url: `${BASE}/build/${b.slug}`,
    lastModified: now,
    changeFrequency: "weekly",
    priority: 0.65,
  }));
  return [...staticPages, ...championPages, ...buildPages];
}
