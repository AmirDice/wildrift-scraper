import creatorData from "@/data/creators.json";

/**
 * The Wild Rift creator directory.
 *
 * Everything here describes real people, so the bar for adding an entry is
 * higher than for the rest of the site's data: a wrong link sends traffic to
 * the wrong channel, and calling someone "still uploading" when they stopped a
 * year ago is a claim about them that we made up. So:
 *
 *   - open the channel and copy the URL from the address bar; never guess a
 *     handle from a display name
 *   - set `lastChecked` to the day you actually looked
 *   - only list platforms the creator actively posts on
 *   - `categories` describes the content, not the person
 *
 * Add entries to src/data/creators.json:
 *
 *   {
 *     "name": "Channel name exactly as it appears",
 *     "tagline": "One line on what they make",
 *     "categories": ["educational", "high-elo"],
 *     "languages": ["English"],
 *     "links": { "youtube": "https://www.youtube.com/@handle" },
 *     "lastChecked": "2026-07-23"
 *   }
 */

export const CREATOR_CATEGORIES = [
  { key: "educational", label: "Educational", blurb: "Teaches you to play better" },
  { key: "guides", label: "Guides & builds", blurb: "Champion guides, items, runes" },
  { key: "high-elo", label: "High elo", blurb: "Top-rank gameplay to learn from" },
  { key: "funny", label: "Funny", blurb: "Entertainment first" },
  { key: "montage", label: "Montages", blurb: "Highlights and outplays" },
  { key: "esports", label: "Esports", blurb: "Competitive scene coverage" },
  { key: "news", label: "News & patches", blurb: "Updates, leaks, patch breakdowns" },
  { key: "community", label: "Community", blurb: "Events, tournaments, creators of creators" },
] as const;

export type CreatorCategory = (typeof CREATOR_CATEGORIES)[number]["key"];

export const PLATFORMS = [
  { key: "youtube", label: "YouTube" },
  { key: "twitch", label: "Twitch" },
  { key: "tiktok", label: "TikTok" },
  { key: "kick", label: "Kick" },
  { key: "x", label: "X" },
  { key: "instagram", label: "Instagram" },
  { key: "discord", label: "Discord" },
  { key: "website", label: "Website" },
] as const;

export type Platform = (typeof PLATFORMS)[number]["key"];

export interface Creator {
  name: string;
  tagline: string;
  categories: CreatorCategory[];
  languages?: string[];
  links: Partial<Record<Platform, string>>;
  /** Avatar URL. Optional: the directory reads fine without one. */
  avatar?: string;
  /** ISO date the entry was last verified against the live channel. */
  lastChecked: string;
}

type CreatorFile = { updatedAt: string; creators: Creator[] };

const DATA = creatorData as CreatorFile;

export const CREATORS_UPDATED_AT = DATA.updatedAt;

export function getCreators(): Creator[] {
  return [...DATA.creators].sort((left, right) => left.name.localeCompare(right.name));
}

/** Categories that actually have someone in them, so the filter bar never
 *  offers a tab that leads to an empty list. */
export function activeCategories(creators: Creator[] = getCreators()) {
  const used = new Set(creators.flatMap((creator) => creator.categories));
  return CREATOR_CATEGORIES.filter((category) => used.has(category.key));
}

export function creatorsInCategory(category: CreatorCategory): Creator[] {
  return getCreators().filter((creator) => creator.categories.includes(category));
}
