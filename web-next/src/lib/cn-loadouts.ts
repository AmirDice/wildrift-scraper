import loadoutData from "@/data/cn_loadouts.json";
import itemsData from "@/data/items.json";
import runeIconsData from "@/data/rune_icons.json";
import siteData from "@/data/site.json";
import spellsData from "@/data/spells.json";

type RawRow = {
  rank: number;
  winRate: number;
  pickRate: number;
  entities: string[];
  /** The same row in the previous snapshot (scripts/export_loadouts_for_web.py). */
  prev?: { rank: number; winRate: number; pickRate: number };
  /** Listed now, not in the previous snapshot. */
  new?: boolean;
};

type RawTab = {
  date: string | null;
  sourceRows: number;
  recognizedRows: number;
  reportedCoverage: number;
  visibleCoverage: number;
  rows: RawRow[];
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

export type LoadoutTab = Omit<RawTab, "rows"> & {
  rows: LoadoutRow[];
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

function resolveTab(kind: keyof RawLane["tabs"], tab: RawTab): LoadoutTab {
  return {
    ...tab,
    rows: tab.rows.map((row) => ({
      ...row,
      entities: row.entities.map((name) => resolveEntity(kind, name)),
    })),
  };
}

export function getChampionLoadouts(slug: string): ChampionLoadoutLane[] {
  const raw = (loadoutData as RawData).champions[slug] ?? [];
  return raw.map((lane) => ({
    ...lane,
    tabs: {
      items: resolveTab("items", lane.tabs.items),
      runes: resolveTab("runes", lane.tabs.runes),
      boots: resolveTab("boots", lane.tabs.boots),
      spells: resolveTab("spells", lane.tabs.spells),
      versus: resolveTab("versus", lane.tabs.versus),
    },
  }));
}

export function cnLoadoutCoverage() {
  return (loadoutData as RawData).coverage;
}
