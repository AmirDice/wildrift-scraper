import loadoutData from "@/data/cn_loadouts.json";
import itemsData from "@/data/items.json";
import runeIconsData from "@/data/rune_icons.json";
import siteData from "@/data/site.json";
import spellsData from "@/data/spells.json";
import { recommendedRow } from "@/lib/loadout-score";

type RawRow = {
  rank: number;
  winRate: number;
  pickRate: number;
  entities: string[];
  /** The same row in the previous snapshot (scripts/export_loadouts_for_web.py). */
  prev?: { rank: number; winRate: number; pickRate: number };
  /** Listed now, not in the previous snapshot. */
  new?: boolean;
  /** Week rows only: captures the row appeared in, and was the day's pick in. */
  seen?: number;
  bestIn?: number;
  /** Week rows only: [MM-DD, win rate, pick rate] per archived capture. */
  trend?: [string, number, number][];
};

/** This lane's captures from the last 7 days, pooled
 *  (scripts/export_loadouts_for_web.py attach_week_and_trend). */
type RawWeek = {
  from: string;
  to: string;
  captures: number;
  /** The weekly pick's row key, entities joined with " + ". */
  best: string | null;
  rows: RawRow[];
};

/** One core or rune page scored patch by patch
 *  (scripts/export_loadouts_for_web.py attach_patches). */
type RawPatchRow = {
  entities: string[];
  /** Mean edge over each patch's lane average, older patches weighted 0.7x per patch back. */
  score: number;
  byPatch: Record<string, { wr: number; pick: number; edge: number }>;
  /** proven: beat the previous patch's average, now played half as much or not at all.
   *  outdated: the same, but an item or rune of it changed since. */
  flag?: "proven" | "outdated";
  changed?: string[];
};
type RawPatches = { order: string[]; captures: Record<string, number>; rows: RawPatchRow[] };

type RawTab = {
  date: string | null;
  sourceRows: number;
  recognizedRows: number;
  reportedCoverage: number;
  visibleCoverage: number;
  rows: RawRow[];
  week?: RawWeek;
  patches?: RawPatches;
};

type RawLane = {
  lane: string;
  capturedAt: string;
  bracket: string;
  mode: string;
  versusKind: "matchup" | "partners";
  /** When the snapshot the movement compares against was captured. */
  previousCapturedAt?: string;
  tabs: {
    items: RawTab;
    runes: RawTab;
    boots: RawTab;
    spells: RawTab;
    versus: RawTab;
  };
};

type RawData = {
  coverage: {
    champions: number;
    totalChampions: number;
    lanePages: number;
    missing: string[];
  };
  champions: Record<string, RawLane[]>;
};

export type LoadoutEntity = {
  name: string;
  icon: string;
  href?: string;
};

export type LoadoutRow = Omit<RawRow, "entities"> & {
  entities: LoadoutEntity[];
};

export type LoadoutWeek = Omit<RawWeek, "rows"> & { rows: LoadoutRow[] };
export type LoadoutPatchRow = Omit<RawPatchRow, "entities"> & { entities: LoadoutEntity[] };
export type LoadoutPatches = Omit<RawPatches, "rows"> & { rows: LoadoutPatchRow[] };

export type LoadoutTab = Omit<RawTab, "rows" | "week" | "patches"> & {
  rows: LoadoutRow[];
  week?: LoadoutWeek;
  patches?: LoadoutPatches;
  /** The tab's own data date is weeks older than the capture: China's app
   *  stopped refreshing it (boots have read July since October). */
  stale?: boolean;
};

export type ChampionLoadoutLane = Omit<RawLane, "tabs"> & {
  tabs: {
    items: LoadoutTab;
    runes: LoadoutTab;
    boots: LoadoutTab;
    spells: LoadoutTab;
    versus: LoadoutTab;
  };
};

const ITEMS = new Map(
  (itemsData as { name: string; slug: string; icon: string }[]).map((item) => [item.name, item]),
);
const RUNES = runeIconsData as Record<string, string>;
const SPELLS = new Map(
  (spellsData as { name: string; slug: string; icon: string }[]).map((spell) => [spell.name, spell]),
);
const CHAMPIONS = new Map(
  (siteData.champions as { name: string; slug: string; icon: string }[]).map((champion) => [champion.name, champion]),
);

function resolveEntity(kind: keyof RawLane["tabs"], name: string): LoadoutEntity {
  if (kind === "items" || kind === "boots") {
    const item = ITEMS.get(name);
    return { name, icon: item?.icon ?? "/items/unknown.webp", href: item ? `/items#${item.slug}` : undefined };
  }
  if (kind === "runes") {
    return { name, icon: RUNES[name] ?? "/items/unknown.webp", href: "/runes" };
  }
  if (kind === "spells") {
    const spell = SPELLS.get(name);
    return { name, icon: spell?.icon ?? "/items/unknown.webp", href: "/runes" };
  }
  const champion = CHAMPIONS.get(name);
  return {
    name,
    icon: champion?.icon ?? "/favicon.ico",
    href: champion ? `/champions/${champion.slug}` : undefined,
  };
}

/** A tab whose data date trails the capture by more than this is stale. */
const STALE_DAYS = 14;

function isStale(tab: RawTab, capturedAt: string): boolean {
  const m = /^(\d{4})(\d{2})(\d{2})$/.exec(tab.date ?? "");
  if (!m) return false;
  const data = Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  const captured = Date.parse(capturedAt.slice(0, 10));
  return Number.isFinite(captured) && (captured - data) / 86_400_000 > STALE_DAYS;
}

function resolveTab(kind: keyof RawLane["tabs"], tab: RawTab, capturedAt: string): LoadoutTab {
  const resolveRows = (rows: RawRow[]) => rows.map((row) => ({
    ...row,
    entities: row.entities.map((name) => resolveEntity(kind, name)),
  }));
  const { week, patches, ...rest } = tab;
  return {
    ...rest,
    rows: resolveRows(tab.rows),
    ...(week ? { week: { ...week, rows: resolveRows(week.rows) } } : {}),
    ...(patches ? { patches: { ...patches, rows: patches.rows.map((row) => ({ ...row, entities: row.entities.map((name) => resolveEntity(kind, name)) })) } } : {}),
    ...(isStale(tab, capturedAt) ? { stale: true } : {}),
  };
}

export function getChampionLoadouts(slug: string): ChampionLoadoutLane[] {
  const raw = (loadoutData as unknown as RawData).champions[slug] ?? [];
  return raw.map((lane) => ({
    ...lane,
    tabs: {
      items: resolveTab("items", lane.tabs.items, lane.capturedAt),
      runes: resolveTab("runes", lane.tabs.runes, lane.capturedAt),
      boots: resolveTab("boots", lane.tabs.boots, lane.capturedAt),
      spells: resolveTab("spells", lane.tabs.spells, lane.capturedAt),
      versus: resolveTab("versus", lane.tabs.versus, lane.capturedAt),
    },
  }));
}

/**
 * The row the site recommends for a tab: the weekly pick when the lane has
 * two or more captures in the last 7 days, else the latest capture's, and
 * nothing for a tab China stopped refreshing (boots since July).
 */
export function recommendedLoadout(tab: LoadoutTab | undefined): LoadoutRow | null {
  if (!tab || tab.stale) return null;
  if (tab.week && tab.week.captures > 1) {
    const key = tab.week.best;
    return tab.week.rows.find((row) => row.entities.map((entity) => entity.name).join(" + ") === key) ?? null;
  }
  return recommendedRow(tab.rows);
}

export function cnLoadoutCoverage() {
  return (loadoutData as unknown as RawData).coverage;
}
