import detailsData from "@/data/champion_details.json";

export interface AbilityCard {
  slot: string;         // P | 1 | 2 | 3 | 4
  key: string;          // Passive | Q | W | E | R
  name: string;
  text: string;
  cooldowns: string[];
  damageTypes: string[];
  icon: string | null;  // /abilities/<file>.png, rehosted Riot art
}

export interface BaseStat {
  base: number;
  perLevel: number;
  lvl15?: number;
}

export interface ChampionDetails {
  name: string;
  baseStats: Record<string, BaseStat>;
  abilities: AbilityCard[];
  /** Max order of the three basic abilities, as keys e.g. ["Q","E","W"]. */
  skillPriority: string[];
}

const DETAILS = detailsData as unknown as Record<string, ChampionDetails>;

export function getChampionDetails(slug: string): ChampionDetails | null {
  return DETAILS[slug] ?? null;
}
