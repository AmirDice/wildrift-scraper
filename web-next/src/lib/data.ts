import siteData from "@/data/site.json";

export interface BestPlayer {
  player: string;
  rank: number | null;
  confidence_wr: number | null;
}

export interface Champion {
  name: string;
  slug: string;
  role: string;
  class: string;
  difficulty: number;
  difficultyLabel: string;
  isHard: boolean;
  wr: number;
  meanWr: number | null;
  maxWr: number | null;
  winrateStd: number | null;
  medianGames: number | null;
  totalGames: number | null;
  nPlayers: number | null;
  medianMastery: number | null;
  maxScore: number | null;
  otpScore: number | null;
  isOtp: boolean;
  topPlayer: string | null;
  tier: string;
  tierCss: string;
  tierRole: string;
  tierRoleCss: string;
  skillSpread: number | null;
  icon: string;
  splash: string;
  bestPlayer: BestPlayer | null;
}

export interface MetaClass {
  class: string;
  wr: number;
  nChampions: number;
  totalGames: number;
}

export interface DiffBucket {
  difficulty: string;
  wr: number;
  nChampions: number;
}

export interface RoleStrength {
  wr: number;
  lowConfidence: boolean;
}

export interface ChampionMain {
  player: string;
  nChampions: number;
  champions: string[];
  avgWr: number | null;
  bestRank: number | null;
  firstChampionIcon: string | null;
}

export interface FunnyName {
  player: string;
  champion: string;
  icon: string;
}

export interface MasteryEntry {
  player: string;
  champion: string;
  slug: string;
  icon: string;
  score: number | null;
  wr: number | null;
}

export interface Site {
  collectedOn: string | null;
  roles: string[];
  nChampions: number;
  nPlayers: number;
  champions: Champion[];
  metaBreakdown: MetaClass[];
  winrateByDifficulty: DiffBucket[];
  roleStrength: Record<string, RoleStrength>;
  multiChampionMains: ChampionMain[];
  funnyNames: FunnyName[];
  offMetaSlugs: string[];
  topMastery: MasteryEntry[];
}

export const site = siteData as Site;

/** Tier display order, top to bottom. */
export const TIER_ORDER = ["GOD", "S", "A", "B", "C", "Ass"] as const;
export type Tier = (typeof TIER_ORDER)[number];

export const tierClass: Record<string, string> = {
  GOD: "tier-god",
  S: "tier-s",
  A: "tier-a",
  B: "tier-b",
  C: "tier-c",
  Ass: "tier-ass",
};

export const tierText: Record<string, string> = {
  GOD: "tx-god",
  S: "tx-s",
  A: "tx-a",
  B: "tx-b",
  C: "tx-c",
  Ass: "tx-ass",
};

export function getChampions(): Champion[] {
  return site.champions;
}

export function getChampion(slug: string): Champion | undefined {
  return site.champions.find((c) => c.slug === slug);
}

export function championsInRole(role: string): Champion[] {
  return site.champions.filter((c) => c.role === role);
}
