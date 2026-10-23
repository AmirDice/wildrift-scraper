import impactData from "@/data/cn_patch_impact.json";
import itemsData from "@/data/items.json";
import runeIconsData from "@/data/rune_icons.json";
import siteData from "@/data/site.json";
import wrHistory from "@/data/wr_history.json";
import historyData from "@/data/champion_change_history.json";

/**
 * What a patch did to China's Legendary builds, for /patch-impact/[patch].
 * Built by scripts/export_loadouts_for_web.py export_patch_impact from the
 * archived loadout captures on either side of the patch.
 *
 * Shares are of each champion-lane's games, averaged with every lane counting
 * once (China gives no game counts), so "4.8% of cores" means: across the
 * roster's lanes, 4.8% of games on average had that item in the core.
 */
type Role = Record<string, { before: number; after: number }>;
type Mover = { slug: string; lane: string; before: number; after: number };
type Entry = {
  name: string; changed: boolean; before: number; after: number;
  coreBefore: number; coreAfter: number; roles: Role; movers: Mover[];
};
type Impact = {
  patch: string; previous: string; lanes: number; liveDate: string | null; notesUrl: string | null;
  captures: Record<string, number>; items: Entry[]; runes: Entry[];
};

const DATA = (impactData as unknown as { patches: Record<string, Impact> }).patches;
const ITEMS = new Map((itemsData as { name: string; slug: string; icon: string }[]).map((item) => [item.name, item]));
const RUNES = runeIconsData as Record<string, string>;
const CHAMPS = new Map((siteData.champions as { slug: string; name: string; icon: string }[]).map((c) => [c.slug, c]));
const DAILY = (wrHistory as unknown as { champions: Record<string, { daily?: [string, number][] }> }).champions;

export const LANE_NAME: Record<string, string> = { baron: "Baron", jungle: "Jungle", mid: "Mid", dragon: "Dragon", support: "Support" };

export function impactPatches(): string[] {
  return Object.keys(DATA).sort((a, b) => b.localeCompare(a, undefined, { numeric: true }));
}

export type ImpactMover = Mover & { champion: string; icon: string };
export type ImpactEntry = Omit<Entry, "movers"> & { icon: string; href?: string; delta: number; movers: ImpactMover[]; summary: string };

const r1 = (v: number) => Math.round(v * 10) / 10;

function describe(entry: Entry, kind: "items" | "runes", movers: ImpactMover[], patch: string): string {
  const delta = r1(entry.after - entry.before);
  const what = kind === "items" ? "of games had it in the three-item core" : "of rune pages ran it";
  const lead = Math.abs(delta) < 0.3
    ? `${entry.name} barely moved after ${patch}: ${entry.before.toFixed(1)}% ${what} before, ${entry.after.toFixed(1)}% after.`
    : `${entry.name} ${delta > 0 ? "gained" : "lost"} ground after ${patch}: ${entry.before.toFixed(1)}% ${what} before, ${entry.after.toFixed(1)}% after.`;
  const core = kind === "items" && entry.coreBefore !== entry.coreAfter
    ? ` It is a core item (in 20%+ of cores) for ${entry.coreAfter} champion-lanes, from ${entry.coreBefore}.`
    : "";
  const top = movers[0];
  const swing = top && Math.abs(top.after - top.before) >= 5
    ? ` The biggest swing is ${top.champion} ${LANE_NAME[top.lane] ?? top.lane}, ${top.before.toFixed(1)}% to ${top.after.toFixed(1)}%.`
    : "";
  return lead + core + swing;
}

function resolve(entry: Entry, kind: "items" | "runes", patch: string): ImpactEntry {
  const movers = entry.movers
    .map((m) => ({ ...m, champion: CHAMPS.get(m.slug)?.name ?? m.slug, icon: CHAMPS.get(m.slug)?.icon ?? "/favicon.ico" }));
  const item = kind === "items" ? ITEMS.get(entry.name) : undefined;
  return {
    ...entry,
    icon: kind === "items" ? item?.icon ?? "/items/unknown.webp" : RUNES[entry.name] ?? "/items/unknown.webp",
    href: kind === "items" ? (item ? `/items#${item.slug}` : undefined) : "/runes",
    delta: r1(entry.after - entry.before),
    movers,
    summary: describe(entry, kind, movers, patch),
  };
}

export type ChampionImpact = { name: string; slug: string; icon: string; before: number | null; after: number | null };

/** Tencent's daily China win rate (every ranked game) for each champion the
 *  patch changed: the mean of the week before it went live against the days
 *  since. A different measure from the ladder, labelled as such on the page. */
function championImpact(patch: string, liveDate: string | null): ChampionImpact[] {
  const changes = historyData as { champions: Record<string, { patch: string; modeOnly: boolean }[]> };
  const names = Object.entries(changes.champions)
    .filter(([, list]) => list.some((c) => c.patch === patch && !c.modeOnly)).map(([name]) => name);
  const bySlug = new Map([...CHAMPS.values()].map((c) => [c.name, c]));
  const mean = (points: [string, number][]) => (points.length ? r1(points.reduce((s, [, v]) => s + v, 0) / points.length) : null);
  return names.flatMap((name) => {
    const champ = bySlug.get(name);
    if (!champ) return [];
    const daily = DAILY[champ.slug]?.daily ?? [];
    if (!liveDate) return [{ name, slug: champ.slug, icon: champ.icon, before: null, after: null }];
    const live = Date.parse(liveDate);
    const before = daily.filter(([d]) => Date.parse(d) < live && Date.parse(d) >= live - 7 * 86_400_000);
    const after = daily.filter(([d]) => Date.parse(d) > live);
    return [{ name, slug: champ.slug, icon: champ.icon, before: mean(before), after: mean(after) }];
  }).sort((a, b) => ((b.after ?? 0) - (b.before ?? 0)) - ((a.after ?? 0) - (a.before ?? 0)));
}

export function getPatchImpact(patch: string) {
  const data = DATA[patch];
  if (!data) return null;
  const items = data.items.map((entry) => resolve(entry, "items", patch));
  const runes = data.runes.map((entry) => resolve(entry, "runes", patch));
  const untouched = (list: ImpactEntry[]) => list.filter((e) => !e.changed && Math.max(e.before, e.after) >= 1)
    .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta)).slice(0, 6);
  return {
    ...data,
    changedItems: items.filter((e) => e.changed).sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta)),
    changedRunes: runes.filter((e) => e.changed).sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta)),
    movedItems: untouched(items),
    movedRunes: untouched(runes),
    champions: championImpact(patch, data.liveDate),
  };
}

export type PatchImpact = NonNullable<ReturnType<typeof getPatchImpact>>;
