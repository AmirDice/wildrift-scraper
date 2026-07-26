import releaseData from "@/data/champion_releases.json";

/**
 * When each champion arrived in Wild Rift, matched from Riot's own announcement
 * wording in the official patch notes (scripts/extract_champion_releases.py).
 *
 * Not every champion is here: the patch history begins in October 2020, and
 * anything shipped before that has no announcement to read. Callers must handle
 * a missing date rather than substituting a guess -- "since release" is a claim,
 * and an invented release date makes every number derived from it a fiction.
 */

export interface ChampionRelease {
  patch: string | null;
  releasedAt: string | null;
  url: string | null;
  /** The sentence the date was matched from, so any figure can be traced. */
  evidence: string;
}

const DATA = releaseData as {
  historyStartsAt: string;
  releases: Record<string, ChampionRelease>;
};

/** The first patch we have notes for; nothing earlier can be dated. */
export const PATCH_HISTORY_STARTS_AT = DATA.historyStartsAt;

export function getRelease(champion: string): ChampionRelease | null {
  return DATA.releases[champion] ?? null;
}

/** Whole days between a champion's release and now, or null if undated. */
export function daysSinceRelease(champion: string, now = Date.now()): number | null {
  const release = getRelease(champion);
  if (!release?.releasedAt) return null;
  const at = Date.parse(release.releasedAt);
  if (Number.isNaN(at)) return null;
  return Math.max(0, Math.floor((now - at) / 86_400_000));
}

const RELEASE_DATE_FORMAT = new Intl.DateTimeFormat("en-US", {
  year: "numeric",
  month: "long",
  day: "numeric",
  timeZone: "UTC",
});

/** "September 10, 2025", or null when the champion predates the notes. */
export function releaseDateLabel(champion: string): string | null {
  const release = getRelease(champion);
  if (!release?.releasedAt) return null;
  const at = new Date(release.releasedAt);
  return Number.isNaN(at.getTime()) ? null : RELEASE_DATE_FORMAT.format(at);
}
