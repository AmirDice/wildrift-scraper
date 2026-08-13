import cnData from "@/data/cn.json";
import { getChampion, getChampions, regionBoard, tierClass, type Champion } from "@/lib/data";
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

/** The fallback order when a champion has no row in the requested bracket.
 *  The CN source omits low-pick champions from thin samples, which silently
 *  removed them from the whole CN view. Same-queue brackets are tried first
 *  (widest sample outward); the OTHER queue is a deliberate last resort,
 *  because Gragas has ranked rows in NO bracket at all -- only Legendary --
 *  and a real number from the other queue beats a champion that simply
 *  vanishes. A row borrowed across queues is still that champion's live CN
 *  performance, just from the other ladder. */
const BRACKET_FALLBACK: Record<CnBracketKey, CnBracketKey[]> = {
  "1": ["1", "2", "3", "4"],
  "2": ["2", "1", "3", "4"],
  "3": ["3", "2", "1", "4"],
  "4": ["4", "3", "2", "1"],
};

export function getCnChampions(bracket: CnBracketKey = CN_DEFAULT_BRACKET): CnChampion[] {
  const out: CnChampion[] = [];
  for (const c of CN.champions) {
    const e = BRACKET_FALLBACK[bracket]
      .map((key) => c.byBracket[key])
      .find(Boolean);
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

/**
 * Champions the CN source has no rows for at this rank.
 *
 * getCnChampions drops them, because every column in the table is a number and
 * a champion with no games has none. Dropping them silently is what made the
 * list read "136 champions" against a 141-champion roster with no explanation,
 * so the page names them instead. The set is rank-dependent: a champion nobody
 * plays in Challenger usually has plenty of games lower down.
 */
export function cnChampionsWithoutData(
  bracket: CnBracketKey = CN_DEFAULT_BRACKET,
): string[] {
  return CN.champions
    .filter((c) => !c.byBracket[bracket])
    .map((c) => c.name)
    .sort((a, b) => a.localeCompare(b));
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

/** Champion objects with wr = the mean of the EU and NA top-50 measurements,
 *  and a global tier.
 *
 *  CN was part of this average until 2026-08-11 and was removed deliberately.
 *  It is not a third region of the same measurement: EU and NA are our own
 *  scrape of the 50 best players on a champion, while CN is Tencent's
 *  published rate across a whole bracket population. Averaging them produced
 *  a number that answered neither question, most visibly on Hecarim, who read
 *  59.5 in the west, 50.9 in CN, and 55.2 blended, a figure no group of
 *  players anywhere achieves.
 *
 *  The correlations said the same thing. EU and NA agree at r = +0.71, while
 *  CN sits at +0.46 against EU and +0.44 against NA: roughly equally distant
 *  from both, which points at the methodology rather than at a European
 *  quirk. Dropping CN moved 47 of 140 champions across a tier boundary.
 *
 *  CN keeps its own tab, /ranks and /rising, where the disagreement is the
 *  product rather than noise to be averaged away.
 *
 *  Both regions are required. A single-server number is not a global one, it
 *  is that server's number wearing a different label. */
/** Mean of the values that exist, or null when neither region has one. */
function mean2(a: number | null | undefined, b: number | null | undefined): number | null {
  const parts = [a, b].filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  if (!parts.length) return null;
  return Math.round((parts.reduce((x, y) => x + y, 0) / parts.length) * 100) / 100;
}

/** Sum of the values that exist, or null when neither region has one. */
function sum2(a: number | null | undefined, b: number | null | undefined): number | null {
  const parts = [a, b].filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  if (!parts.length) return null;
  return parts.reduce((x, y) => x + y, 0);
}

/**
 * Depth slices for a Global row: the same 25 / 10 / 5 blend the top-level win
 * rate gets, so the pool-depth filter works on Global too.
 *
 * This used to return null, and the filter was hidden for Global as a result.
 * That was the safe call at the time, because keeping EU's slices unblended
 * would have ranked a 5-deep EU number against a full-pool NA one. Blending
 * them properly is the actual fix.
 *
 * Each depth carries its OWN offset (a shallower pool is centred harder), so
 * the offsets are averaged alongside the win rates rather than assumed equal.
 * A depth is emitted only when BOTH boards have it: half a blend is not a
 * blend, and a champion with fewer than N counted players on one server would
 * otherwise be silently represented by the other server alone.
 */
function blendPools(eu: Champion, na: Champion): Champion["pools"] {
  if (!eu.pools || !na.pools) return null;
  const out: NonNullable<Champion["pools"]> = {};
  for (const depth of ["25", "10", "5"]) {
    const a = eu.pools[depth];
    const b = na.pools[depth];
    if (!a || !b || a.wr == null || b.wr == null) continue;
    const wr = Math.round(((a.wr + b.wr) / 2) * 10) / 10;
    const tier = globalTier(wr);
    out[depth] = {
      wr,
      wrOffset: Math.round((((a.wrOffset ?? 0) + (b.wrOffset ?? 0)) / 2) * 100) / 100,
      nPlayers: (a.nPlayers ?? 0) + (b.nPlayers ?? 0),
      tier,
      tierCss: tierClass[tier],
      tierRole: tier,
      tierRoleCss: tierClass[tier],
    };
  }
  return Object.keys(out).length ? out : null;
}

export function getGlobalChampions(): Champion[] {
  const na = new Map(regionBoard("NA").champions.map((c) => [c.slug, c]));
  const out: Champion[] = [];
  for (const eu of getChampions()) {
    const parts: number[] = [];
    if (Number.isFinite(eu.wr)) parts.push(eu.wr);
    const naChamp = na.get(eu.slug);
    if (naChamp && Number.isFinite(naChamp.wr)) parts.push(naChamp.wr);
    if (parts.length < 2 || !naChamp) continue;
    const g = Math.round((parts.reduce((a, b) => a + b, 0) / parts.length) * 10) / 10;
    const tier = globalTier(g);

    // Every displayed stat has to be blended too. Spreading the EU object and
    // overwriting only wr used to leave a global win rate sitting beside EU's
    // player count and EU's best player, with nothing marking the difference.
    //
    // Counts add, averages average, and the ceiling is the higher of the two
    // ceilings -- with the player who set it, so "best tracked main" names the
    // right person on the right server instead of always naming EU's.
    const euCeiling = eu.maxWr ?? -Infinity;
    const naCeiling = naChamp.maxWr ?? -Infinity;
    const peak = naCeiling > euCeiling ? naChamp : eu;

    out.push({
      ...eu,
      wr: g,
      tier,
      tierRole: tier,
      globalParts: parts.length,
      meanWr: mean2(eu.meanWr, naChamp.meanWr),
      maxWr: peak.maxWr,
      maxScore: peak.maxScore,
      topPlayer: peak.topPlayer,
      bestPlayer: peak.bestPlayer,
      nPlayers: sum2(eu.nPlayers, naChamp.nPlayers),
      totalGames: sum2(eu.totalGames, naChamp.totalGames),
      medianGames: mean2(eu.medianGames, naChamp.medianGames),
      medianMastery: mean2(eu.medianMastery, naChamp.medianMastery),
      otpScore: mean2(eu.otpScore, naChamp.otpScore),
      isOtp: eu.isOtp && naChamp.isOtp,

      // Deliberately dropped rather than averaged.
      //   winrateStd / skillSpread: pooling spread needs the per-player rows,
      //     not two summary numbers. Averaging two standard deviations is not
      //     the standard deviation of the combined pool.
      //   (pools are NOT dropped: they are blended below, same as wr.)
      //   tierMoved / prevTier: EU tier crossings, computed against EU bands.
      //     A Global row can sit in a different band entirely.
      winrateStd: null,
      skillSpread: null,
      pools: blendPools(eu, naChamp),
      tierMoved: null,
      prevTier: null,
    });
  }
  return out.sort((a, b) => b.wr - a.wr);
}

let _globalBySlug: Map<string, Champion> | null = null;

/** The blended row for one champion, or undefined when a region is missing. */
export function getGlobalBySlug(slug: string): Champion | undefined {
  if (!_globalBySlug) _globalBySlug = new Map(getGlobalChampions().map((c) => [c.slug, c]));
  return _globalBySlug.get(slug);
}

export function globalRoles(): string[] {
  const order = ["Baron", "Jungle", "Mid", "Dragon", "Support"];
  const present = new Set(getGlobalChampions().map((c) => c.role));
  return order.filter((r) => present.has(r));
}
