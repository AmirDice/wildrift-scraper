import { getChampions, site, TIER_ORDER, tierLabel, type Champion, type Tier } from "./data";

// Aggregations powering the Meta Report charts. All derived on the fly from the
// same site.json the rest of the app reads, so nothing here needs regenerating.

export type TierCount = { tier: Tier; label: string; count: number };

export function tierDistribution(): TierCount[] {
  const champs = getChampions();
  return TIER_ORDER.map((tier) => ({
    tier,
    label: tierLabel(tier),
    count: champs.filter((c) => c.tier === tier).length,
  }));
}

export type HistBin = { lo: number; hi: number; count: number; mid: number };

// Win-rate histogram. Win rates are already 50%-centred, so bins straddle 50.
export function wrHistogram(binSize = 1): HistBin[] {
  const champs = getChampions().filter((c) => (c.nPlayers ?? 0) >= 20);
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
  return getChampions()
    .filter((c) => (c.nPlayers ?? 0) >= 20 && c.totalGames != null)
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

export function classMeta(): ClassStat[] {
  return (site.metaBreakdown as ClassStat[]).slice().sort((a, b) => b.wr - a.wr);
}

export type RoleStat = { role: string; wr: number };

export function roleMeta(): RoleStat[] {
  return Object.entries(site.roleStrength)
    .map(([role, s]) => ({ role, wr: s.wr }))
    .sort((a, b) => b.wr - a.wr);
}

// Role x tier heatmap: how many champions of each role land in each tier.
export type HeatRow = { role: string; cells: { tier: Tier; label: string; count: number }[]; total: number };

export function roleTierMatrix(): HeatRow[] {
  const champs = getChampions();
  return (site.roles as string[]).map((role) => {
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

export type DifficultyStat = { difficulty: string; wr: number; nChampions: number };

export function difficultyMeta(): DifficultyStat[] {
  return site.winrateByDifficulty as DifficultyStat[];
}

// Headline numbers for the summary strip.
export function metaHeadline() {
  const champs = getChampions();
  const ranked = champs.filter((c) => (c.nPlayers ?? 0) >= 20);
  const topClass = classMeta()[0];
  const topRole = roleMeta()[0];
  const godS = champs.filter((c) => c.tier === "GOD" || c.tier === "S").length;
  const avgWr = ranked.reduce((s, c) => s + c.wr, 0) / ranked.length;
  return {
    nChampions: champs.length,
    ranked: ranked.length,
    topClass,
    topRole,
    metaDefining: godS,
    avgWr,
  };
}

export type { Champion };
