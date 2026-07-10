import buildsData from "@/data/builds.json";
import { getChampion, getChampions, type Champion } from "@/lib/data";

export interface BuildItem {
  slug: string;
  name: string;
  cost: number;
  icon: string;
  reason?: string;
  /** Situational threat label, e.g. "vs Tanks". */
  when?: string;
  /** For situational swaps: the coreBuild slug this item replaces. */
  replaces?: string;
  /** Engine-search verdict: this item appears in nearly every top build. */
  core?: boolean;
}

export interface SituationalRune {
  name: string;
  slug: string;
  icon: string;
  when?: string;
  /** The rune in the page this one swaps in for. */
  replaces?: string;
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
  /** Fight value at unlimited gold (full build); the curve gives budgets. */
  score: number;
  level?: number;
  /** Engine metrics after each purchase in build order: the user's gold slider. */
  curve?: CurvePoint[];
  /** Final full-build stats at level 15 (base + items + runes + kit steroids). */
  ad?: number;
  ap?: number;
  hp?: number;
  armor?: number;
  mr?: number;
  moveSpeed?: number;
  attackSpeed?: number;
  haste?: number;
  crit?: number;
  mana?: number;
}

/** Engine metrics after the Nth purchase in build order (gold-budget slider). */
export interface CurvePoint {
  n: number;
  gold: number;
  level: number;
  item: string;
  score: number;
  burst3: number;
  dps8: number;
  ehp: number;
}

/** One anchor on the damage/tankiness playstyle dial. */
export interface DialAnchor {
  /** Offense weight in percent (90 = glass cannon, 10 = full tank). */
  offense: number;
  variantRunes: string;
  items: { slug: string; name: string; cost: number; icon: string }[];
  boots: { slug: string; name: string; icon: string } | null;
  engine: EngineMetrics;
}

export interface AttackStyle {
  /** How the champion deals damage, measured from the scraped formulas. */
  style: "basic-attack" | "ability-caster" | "hybrid";
  /** Blended auto-reliance 0..1 (1 = pure auto-attacker, 0 = pure caster). */
  autoness: number;
  /** Raw simulated auto-share on the champion's damage build. */
  measuredAutoShare: number;
  /** LLM game-knowledge attack-speed efficiency scalar (cross-check signal). */
  asEfficiency: number | null;
  /** "ok" | "flagged" (signals disagree -> ability formulas likely incomplete) | "measured-only". */
  dataQuality: string;
  /** One-line what-to-build-around hint derived from the style. */
  buildHint: string;
}

/** Full multi-dimensional simulator readout for a build (precomputed). */
export interface BuildAnalysis {
  winScore: number;
  preset: string;
  burst: Record<string, number>;   // 0.5/1/2/3s vs squishy
  dps: Record<string, number>;     // 5/10/20s vs bruiser
  ttk: Record<string, number | null>; // adc/mage/fighter/bruiser/tank
  byTypePct: { physical: number; magic: number; true: number };
  bySource: { auto: number; ability: number };
  byAbility: Record<string, number>;
  items: { slug: string; name: string; dmg: number }[];
  runes: { name: string; dmg: number }[];
  ehp: number;
  ehpSplit: { physical: number; magic: number };
  survivalTime: Record<string, number | null>;
  goldEff: { gold: number; dmgPerGold: number | null; ehpPerGold: number | null };
  healing: { lifesteal: number; omnivamp: number; onHit: number; rune: number; total: number };
  shields: { value: number; avgUptime: number; amp: number };
  damagePrevented: { armor: number; mr: number; dr: number; shield: number; total: number };
  cooldownUtil: { efficiency: number };
  damageLost: { autoUptimePct: number; autoDmgLost: number; overkill: number };
}

export interface Build {
  summary: string;
  coreBuild: BuildItem[];
  boots: BuildItem | null;
  enchantment: BuildItem | null;
  situational: BuildItem[];
  situationalRunes?: SituationalRune[];
  summoners?: SummonerSpell[];
  runes: RunePage;
  engine?: EngineMetrics;
  analysis?: BuildAnalysis;
}

export interface ChampionBuilds {
  name: string;
  class: string;
  role: string;
  damageProfile: string;
  canOneshot: boolean;
  /** Engine-measured auto-vs-ability lean: what the champion should build around. */
  attackStyle?: AttackStyle;
  /** Kit synergy hooks the builds were designed around (passive/item/rune interactions). */
  synergyNotes?: string[];
  variants: string[];
  builds: Record<string, Build>;
  /** Precomputed playstyle-dial anchor builds (engine-searched per weighting). */
  dial?: DialAnchor[];
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
