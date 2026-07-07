import type { MetadataRoute } from "next";
import { getChampions } from "@/lib/data";

const BASE = "https://wrtruemeta.com";

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  const staticPages: MetadataRoute.Sitemap = [
    { url: `${BASE}/`, lastModified: now, changeFrequency: "weekly", priority: 1 },
    { url: `${BASE}/tier-list`, lastModified: now, changeFrequency: "weekly", priority: 0.95 },
    { url: `${BASE}/champions`, lastModified: now, changeFrequency: "weekly", priority: 0.9 },
    { url: `${BASE}/global`, lastModified: now, changeFrequency: "weekly", priority: 0.85 },
    { url: `${BASE}/rising`, lastModified: now, changeFrequency: "weekly", priority: 0.85 },
    { url: `${BASE}/ranks`, lastModified: now, changeFrequency: "weekly", priority: 0.85 },
    { url: `${BASE}/compare`, lastModified: now, changeFrequency: "weekly", priority: 0.7 },
    { url: `${BASE}/consistency`, lastModified: now, changeFrequency: "weekly", priority: 0.7 },
    { url: `${BASE}/build`, lastModified: now, changeFrequency: "monthly", priority: 0.4 },
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
  // Per-champion build pages are omitted while the optimizer is "coming soon".
  return [...staticPages, ...championPages];
}
