import siteData from "@/data/site.json";
import siteDataNa from "@/data/site_na.json";
import { getNewChampion, getNewChampions, type NewChampion } from "@/lib/new-champions";

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
  /** Raw win-rate movement since the previous collection (site.movementSince).
   *  Null for champions absent from the earlier snapshot. */
  wrDelta?: number | null;
  /** "up" | "down" when the champion crossed a TIER boundary since the
   *  previous collection; null inside the same tier. Gates the arrow badge. */
  tierMoved?: string | null;
  tierRoleMoved?: string | null;
  /** How many regional win rates were averaged into a Global row (2 or 3).
   *  Set only by getGlobalChampions. A move in ONE region shifts the combined
   *  score by its delta divided by this, so the figure has to travel with the
   *  champion rather than being assumed: it was hardcoded to 2 when Global
   *  meant EU and CN, and adding NA silently inflated every arrow by half. */
  globalParts?: number;
  prevTier?: string | null;
  prevTierRole?: string | null;
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
  /** Shallower pool slices for the tier list's depth toggle, keyed "25" |
   *  "10" | "5". "All" is the top-level wr/tier. EU only: CN's numbers are
   *  Tencent's bracket aggregates with no per-player rows to re-slice. */
  pools?: Record<string, {
    wr: number | null;
    nPlayers: number | null;
    tier: string;
    wrOffset?: number;
    tierCss: string;
    tierRole: string;
    tierRoleCss: string;
  }> | null;
  /** No top-50 leaderboard yet, so every ranking field on this record is a
   *  placeholder and must not be rendered. Set only for champions surfaced
   *  from new_champions.json; see pendingChampion(). */
  statsPending?: boolean;
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
  movementSince?: string | null;
  roles: string[];
  nChampions: number;
  nPlayers: number;
  /** Champion win rates are shifted by this so the pool average reads 50%. */
  wrOffset: number;
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

// The bottom bucket is stored as "Ass" (its internal key, set by the Python
// pipeline and cn.ts). User-facing text shows "L" instead -- always render a
// tier through tierLabel() rather than printing the raw key.
export const TIER_LABEL: Record<string, string> = {
  GOD: "GOD", S: "S", A: "A", B: "B", C: "C", Ass: "L",
};
export const tierLabel = (tier: string): string => TIER_LABEL[tier] ?? tier;

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

/** NA's own board, exported by the same pipeline into its own files. Shape is
 *  identical to EU's; only the numbers differ. Collection is still in
 *  progress, so this holds fewer champions than EU and the callers that show
 *  it say so. */
export const siteNa = siteDataNa as unknown as Site;

export function getChampions(): Champion[] {
  return site.champions;
}

export function getChampionsNa(): Champion[] {
  return siteNa.champions;
}

/** Champion rows for a region, plus the metadata a page needs to describe the
 *  sample honestly (collection date, how many champions it covers). */
export function regionBoard(region: "EU" | "NA") {
  const source = region === "NA" ? siteNa : site;
  return {
    champions: source.champions,
    roles: source.roles,
    collectedOn: source.collectedOn,
    nChampions: source.nChampions,
    nPlayers: source.nPlayers,
  };
}

// Built once. getChampion is called from every champion page, every matchup
// row and every blend result, and a linear scan of 138 records per lookup is
// the kind of cost that only shows up once the build has 140 pages in it.
let _bySlug: Map<string, Champion> | null = null;

/**
 * A champion who is live in the game but has no ranked data here yet.
 *
 * Every ranking field is a placeholder: the site's numbers come from top-50
 * player win rates, and inventing one for a champion with no leaderboard is
 * exactly what this codebase refuses to do. `statsPending` marks that, and
 * callers must hide the ranking UI rather than render these values -- which is
 * why the win rate is NaN and the tier is empty: they cannot be shown by
 * accident without looking obviously wrong.
 */
function pendingChampion(c: NewChampion): Champion {
  return {
    name: c.name, slug: c.slug, role: c.role, class: c.class,
    difficulty: c.difficulty, difficultyLabel: c.difficultyLabel,
    isHard: c.difficulty >= 7,
    wr: NaN, meanWr: null, maxWr: null, winrateStd: null, wrDelta: null,
    tierMoved: null, prevTier: null, tierRoleMoved: null, prevTierRole: null,
    medianGames: null, totalGames: null, nPlayers: null, medianMastery: null,
    maxScore: null, otpScore: null, isOtp: false, topPlayer: null,
    tier: "", tierCss: "", tierRole: "", tierRoleCss: "",
    skillSpread: null, icon: c.icon, splash: c.splash, bestPlayer: null,
    statsPending: true,
  };
}

export function getChampion(slug: string): Champion | undefined {
  if (!_bySlug) _bySlug = new Map(site.champions.map((c) => [c.slug, c]));
  const ranked = _bySlug.get(slug);
  if (ranked) return ranked;
  // Falls back so a champion with a real kit and a generated build still has a
  // page and a build, even before they have a win rate. getChampions() is left
  // alone on purpose: it feeds the tier list and every ranking on the site.
  const pending = getNewChampion(slug);
  return pending ? pendingChampion(pending) : undefined;
}

/** Kit-complete champions with no ranked data yet, as Champion records. */
export function pendingChampions(): Champion[] {
  return getNewChampions().map(pendingChampion);
}

export function championsInRole(role: string): Champion[] {
  return site.champions.filter((c) => c.role === role);
}
