import { site, TIER_ORDER, tierLabel, type Champion, type Tier } from "./data";
import { getGlobalChampions, globalRoles } from "./cn";

// Aggregations powering the Meta Report charts. All derived on the fly from
// the same data the rest of the app reads, so nothing here needs
// regenerating.
//
// THE POOL IS THE GLOBAL BLEND, not EU. This page is called "Meta Overview"
// and the homepage repeats its figures as plain statements about the game;
// with three servers collected, answering them from one board would make
// every number on both pages a regional claim wearing a global label. The
// blend is the same set of rows the tier list's Global tab shows.
function pool(): Champion[] {
  return getGlobalChampions();
}

// A ranked champion, scaled to however many boards it was blended from.
// nPlayers is the SUM across those boards, so a fixed floor would quietly
// demand twice as much of a two-server champion as of a three-server one.
function ranked(champs: Champion[], perBoard = 20): Champion[] {
  return champs.filter(
    (c) => (c.nPlayers ?? 0) >= perBoard * (c.globalParts ?? 2),
  );
}

/** Games-weighted mean win rate of the strongest `topN` of a group.
 *
 *  The same cut web/data_loader.py makes: take the best few rather than the
 *  whole group, because the off-meta tail of a large class or role answers
 *  a different question than "what is strong right now". Falls back to a
 *  plain mean when no games are recorded, so a group never vanishes for
 *  want of a denominator. */
function topWeightedWr(group: Champion[], topN: number): number | null {
  const best = [...group].sort((a, b) => b.wr - a.wr).slice(0, topN);
  if (!best.length) return null;
  const games = best.reduce((t, c) => t + (c.totalGames ?? 0), 0);
  if (games <= 0) {
    return Math.round((best.reduce((t, c) => t + c.wr, 0) / best.length) * 10) / 10;
  }
  const wr = best.reduce((t, c) => t + c.wr * (c.totalGames ?? 0), 0) / games;
  return Math.round(wr * 10) / 10;
}

export type TierCount = { tier: Tier; label: string; count: number };

export function tierDistribution(): TierCount[] {
  const champs = pool();
  return TIER_ORDER.map((tier) => ({
    tier,
    label: tierLabel(tier),
    count: champs.filter((c) => c.tier === tier).length,
  }));
}

export type HistBin = { lo: number; hi: number; count: number; mid: number };

// Win-rate histogram. Win rates are already 50%-centred, so bins straddle 50.
export function wrHistogram(binSize = 1): HistBin[] {
  const champs = ranked(pool());
  const wrs = champs.map((c) => c.wr);
  const lo = Math.floor(Math.min(...wrs));
  const hi = Math.ceil(Math.max(...wrs));
  const bins: HistBin[] = [];
  for (let x = lo; x < hi; x += binSize) {
    const count = wrs.filter((w) => w >= x && w < x + binSize).length;
    bins.push({ lo: x, hi: x + binSize, mid: x + binSize / 2, count });
  }
  return bins;
}

export type ScatterPoint = {
  slug: string;
  name: string;
  icon: string;
  role: string;
  tier: Tier;
  wr: number;
  games: number;
  ceiling: number;
};

// One point per ranked champion: win rate vs games played, sized by ceiling.
export function wrVsGames(): ScatterPoint[] {
  return ranked(pool())
    .filter((c) => c.totalGames != null)
    .map((c) => ({
      slug: c.slug,
      name: c.name,
      icon: c.icon,
      role: c.role,
      tier: c.tier as Tier,
      wr: c.wr,
      games: c.totalGames as number,
      ceiling: c.maxWr ?? c.wr,
    }));
}

export type ClassStat = { class: string; wr: number; nChampions: number; totalGames: number };

/** Top 5 champions of each class, games-weighted. */
export function classMeta(): ClassStat[] {
  const byClass = new Map<string, Champion[]>();
  for (const champ of pool()) {
    if (!champ.class) continue;
    const bucket = byClass.get(champ.class);
    if (bucket) bucket.push(champ);
    else byClass.set(champ.class, [champ]);
  }
  const out: ClassStat[] = [];
  for (const [name, group] of byClass) {
    const best = [...group].sort((a, b) => b.wr - a.wr).slice(0, 5);
    const wr = topWeightedWr(group, 5);
    if (wr == null) continue;
    out.push({
      class: name,
      wr,
      nChampions: best.length,
      totalGames: best.reduce((t, c) => t + (c.totalGames ?? 0), 0),
    });
  }
  return out.sort((a, b) => b.wr - a.wr);
}

export type RoleStat = { role: string; wr: number; lowConfidence?: boolean };

/** Top 10 champions of each role, games-weighted.
 *
 *  lowConfidence marks a role that could not fill the cut, which is the
 *  same flag the exported EU figures carried and the reason the homepage
 *  can say "strongest role" without a four-champion role winning it. */
export function roleMeta(): RoleStat[] {
  const TOP_PER_ROLE = 10;
  const champs = pool();
  const out: RoleStat[] = [];
  for (const role of globalRoles()) {
    const group = champs.filter((c) => c.role === role);
    const wr = topWeightedWr(group, TOP_PER_ROLE);
    if (wr == null) continue;
    out.push({ role, wr, lowConfidence: group.length < TOP_PER_ROLE });
  }
  return out.sort((a, b) => b.wr - a.wr);
}

// Role x tier heatmap: how many champions of each role land in each tier.
export type HeatRow = { role: string; cells: { tier: Tier; label: string; count: number }[]; total: number };

export function roleTierMatrix(): HeatRow[] {
  const champs = pool();
  return globalRoles().map((role) => {
    const inRole = champs.filter((c) => c.role === role);
    return {
      role,
      total: inRole.length,
      cells: TIER_ORDER.map((tier) => ({
        tier,
        label: tierLabel(tier),
        count: inRole.filter((c) => c.tier === tier).length,
      })),
    };
  });
}

// Headline numbers for the summary strip.
export function metaHeadline() {
  const champs = pool();
  const rankedChamps = ranked(champs);
  const topClass = classMeta()[0];
  const topRole = roleMeta()[0];
  const godS = champs.filter((c) => c.tier === "GOD" || c.tier === "S").length;
  const avgWr = rankedChamps.reduce((s, c) => s + c.wr, 0) / rankedChamps.length;
  return {
    nChampions: champs.length,
    ranked: rankedChamps.length,
    topClass,
    topRole,
    metaDefining: godS,
    avgWr,
  };
}

export type { Champion };
