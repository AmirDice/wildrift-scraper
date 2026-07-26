import historyData from "@/data/champion_change_history.json";
import summaryData from "@/data/champion_change_summary.json";

export interface ChampionChange {
  patch: string;
  publishedAt: string;
  url: string;
  kind: string;
  scope: string;
  modeOnly: boolean;
  summary: string;
  changes: { ability: string; text: string }[];
}

export interface ChampionHistorySummary {
  totalChanges: number;
  modeOnlyChanges: number;
  balanceChanges: number;
  lastChangedPatch: string | null;
  lastChangedAt: string | null;
  lastBalancePatch: string | null;
  lastBalanceAt: string | null;
}

type HistoryFile = { champions: Record<string, ChampionChange[]> };
type SummaryFile = { champions: Record<string, ChampionHistorySummary> };

export function getChampionHistory(name: string) {
  const changes = [...((historyData as HistoryFile).champions[name] ?? [])].sort((left, right) => {
    const dateDifference = Date.parse(right.publishedAt) - Date.parse(left.publishedAt);
    if (Number.isFinite(dateDifference) && dateDifference !== 0) return dateDifference;
    return right.patch.localeCompare(left.patch, undefined, { numeric: true });
  });
  return {
    changes,
    summary: (summaryData as SummaryFile).champions[name] ?? null,
  };
}
