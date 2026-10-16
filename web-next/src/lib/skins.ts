import skinData from "@/data/wr_skins.json";

/**
 * Wild Rift skins per champion, from the official site's "Available Skins"
 * carousel (scripts/fetch_wr_skins.py). Server-side only: the whole file is
 * every champion's list, and a page needs one.
 */
export interface ChampionSkin {
  /** Stable vote key: the skin name, lower-case alphanumerics. Keyed by name
   *  rather than position so a re-scrape that reorders the carousel cannot
   *  move votes onto a different skin. */
  key: string;
  name: string;
  /** Riot's CMS image, 1280x720; add `&w=...&fm=webp` to resize. */
  image: string;
}

const DATA = skinData as { champions: Record<string, { name: string; image: string }[]> };

export const skinKey = (name: string) => name.toLowerCase().replace(/[^a-z0-9]/g, "");

export function getChampionSkins(slug: string): ChampionSkin[] {
  return (DATA.champions[slug] ?? []).map((skin) => ({ key: skinKey(skin.name), name: skin.name, image: skin.image }));
}
