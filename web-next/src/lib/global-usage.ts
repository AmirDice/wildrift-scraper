import eu from "@/data/ladder_pulse.json";
import na from "@/data/ladder_pulse_na.json";
import cn from "@/data/ladder_pulse_cn.json";
import { LIVE_ITEMS } from "@/lib/items";

export type UsageRow = {
  name: string; count: number; wr: number | null; slug?: string; tree?: string;
  games: number; wrGames: number;
};
type SpellRow = { pair: string; count: number };
const MINOR_TREES = new Set(["Precision", "Resolve", "Sorcery", "Domination"]);
const FINISHED_ITEMS = new Set(LIVE_ITEMS.filter((item) => !item.categories.includes("MidTier"))
  .map((item) => item.slug));

export function isMinorRune(row: Pick<UsageRow, "tree">): boolean {
  return MINOR_TREES.has(row.tree ?? "");
}

/** Explicit ordering keeps ties alphabetical rather than reversing them too. */
export function leastUsedRows<T extends { count: number; name: string }>(rows: T[], limit: number): T[] {
  return rows.filter((row) => row.count > 0)
    .sort((a, b) => a.count - b.count || a.name.localeCompare(b.name)).slice(0, limit);
}

export function finishedItemRows(rows: UsageRow[]): UsageRow[] {
  return rows.filter((row) => row.slug != null && FINISHED_ITEMS.has(row.slug));
}
export type UsageSource = {
  nPlayers: number; nBuilds: number; nChampions: number;
  generatedAt: string; buildsFrom?: string;
  champions: Record<string, unknown>;
  treeMeta: UsageRow[]; keystoneAll: UsageRow[];
  minorMeta: UsageRow[]; itemAll: UsageRow[]; spellAll: SpellRow[];
};

/** Counts pool across boards; win rates pool their original game weights.
 * Never average rounded regional rates or substitute build counts for games.
 * A board appearance is not a unique account or an observed item-specific game. */
export function combineUsage(sources: UsageSource[]) {
  if (!sources.length) throw new Error("Global usage requires regional sources");
  const merge = (key: "treeMeta" | "keystoneAll" | "minorMeta" | "itemAll") => {
    const buckets = new Map<string, UsageRow>();
    for (const source of sources) for (const row of source[key]) {
      // Old exports counted keystones misread in positions 1-4 as minors.
      // Do not move these into keystone usage: slot 0 already counted that
      // build's keystone, so moving them could double-count the same build.
      if (key === "minorMeta" && !isMinorRune(row)) continue;
      if (!Number.isFinite(row.games) || !Number.isFinite(row.wrGames)
        || row.games < 0 || row.wrGames < 0 || row.wrGames > row.games * 100) {
        throw new Error("Rebuild regional ladder pulses before combining global usage");
      }
      const id = row.slug ?? row.name;
      const combined = buckets.get(id) ?? { ...row, count: 0, games: 0, wrGames: 0, wr: null };
      combined.count += row.count;
      combined.games += row.games;
      combined.wrGames += row.wrGames;
      buckets.set(id, combined);
    }
    return [...buckets.values()].map((row) => ({
      ...row,
      wr: row.games >= 200 ? Math.round(row.wrGames / row.games * 100) / 100 : null,
    })).sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
  };
  const spells = new Map<string, number>();
  for (const source of sources) for (const row of source.spellAll) {
    spells.set(row.pair, (spells.get(row.pair) ?? 0) + row.count);
  }
  const itemAll = merge("itemAll");
  const keystoneAll = merge("keystoneAll");
  return {
    nPlayers: sources.reduce((n, s) => n + s.nPlayers, 0),
    nBuilds: sources.reduce((n, s) => n + s.nBuilds, 0),
    nChampions: new Set(sources.flatMap((s) => Object.keys(s.champions))).size,
    treeMeta: merge("treeMeta"), minorMeta: merge("minorMeta"), itemAll, keystoneAll,
    itemMeta: itemAll.slice(0, 20), keystoneMeta: keystoneAll.slice(0, 10),
    spellMeta: [...spells].map(([pair, count]) => ({ pair, count }))
      .sort((a, b) => b.count - a.count || a.pair.localeCompare(b.pair)),
    sources: sources.map((s, i) => ({
      server: ["EU", "NA", "CN"][i],
      buildsFrom: s.buildsFrom ?? s.generatedAt,
    })),
  };
}

let cached: ReturnType<typeof combineUsage> | undefined;
export function globalUsage() {
  return cached ??= combineUsage([eu, na, cn] as UsageSource[]);
}
