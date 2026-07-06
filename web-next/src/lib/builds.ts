import buildsData from "@/data/builds.json";
import { getChampion, getChampions, type Champion } from "@/lib/data";

export interface BuildItem {
  slug: string;
  name: string;
  cost: number;
  icon: string;
  reason?: string;
  when?: string;
}

export interface Rune {
  name: string;
  slug: string;
  icon: string;
  tree?: string;
  reason?: string;
}

export interface RunePage {
  keystone: Rune | null;
  primaryTree: string;
  treeMinors: Rune[];
  flexMinor: Rune | null;
}

export interface Build {
  summary: string;
  coreBuild: BuildItem[];
  boots: BuildItem | null;
  enchantment: BuildItem | null;
  situational: BuildItem[];
  runes: RunePage;
}

export interface ChampionBuilds {
  name: string;
  class: string;
  role: string;
  damageProfile: string;
  canOneshot: boolean;
  variants: string[];
  builds: Record<string, Build>;
}

const BUILDS = buildsData as unknown as Record<string, ChampionBuilds>;

/** Champions that have a generated build, as {slug, champion} pairs. */
export function buildChampions(): { slug: string; champion: Champion; builds: ChampionBuilds }[] {
  const out: { slug: string; champion: Champion; builds: ChampionBuilds }[] = [];
  for (const c of getChampions()) {
    const b = BUILDS[c.name];
    if (b) out.push({ slug: c.slug, champion: c, builds: b });
  }
  return out;
}

export function getBuild(slug: string): { champion: Champion; builds: ChampionBuilds } | null {
  const champion = getChampion(slug);
  if (!champion) return null;
  const builds = BUILDS[champion.name];
  if (!builds) return null;
  return { champion, builds };
}

/** Total gold for a build (5 items + boots + enchant). */
export function buildGold(b: Build): number {
  const core = b.coreBuild.reduce((s, it) => s + (it.cost || 0), 0);
  return core + (b.boots?.cost || 0) + (b.enchantment?.cost || 0);
}
