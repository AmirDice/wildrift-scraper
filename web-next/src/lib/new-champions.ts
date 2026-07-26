import newChampionData from "@/data/new_champions.json";

/**
 * Champions that are live in Wild Rift but have no ranked-player data here yet.
 *
 * They are deliberately kept OUT of getChampions(): every ranking on the site
 * is built from top-50 player win rates, and a champion with no leaderboard
 * cannot be placed in one honestly. Instead they get their own section, with
 * what wildriftfire knows (role, its own tier grade, kit and base stats) and an
 * explicit "stats pending" state.
 *
 * Regenerate with: python -m scripts.export_new_champions
 */

export interface NewChampionAbility {
  slot: string;
  name: string;
  text: string;
  cooldowns: string[];
}

export interface NewChampion {
  name: string;
  slug: string;
  role: string;
  class: string;
  difficulty: number;
  difficultyLabel: string;
  icon: string;
  splash: string;
  primaryDamage: string | null;
  scalesWith: string[];
  mechanics: string[];
  baseStats: Record<string, { base: number; perLevel: number; lvl15: number }>;
  abilities: NewChampionAbility[];
  /** wildriftfire's own letter grade, when their guide has one yet. */
  guideTier: string | null;
  guideLane: string | null;
  guideUrl: string;
  /** Announced but not yet playable. Its scraped stats are placeholder data
   *  (a stub kit with no real cooldowns), so the card shows "Coming soon" and
   *  hides the numbers rather than presenting fiction as fact. */
  comingSoon?: boolean;
}

const DATA = newChampionData as {
  source: string;
  generatedAt: string;
  champions: NewChampion[];
};

export const NEW_CHAMPION_SOURCE = DATA.source;

export function getNewChampions(): NewChampion[] {
  return DATA.champions;
}

export function getNewChampion(slug: string): NewChampion | undefined {
  return DATA.champions.find((champion) => champion.slug === slug);
}
