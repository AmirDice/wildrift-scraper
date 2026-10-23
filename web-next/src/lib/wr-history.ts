import history from "@/data/wr_history.json";
import { getChampionHistory } from "@/lib/champion-history";

/**
 * A champion's win rate over time, per server, for the champion page chart.
 * Built by scripts/export_wr_history.py from the collection snapshots.
 *
 * Ladder points (eu, na, cn) are the centred top-player rates the tier list
 * showed at each collection. `global` is derived here the way the Global tier
 * list is: at each collection date, the mean of the latest board each server
 * had by then. `daily` is Tencent's China rate over every ranked game, a
 * different measurement kept on its own line.
 */
export type Point = [date: string, wr: number];
export type LadderRegion = "eu" | "na" | "cn";
export type WinRateHistory = {
  eu: Point[];
  na: Point[];
  cn: Point[];
  global: Point[];
  /** How many servers each global point averages. */
  globalServers: number[];
  daily: Point[];
  patches: { patch: string; date: string; kind: string }[];
};

type File = { champions: Record<string, Partial<Record<LadderRegion | "daily", Point[]>>> };

/** Collections closer together than this are one round across servers. */
const WINDOW_DAYS = 7;

export function getWinRateHistory(slug: string, name: string): WinRateHistory | null {
  const rec = (history as unknown as File).champions[slug];
  if (!rec) return null;
  const eu = rec.eu ?? [];
  const na = rec.na ?? [];
  const cn = rec.cn ?? [];

  // Global: one point per collection WINDOW, averaging the latest board each
  // server had by its end. The servers are collected a few days apart (NA 6
  // Oct, EU 7 Oct, China 11 Oct), and a point at every one of those dates
  // averaged EU's September board with NA's October one: a spike that was a
  // scraping schedule, not the meta.
  const all = [...new Set([...eu, ...na, ...cn].map(([date]) => date))].sort();
  const dates = all.filter((date, i) => i === all.length - 1
    || (Date.parse(all[i + 1]) - Date.parse(date)) / 86_400_000 > WINDOW_DAYS);
  const latest = (series: Point[], date: string) => {
    let value: number | null = null;
    for (const [d, wr] of series) if (d <= date) value = wr;
    return value;
  };
  const global: Point[] = [];
  const globalServers: number[] = [];
  for (const date of dates) {
    const values = [latest(eu, date), latest(na, date), latest(cn, date)].filter((v): v is number => v != null);
    if (!values.length) continue;
    global.push([date, Math.round((values.reduce((a, b) => a + b, 0) / values.length) * 10) / 10]);
    globalServers.push(values.length);
  }

  // Balance patches inside the chart's window, as markers.
  const from = [dates[0], rec.daily?.[0]?.[0]].filter(Boolean).sort()[0];
  const patches = getChampionHistory(name).changes
    .filter((change) => !change.modeOnly && from && change.publishedAt.slice(0, 10) >= from)
    .map((change) => ({ patch: change.patch, date: change.publishedAt.slice(0, 10), kind: change.kind }))
    // One marker per patch and day: a champion changed twice in the same
    // notes (Riven, 7.3) would draw two lines on top of each other.
    .filter((change, index, all) => all.findIndex((other) => other.patch === change.patch && other.date === change.date) === index)
    .sort((a, b) => a.date.localeCompare(b.date));

  return { eu, na, cn, global, globalServers, daily: rec.daily ?? [], patches };
}
