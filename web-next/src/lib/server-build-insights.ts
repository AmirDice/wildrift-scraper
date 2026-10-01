import itemsCatalogue from "@/data/items.json";
import { liveMetrics } from "@/lib/engine";
import type { ServerBuildStats } from "@/lib/server-build";

type BuildInput = {
  items?: string[];
  boots?: string;
  runes?: { keystone?: string; minors?: string[]; flex?: string };
};

type ItemRecord = {
  slug: string;
  cost?: number;
  stats?: Record<string, { value?: number } | number | undefined>;
  tags?: string[];
  passives?: string[];
};

const ITEMS = new Map(
  (itemsCatalogue as unknown as ItemRecord[]).map((item) => [item.slug, item]),
);

function statValue(item: ItemRecord, key: string): number {
  const value = item.stats?.[key === "haste" ? "abilityHaste" : key];
  if (typeof value === "number") return value;
  return Number(value?.value ?? 0) || 0;
}

function profileLabels(slugs: string[], stats: Record<string, number>): string[] {
  const records = slugs.map((slug) => ITEMS.get(slug)).filter(Boolean) as ItemRecord[];
  const text = records.flatMap((item) => [
    ...(item.tags ?? []),
    ...(item.passives ?? []),
  ]).join(" ").toLowerCase();
  const labels: string[] = [];
  if (stats.crit >= 50) labels.push("Crit core");
  else if (stats.crit >= 25) labels.push("Crit flex");
  if (text.includes("onhit") || text.includes("on-hit") || text.includes("on hit")) {
    labels.push("On-hit");
  }
  if (stats.lethality >= 15 || stats.physicalPenFlat >= 15) labels.push("Lethality");
  if (stats.ap >= 50) labels.push("AP");
  if (stats.hp >= 500 || stats.armor + stats.mr >= 80) labels.push("Durable");
  if (stats.lifesteal >= 10) labels.push("Sustain");
  return labels.length ? labels : ["Mixed profile"];
}

/**
 * Build a compact, comparable readout for the per-server ladder card.
 *
 * The engine numbers use the same level-15 standard target assumptions as the
 * Build Studio. They are deliberately labelled as an estimate in the UI: the
 * ladder record contains player item/rune choices, not a measured DPS sample.
 */
export function serverBuildInsights(
  champion: string,
  build: BuildInput | null,
): ServerBuildStats | undefined {
  if (!build?.items?.length) return undefined;
  const slugs = [...build.items, ...(build.boots ? [build.boots] : [])];
  const staticStats = {
    ad: 0, ap: 0, hp: 0, armor: 0, mr: 0, attackSpeed: 0,
    haste: 0, crit: 0, physicalPenFlat: 0, physicalPen: 0,
    magicPenFlat: 0, magicPen: 0, lethality: 0, lifesteal: 0,
  };
  let cost = 0;
  for (const slug of slugs) {
    const item = ITEMS.get(slug);
    if (!item) continue;
    cost += Number(item.cost) || 0;
    for (const key of Object.keys(staticStats) as (keyof typeof staticStats)[]) {
      staticStats[key] += statValue(item, key);
    }
  }

  const runeNames = [
    build.runes?.keystone,
    ...(build.runes?.minors ?? []),
    build.runes?.flex,
  ].filter((name): name is string => Boolean(name));
  let engine: ReturnType<typeof liveMetrics> = null;
  try {
    engine = liveMetrics(champion, slugs, runeNames, "standard", 15);
  } catch {
    // A newly scraped champion can be visible before its formula set reaches
    // the browser engine. Static item stats are still useful in that case.
  }

  return {
    cost,
    ...staticStats,
    ...(engine ?? {}),
    profile: profileLabels(slugs, staticStats),
  };
}
