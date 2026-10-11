import cnData from "@/data/cn.json";
import { getChampion, getChampions, regionBoard, siteCn, tierClass, TIER_ORDER, type Champion } from "@/lib/data";
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

/** The China samples the tier list offers: Tencent's four published
 *  brackets, plus our own top-30 ladder board.
 *
 *  A separate type from CnBracketKey on purpose. That one indexes
 *  @/data/cn.json, and the ladder board is not in that file -- a "ladder"
 *  reaching getCnChampions would quietly return an empty list rather than
 *  fail, which is the kind of bug that ships. */
export type CnSampleKey = CnBracketKey | "ladder";

export const CN_SAMPLES = [
  { key: "ladder", label: "Top 30 ladder", short: "Top 30", kind: "ladder" },
  ...CN_BRACKETS,
] as const;

/** The China tab opens on the ladder board. It is the same measurement as
 *  the EU and NA tabs beside it -- the best players on each champion, 30
 *  deep, centred on 50 -- so a reader switching region now compares like
 *  with like by default. Tencent's brackets are one tap away and answer the
 *  other question, which is the whole ladder rather than the top of it. */
export const CN_TIERLIST_DEFAULT: CnSampleKey = "ladder";

/** Challenger is the default standard-ranked sample. */
export const CN_DEFAULT_BRACKET: CnBracketKey = "3";

export const CN_META = {
  source: CN.source,
  date: CN.date,
  bracket: CN.bracketLabels[CN_DEFAULT_BRACKET] ?? "Challenger",
  defaultBracket: CN_DEFAULT_BRACKET,
  brackets: CN_BRACKETS,
  /** The tier list's own China selector: brackets plus the ladder board. */
  samples: CN_SAMPLES,
  tierListDefault: CN_TIERLIST_DEFAULT,
  /** When our CN ladder board was captured, and the centring it carries.
   *  Tencent's figures are published raw, the ladder board is centred like
   *  EU and NA, so the two cannot share one offset. */
  ladderDate: siteCn.collectedOn,
  ladderOffset: siteCn.wrOffset ?? 0,
  ladderChampions: siteCn.nChampions,
  ladderMovementSince: siteCn.movementSince ?? null,
};

