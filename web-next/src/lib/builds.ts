import buildsData from "@/data/builds.json";
import { getChampion, getChampions, type Champion } from "@/lib/data";

export interface BuildItem {
  slug: string;
  name: string;
  cost: number;
  icon: string;
  reason?: string;
  when?: string;
  /** Engine-search verdict: this item appears in nearly every top build. */
  core?: boolean;
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

export interface SummonerSpell {
  name: string;
  icon: string;
  reason?: string;
}

/** Deterministic fight-engine metrics for one build (web/fight_engine.py). */
export interface EngineMetrics {
  burst3: number;
  dps8: number;
  ttk: number | null;
  ehp: number;
  sustain: number;
  /** Combined fight value: 0.6 x 15-min gold reality + 0.4 x full build. */
  score: number;
  scoreMid?: number;
  scoreFull?: number;
  goldMid?: number;
  itemsMid?: number;
}

export interface Build {
  summary: string;
  coreBuild: BuildItem[];
  boots: BuildItem | null;
  enchantment: BuildItem | null;
  situational: BuildItem[];
  summoners?: SummonerSpell[];
  runes: RunePage;
  engine?: EngineMetrics;
}

export interface ChampionBuilds {
  name: string;
  class: string;
  role: string;
  damageProfile: string;
  canOneshot: boolean;
  /** Kit synergy hooks the builds were designed around (passive/item/rune interactions). */
  synergyNotes?: string[];
  variants: string[];
  builds: Record<string, Build>;
  /** Hard validation failures the generator couldn't repair; never ship these. */
  errors?: string[];
  warnings?: string[];
}

const BUILDS = buildsData as unknown as Record<string, ChampionBuilds>;

/** A record is shippable when the generator validated it clean (no hard errors)
 *  and every declared variant actually exists. */
function shippable(b: ChampionBuilds | undefined): b is ChampionBuilds {
  if (!b || (b.errors && b.errors.length > 0)) return false;
  return b.variants.length > 0 && b.variants.every((v) => b.builds[v]);
}

/** Champions that have a valid generated build, as {slug, champion} pairs. */
export function buildChampions(): { slug: string; champion: Champion; builds: ChampionBuilds }[] {
  const out: { slug: string; champion: Champion; builds: ChampionBuilds }[] = [];
  for (const c of getChampions()) {
    const b = BUILDS[c.name];
    if (shippable(b)) out.push({ slug: c.slug, champion: c, builds: b });
  }
  return out;
}

export function getBuild(slug: string): { champion: Champion; builds: ChampionBuilds } | null {
  const champion = getChampion(slug);
  if (!champion) return null;
  const builds = BUILDS[champion.name];
  if (!shippable(builds)) return null;
  return { champion, builds };
}

/** Total gold for a build (5 items + boots + enchant). */
export function buildGold(b: Build): number {
  const core = b.coreBuild.reduce((s, it) => s + (it.cost || 0), 0);
  return core + (b.boots?.cost || 0) + (b.enchantment?.cost || 0);
}
