import cnData from "@/data/cn.json";
import { getChampion, getChampions, tierClass, type Champion } from "@/lib/data";
import { getNewChampion } from "@/lib/new-champions";

interface CnEntry {
  winRate: number;
  pickRate: number;
  banRate: number;
  strength: number;
  position: string;
}
interface CnChamp {
  name: string;
  slug: string;
  heroId: string;
  cnName: string;
  byBracket: Record<string, CnEntry>;
}
const CN = cnData as unknown as {
  source: string;
  date: string;
  bracketLabels: Record<string, string>;
  defaultBracket?: string;
  champions: CnChamp[];
};

export const CN_BRACKETS = [
  { key: "1", label: "Diamond+", short: "D+", kind: "regular" },
  { key: "2", label: "Master+", short: "M+", kind: "regular" },
  { key: "3", label: "Challenger", short: "Chal", kind: "regular" },
  { key: "4", label: "Legendary", short: "Legendary", kind: "legendary" },
] as const;

export type CnBracketKey = (typeof CN_BRACKETS)[number]["key"];

/** Challenger is the default standard-ranked sample. */
export const CN_DEFAULT_BRACKET: CnBracketKey = "3";

export const CN_META = {
  source: CN.source,
  date: CN.date,
  bracket: CN.bracketLabels[CN_DEFAULT_BRACKET] ?? "Challenger",
  defaultBracket: CN_DEFAULT_BRACKET,
  brackets: CN_BRACKETS,
};

/** CN win rates cluster near 50% (whole-ladder), so tiers use CN-specific cutoffs. */
function cnTier(wr: number): string {
  if (wr >= 53.5) return "GOD";
  if (wr >= 52) return "S";
  if (wr >= 50.8) return "A";
  if (wr >= 49.5) return "B";
  if (wr >= 48) return "C";
  return "Ass";
}

/** Champion object shaped like the EU one, plus CN pick/ban. Region-specific
 *  stats we don't have on CN (ceiling, games, mastery, best player) are nulled. */
export interface CnChampion extends Champion {
  cnPickRate: number;
  cnBanRate: number;
}

export function getCnChampions(bracket: CnBracketKey = CN_DEFAULT_BRACKET): CnChampion[] {
  const out: CnChampion[] = [];
  for (const c of CN.champions) {
    const e = c.byBracket[bracket];
    const eu = getChampion(c.slug);
    const newcomer = getNewChampion(c.slug);
    if (!e || (!eu && !newcomer)) continue;
    const tier = cnTier(e.winRate);
    const base: Champion = eu ?? {
      name: newcomer!.name,
      slug: newcomer!.slug,
      role: newcomer!.role,
      class: newcomer!.class,
      difficulty: newcomer!.difficulty,
      difficultyLabel: newcomer!.difficultyLabel,
      isHard: newcomer!.difficulty >= 7,
      wr: e.winRate,
      meanWr: null,
      maxWr: null,
      winrateStd: null,
      medianGames: null,
      totalGames: null,
      nPlayers: null,
      medianMastery: null,
      maxScore: null,
      otpScore: null,
      isOtp: false,
      topPlayer: null,
      tier,
      tierCss: tierClass[tier],
      tierRole: tier,
      tierRoleCss: tierClass[tier],
      skillSpread: null,
      icon: newcomer!.icon,
      splash: newcomer!.splash,
      bestPlayer: null,
    };
    out.push({
      ...base,
      role: e.position,
      wr: e.winRate,
      tier,
      tierCss: tierClass[tier],
      tierRole: tier,
      tierRoleCss: tierClass[tier],
      isOtp: false,
      meanWr: null,
      maxWr: null,
      winrateStd: null,
      medianGames: null,
      totalGames: null,
      nPlayers: null,
      medianMastery: null,
      maxScore: null,
      otpScore: null,
      topPlayer: null,
      skillSpread: null,
      bestPlayer: null,
      cnPickRate: e.pickRate,
      cnBanRate: e.banRate,
    });
  }
  return out.sort((a, b) => b.wr - a.wr);
}

export function cnRoles(bracket: CnBracketKey = CN_DEFAULT_BRACKET): string[] {
  const order = ["Baron", "Jungle", "Mid", "Dragon", "Support"];
  const present = new Set(getCnChampions(bracket).map((c) => c.role));
  return order.filter((r) => present.has(r));
}

export function getCnChampionsByBracket(): Record<CnBracketKey, CnChampion[]> {
  return Object.fromEntries(
    CN_BRACKETS.map(({ key }) => [key, getCnChampions(key)]),
  ) as Record<CnBracketKey, CnChampion[]>;
}

export function getCnRolesByBracket(): Record<CnBracketKey, string[]> {
  return Object.fromEntries(
    CN_BRACKETS.map(({ key }) => [key, cnRoles(key)]),
  ) as Record<CnBracketKey, string[]>;
}

const byBracketSlug = new Map<CnBracketKey, Map<string, CnChampion>>();
export function getCnBySlug(
  slug: string,
  bracket: CnBracketKey = CN_DEFAULT_BRACKET,
): CnChampion | undefined {
  let bySlug = byBracketSlug.get(bracket);
  if (!bySlug) {
    bySlug = new Map(getCnChampions(bracket).map((c) => [c.slug, c]));
    byBracketSlug.set(bracket, bySlug);
  }
  return bySlug.get(slug);
}

/** Combined-server tier from the average of the two (50%-centered) win rates. */
export function globalTier(wr: number): string {
  if (wr >= 53.5) return "GOD";
  if (wr >= 52) return "S";
  if (wr >= 50.8) return "A";
  if (wr >= 49.5) return "B";
  if (wr >= 48) return "C";
  return "Ass";
}

/** Champion objects with wr = combined EU+CN score and a global tier. */
export function getGlobalChampions(): Champion[] {
  const out: Champion[] = [];
  for (const eu of getChampions()) {
    const cn = getCnBySlug(eu.slug);
    if (!cn) continue;
    const g = Math.round(((eu.wr + cn.wr) / 2) * 10) / 10;
    const tier = globalTier(g);
    out.push({ ...eu, wr: g, tier, tierRole: tier });
  }
  return out.sort((a, b) => b.wr - a.wr);
}

export function globalRoles(): string[] {
  const order = ["Baron", "Jungle", "Mid", "Dragon", "Support"];
  const present = new Set(getGlobalChampions().map((c) => c.role));
  return order.filter((r) => present.has(r));
}