/** CN win rates cluster near 50% (whole-ladder), so tiers use CN-specific cutoffs. */
export function cnTier(wr: number): string {
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

/** Champions for every China sample the tier list can show. */
export function getCnChampionsBySample(): Record<CnSampleKey, Champion[]> {
  return {
    ladder: regionBoard("CN").champions,
    ...getCnChampionsByBracket(),
  };
}

export function getCnRolesBySample(): Record<CnSampleKey, string[]> {
  return {
    ladder: regionBoard("CN").roles,
    ...getCnRolesByBracket(),
  };
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
/** Percentile bands, the same cutoffs export_json uses for role tiers
 *  (assign_tier_relative): the share of the pool strictly ABOVE a champion
 *  decides its band, so every pool spreads GOD to L whatever its range.
 *
 *  Global used absolute cutoffs (GOD from 53.5, S from 52, ...) tuned to one
 *  EU collection. The blend of two centred boards has a narrower spread than
 *  either board on its own -- averaging pulls every champion toward the
 *  middle -- so the top and bottom bands went empty while EU and NA, ranked
 *  by the same percentiles within roles, always filled theirs. */
const RELATIVE_CUTOFFS: ReadonlyArray<readonly [string, number]> = [
  ["GOD", 0.08], ["S", 0.25], ["A", 0.5], ["B", 0.75], ["C", 0.92], ["Ass", 1.01],
];

export function relativeTier(wr: number, pool: number[]): string {
  if (!pool.length || !Number.isFinite(wr)) return "?";
  const better = pool.reduce((n, v) => (v > wr ? n + 1 : n), 0);
  const pct = better / pool.length;
  for (const [label, cut] of RELATIVE_CUTOFFS) if (pct < cut) return label;
  return "Ass";
}

/** "up" when `after` is a better band than `before`, null when no crossing. */
export function tierCrossing(before: string | null, after: string | null): "up" | "down" | null {
  if (!before || !after || before === after) return null;
  const a = (TIER_ORDER as readonly string[]).indexOf(before);
  const b = (TIER_ORDER as readonly string[]).indexOf(after);
  if (a < 0 || b < 0) return null;
  return b < a ? "up" : "down";
}

const r1 = (n: number) => Math.round(n * 10) / 10;

/** Champion objects with wr = the mean of every regional board that has the
 *  champion, and a tier ranked inside that blend.
 *
 *  TENCENT'S CN WAS REMOVED FROM THIS AVERAGE ON 2026-08-11 AND STAYS OUT.
 *  It is not a third region of the same measurement: EU and NA are our own
 *  scrape of the best players on a champion, while @/data/cn.json is
 *  Tencent's published rate across a whole bracket population. Averaging
 *  them produced a number that answered neither question, most visibly on
 *  Hecarim, who read 59.5 in the west, 50.9 in CN, and 55.2 blended, a
 *  figure no group of players anywhere achieves. The correlations agreed:
 *  EU and NA sit at r = +0.71, while Tencent's CN is +0.46 against EU and
 *  +0.44 against NA, roughly equally distant from both, which points at the
 *  methodology rather than a European quirk. Dropping it moved 47 of 140
 *  champions across a tier boundary.
 *
 *  WHAT IS IN THIS BLEND SINCE 2026-10-11 IS A DIFFERENT CN DATASET: our own
 *  capture of the top 30 of each champion's in-client leaderboard
 *  (site_cn.json, regionBoard("CN")). Same method as EU and NA, same depth
 *  -- all three boards are 30 deep and all three centre on 50.0 -- so it is
 *  the same measurement taken on a third server, which is exactly what the
 *  2026-08 removal said was missing. Tencent's bracket data keeps its own
 *  tab, /ranks and /rising, where the disagreement is the product rather
 *  than noise to be averaged away.
 *
 *  Two boards remain the floor. A single-server number is not a global one,
 *  it is that server's number wearing a different label. */

/** Mean of the values that exist, or null when none do. */
function meanOf(values: (number | null | undefined)[]): number | null {
  const parts = values.filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  if (!parts.length) return null;
  return Math.round((parts.reduce((x, y) => x + y, 0) / parts.length) * 100) / 100;
}

/** Sum of the values that exist, or null when none do. */
function sumOf(values: (number | null | undefined)[]): number | null {
  const parts = values.filter((v): v is number => typeof v === "number" && Number.isFinite(v));
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
 * A depth is emitted only when EVERY board in the blend has it: half a blend
 * is not a blend, and a champion with fewer than N counted players on one
 * server would otherwise be silently represented by the others alone.
 */
type DepthValue = { wr: number; wrOffset: number; nPlayers: number };

/** The blended numbers for each pool depth, tiers assigned later once the
 *  whole pool is known (a percentile band needs everyone else's number). */
function blendPoolValues(boards: Champion[]): Record<string, DepthValue> | null {
  if (boards.some((b) => !b.pools)) return null;
  const out: Record<string, DepthValue> = {};
  for (const depth of ["25", "10", "5"]) {
    const slices = boards.map((b) => b.pools?.[depth]);
    if (slices.some((v) => !v || v.wr == null)) continue;
    const have = slices as { wr: number; wrOffset?: number; nPlayers?: number | null }[];
    out[depth] = {
      wr: r1(have.reduce((t, v) => t + v.wr, 0) / have.length),
      wrOffset: Math.round(
        (have.reduce((t, v) => t + (v.wrOffset ?? 0), 0) / have.length) * 100) / 100,
      nPlayers: have.reduce((t, v) => t + (v.nPlayers ?? 0), 0),
    };
  }
  return Object.keys(out).length ? out : null;
}

/** The servers whose boards are averaged, in the order a tooltip names them. */
const GLOBAL_SERVERS = ["NA", "CN"] as const;

export function getGlobalChampions(): Champion[] {
  const others = GLOBAL_SERVERS.map(
    (key) => new Map(regionBoard(key).champions.map((c) => [c.slug, c])),
  );
  type Entry = {
    eu: Champion; boards: Champion[]; g: number; delta: number | null;
    depths: Record<string, DepthValue> | null;
  };
  const entries: Entry[] = [];
  for (const champ of getChampions()) {
    if (!Number.isFinite(champ.wr)) continue;
    const boards = [champ];
    for (const other of others) {
      const row = other.get(champ.slug);
      if (row && Number.isFinite(row.wr)) boards.push(row);
    }
    // Two is the floor, so a champion missing from one server is still
    // Global on the strength of the other two rather than disappearing.
    if (boards.length < 2) continue;
    const g = r1(boards.reduce((t, b) => t + b.wr, 0) / boards.length);
    // Movement is the mean of the regional deltas, each measured in centred
    // units against ITS OWN previous collection. Half a blend is not a
    // blend: a champion with a delta on only some boards reports none,
    // rather than part of the world's movement presented as all of it.
    const deltas = boards.map((b) => b.wrDelta);
    const delta = deltas.every((d) => typeof d === "number")
      ? Math.round(((deltas as number[]).reduce((x, y) => x + y, 0) / deltas.length) * 100) / 100
      : null;
    entries.push({ eu: champ, boards, g, delta, depths: blendPoolValues(boards) });
  }

  // Every band is a rank inside a pool: the whole blend for the tier, the
  // champion's role for the role tier, and the same two pools rebuilt from
  // each champion's PREVIOUS blended number for the tier it came from.
  const finite = (vs: (number | null | undefined)[]) => vs.filter((v): v is number => v != null);
  const inRole = (role: string) => entries.filter((e) => e.eu.role === role);
  const prevOf = (e: Entry) => (e.delta == null ? null : r1(e.g - e.delta));
  const all = entries.map((e) => e.g);
  const prevAll = finite(entries.map(prevOf));
  const depthAll = (depth: string) => finite(entries.map((e) => e.depths?.[depth]?.wr));

  const out: Champion[] = [];
  for (const e of entries) {
    const { eu: euChamp, boards, g } = e;
    const roleEntries = inRole(euChamp.role);
    const tier = relativeTier(g, all);
    const tierRole = relativeTier(g, roleEntries.map((x) => x.g));
    const prev = prevOf(e);
    const prevTier = prev == null ? null : relativeTier(prev, prevAll);
    const prevTierRole = prev == null ? null : relativeTier(prev, finite(roleEntries.map(prevOf)));

    let pools: Champion["pools"] = null;
    if (e.depths) {
      pools = {};
      for (const [depth, v] of Object.entries(e.depths)) {
        const t = relativeTier(v.wr, depthAll(depth));
        const tr = relativeTier(v.wr, finite(roleEntries.map((x) => x.depths?.[depth]?.wr)));
        pools[depth] = {
          wr: v.wr, wrOffset: v.wrOffset, nPlayers: v.nPlayers,
          tier: t, tierCss: tierClass[t], tierRole: tr, tierRoleCss: tierClass[tr],
        };
      }
    }

    // Every displayed stat has to be blended too. Spreading the EU object and
    // overwriting only wr used to leave a global win rate sitting beside EU's
    // player count and EU's best player, with nothing marking the difference.
    //
    // Counts add, averages average, and the ceiling is the highest of the
    // boards' ceilings -- with the player who set it, so "best tracked main"
    // names the right person on the right server instead of always naming
    // EU's.
    const peak = boards.reduce((best, b) =>
      (b.maxWr ?? -Infinity) > (best.maxWr ?? -Infinity) ? b : best);

    out.push({
      ...euChamp,
      wr: g,
      tier,
      tierCss: tierClass[tier],
      tierRole,
      tierRoleCss: tierClass[tierRole],
      globalParts: boards.length,
      meanWr: meanOf(boards.map((b) => b.meanWr)),
      maxWr: peak.maxWr,
      maxScore: peak.maxScore,
      topPlayer: peak.topPlayer,
      bestPlayer: peak.bestPlayer,
      nPlayers: sumOf(boards.map((b) => b.nPlayers)),
      totalGames: sumOf(boards.map((b) => b.totalGames)),
      medianGames: meanOf(boards.map((b) => b.medianGames)),
      medianMastery: meanOf(boards.map((b) => b.medianMastery)),
      otpScore: meanOf(boards.map((b) => b.otpScore)),
      isOtp: boards.every((b) => b.isOtp),

      // Deliberately dropped rather than averaged: pooling a spread needs the
      // per-player rows, not two summary numbers. Averaging two standard
      // deviations is not the standard deviation of the combined pool.
      winrateStd: null,
      skillSpread: null,
      pools,

      // Movement in Global's OWN bands, from the same before/after pair the
      // tooltip shows, so the badge and the text cannot disagree.
      wrDelta: e.delta,
      prevTier,
      tierMoved: tierCrossing(prevTier, tier),
      prevTierRole,
      tierRoleMoved: tierCrossing(prevTierRole, tierRole),
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
