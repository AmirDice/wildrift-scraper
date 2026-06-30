import type { MetadataRoute } from "next";
import { getChampions } from "@/lib/data";

const BASE = "https://wrtruemeta.com";

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  const staticPages: MetadataRoute.Sitemap = [
    { url: `${BASE}/`, lastModified: now, changeFrequency: "weekly", priority: 1 },
    { url: `${BASE}/tier-list`, lastModified: now, changeFrequency: "weekly", priority: 0.95 },
    { url: `${BASE}/champions`, lastModified: now, changeFrequency: "weekly", priority: 0.9 },
    { url: `${BASE}/methodology`, lastModified: now, changeFrequency: "monthly", priority: 0.6 },
  ];
  const championPages: MetadataRoute.Sitemap = getChampions().map((c) => ({
    url: `${BASE}/champions/${c.slug}`,
    lastModified: now,
    changeFrequency: "weekly",
    priority: 0.7,
  }));
  return [...staticPages, ...championPages];
}
