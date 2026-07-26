import changeSummaryData from "@/data/champion_change_summary.json";
import type { Champion } from "@/lib/data";

type ChangeSummary = {
  champions: Record<string, {
    lastBalancePatch: string | null;
    lastBalanceAt: string | null;
    totalChanges?: number;
    balanceChanges?: number;
    modeOnlyChanges?: number;
  }>;
};

export interface ChampionChangeRankingEntry {
  champion: Champion;
  lastBalancePatch: string | null;
  lastBalanceAt: string | null;
  daysSinceBalanceChange: number | null;
}

export interface ChampionAdjustmentEntry {
  champion: Champion;
  /** Every patch note entry, including mode-only tuning. */
  totalChanges: number;
  /** Standard balance changes only: the number Riot is judged on. */
  balanceChanges: number;
  lastBalancePatch: string | null;
}

const CHANGE_SUMMARY = changeSummaryData as ChangeSummary;
const DAY_MS = 24 * 60 * 60 * 1000;
const RANKING_GENERATED_AT = Date.now();

export function getChampionChangeAge(name: string) {
  const summary = CHANGE_SUMMARY.champions[name];
  const changedAt = summary?.lastBalanceAt ? Date.parse(summary.lastBalanceAt) : Number.NaN;
  return {
    lastBalancePatch: summary?.lastBalancePatch ?? null,
    lastBalanceAt: Number.isFinite(changedAt) ? summary.lastBalanceAt : null,
    daysSinceBalanceChange: Number.isFinite(changedAt)
      ? Math.max(0, Math.floor((RANKING_GENERATED_AT - changedAt) / DAY_MS))
      : null,
  };
}

/** How many times a champion has been touched in the patch notes. Champions
 *  with no entry at all have never been changed, which is itself the story:
 *  those come back as 0 rather than being dropped. */
export function getChampionAdjustments(name: string) {
  const summary = CHANGE_SUMMARY.champions[name];
  return {
    totalChanges: summary?.totalChanges ?? 0,
    balanceChanges: summary?.balanceChanges ?? 0,
    modeOnlyChanges: summary?.modeOnlyChanges ?? 0,
    lastBalancePatch: summary?.lastBalancePatch ?? null,
  };
}

// Both rankings sort the whole roster and are asked for repeatedly: the home
// page, /champion-changes, /changes-report and every blog post that embeds a
// balance list all want the same answer from the same static data.
const _adjustmentCache = new Map<number, ChampionAdjustmentEntry[]>();
const _rankingCache = new Map<number, ChampionChangeRankingEntry[]>();

/** Champions ordered by how often Riot has adjusted them, most first. */
export function getMostAdjustedChampions(champions: Champion[]): ChampionAdjustmentEntry[] {
  const cached = _adjustmentCache.get(champions.length);
  if (cached) return cached;
  const ranked = computeMostAdjusted(champions);
  _adjustmentCache.set(champions.length, ranked);
  return ranked;
}

/**
 * Ranked by STANDARD balance changes, not by total patch-note appearances.
 *
 * The totals mix in mode-only tuning -- ARAM damage multipliers and the like --
 * which says nothing about how often a champion has been rebalanced in the game
 * people actually play. Ranking by those inflated a champion who was never
 * touched in Summoner's Rift but got repeatedly nudged in ARAM.
 */
function computeMostAdjusted(champions: Champion[]): ChampionAdjustmentEntry[] {
  return champions
    .map((champion) => {
      const { totalChanges, balanceChanges, lastBalancePatch } = getChampionAdjustments(champion.name);
      return { champion, totalChanges, balanceChanges, lastBalancePatch };
    })
    .sort(
      (left, right) =>
        right.balanceChanges - left.balanceChanges
        || left.champion.name.localeCompare(right.champion.name),
    );
}

/** Champions that have never had a standard balance change. */
export function getNeverChangedChampions(champions: Champion[]): Champion[] {
  return champions
    .filter((champion) => getChampionAdjustments(champion.name).balanceChanges === 0)
    .sort((left, right) => left.name.localeCompare(right.name));
}

export function getChampionChangeRanking(champions: Champion[]): ChampionChangeRankingEntry[] {
  const cached = _rankingCache.get(champions.length);
  if (cached) return cached;
  const ranked = computeChangeRanking(champions);
  _rankingCache.set(champions.length, ranked);
  return ranked;
}

function computeChangeRanking(champions: Champion[]): ChampionChangeRankingEntry[] {
  return champions
    .map((champion) => {
      return { champion, ...getChampionChangeAge(champion.name) };
    })
    .sort((left, right) => {
      if (left.daysSinceBalanceChange == null) return 1;
      if (right.daysSinceBalanceChange == null) return -1;
      return right.daysSinceBalanceChange - left.daysSinceBalanceChange
        || left.champion.name.localeCompare(right.champion.name);
    });
}
