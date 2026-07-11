/**
 * Enemy-team threat analysis (client-side, Layer 2 of the build optimizer).
 *
 * Given the enemy champions, derives a grounded threat profile (damage type
 * split, healing / shielding / crowd-control / burst presence) and a pair of
 * real defensive targets computed from the enemy comp's own base stats, then
 * recommends situational item and rune swaps that counter that specific team.
 *
 * All inputs come from src/data/roster.json (every champion's damage type, kit
 * mechanics, class and base stats) so this works for any enemy pick, not just
 * the champions that have generated builds.
 */
import rosterData from "@/data/roster.json";
import { bestCounterSwap, type CounterSwap } from "@/lib/engine";

/* eslint-disable @typescript-eslint/no-explicit-any */
const ROSTER = rosterData as Record<string, RosterChampion>;

export interface RosterChampion {
  slug: string;
  name: string;
  class: string;
  role: string;
  icon: string;
  primaryDamage: string; // "physical" | "magic"
  scalesWith: string[];
  mechanics: string[]; // cc | dash | heal | onHit | shield
  baseStats: Record<string, { base?: number; perLevel?: number }>;
}

export interface DefensiveTarget {
  name: string;
  hp: number;
  armor: number;
  mr: number;
  bonusHp: number;
}

export interface ThreatProfile {
  size: number;
  adShare: number;
  apShare: number;
  primary: "AD" | "AP" | "mixed";
  healers: string[];
  shielders: string[];
  marksmen: string[];
  assassins: string[];
  ccCount: number;
  hpScalers: string[];
  frontline: DefensiveTarget;
  carry: DefensiveTarget;
  /** The enemy in your lane/role, whom you fight most (weighted 2x). */
  laneOpponent: string | null;
}

export function roster(): Record<string, RosterChampion> {
  return ROSTER;
}

/** All champions, sorted by name, for an enemy picker. */
export function rosterList(): RosterChampion[] {
  return Object.values(ROSTER).sort((a, b) => a.name.localeCompare(b.name));
}

function stat(c: RosterChampion, k: string, level: number): number {
  const s = c.baseStats[k];
  return s ? (s.base ?? 0) + (s.perLevel ?? 0) * (level - 1) : 0;
}
function ehp(c: RosterChampion, level: number): number {
  return stat(c, "hp", level) * (1 + (stat(c, "armor", level) + stat(c, "mr", level)) / 150);
}
function asTarget(c: RosterChampion, level: number): DefensiveTarget {
  const hp = stat(c, "hp", level);
  return { name: c.name, hp: Math.round(hp), armor: Math.round(stat(c, "armor", level)),
    mr: Math.round(stat(c, "mr", level)), bonusHp: Math.round(hp * 0.45) };
}

/** Derive the enemy team's threat profile at a reference level. When your lane
 *  role is given, the enemy in that role (your lane opponent) is weighted 2x in
 *  the damage split, since that's who you fight most. */
export function threatProfile(names: string[], level = 13, myRole = ""): ThreatProfile | null {
  const champs = names.map((n) => ROSTER[n]).filter(Boolean);
  if (!champs.length) return null;
  const laneChamp = myRole ? champs.find((c) => c.role === myRole) : undefined;
  const weightOf = (c: RosterChampion) => (laneChamp && c.name === laneChamp.name ? 2 : 1);
  let phys = 0, mag = 0;
  for (const c of champs) {
    if (c.primaryDamage === "physical") phys += weightOf(c);
    else if (c.primaryDamage === "magic") mag += weightOf(c);
  }
  const tot = Math.max(1, phys + mag);
  const adShare = Math.round((phys / tot) * 100) / 100;
  const apShare = Math.round((mag / tot) * 100) / 100;
  const primary = adShare >= 0.6 ? "AD" : apShare >= 0.6 ? "AP" : "mixed";

  const fronts = champs.filter((c) => c.class === "Tank" || c.class === "Bruiser");
  const frontPool = fronts.length ? fronts : champs;
  const frontline = frontPool.reduce((a, b) => (ehp(b, level) > ehp(a, level) ? b : a));
  const carry = champs.reduce((a, b) => (stat(b, "hp", level) < stat(a, "hp", level) ? b : a));

  return {
    size: champs.length, adShare, apShare, primary,
    healers: champs.filter((c) => c.mechanics.includes("heal")).map((c) => c.name),
    shielders: champs.filter((c) => c.mechanics.includes("shield")).map((c) => c.name),
    // marksmen drive crit-cutting items; onHit alone is too broad a signal
    marksmen: champs.filter((c) => c.class === "Marksman").map((c) => c.name),
    assassins: champs.filter((c) => c.class === "Assassin").map((c) => c.name),
    ccCount: champs.filter((c) => c.mechanics.includes("cc")).length,
    hpScalers: champs.filter((c) => c.scalesWith.includes("maxHp")).map((c) => c.name),
    frontline: asTarget(frontline, level),
    carry: asTarget(carry, level),
    laneOpponent: laneChamp?.name ?? null,
  };
}

export interface CounterRec {
  key: string;
  label: string;
  reason: string;
  severity: number; // 0..1, how strongly this threat applies
  items: string[]; // candidate item slugs (engine picks/scores the best swap)
  runes?: string[];
}

// Curated counter pools keyed by threat. The engine decides which to actually
// swap in and what it replaces; this narrows the search to meta-correct answers.
const COUNTER_ITEMS = {
  armor: ["thornmail", "randuins-omen", "frozen-heart", "plated-steelcaps", "dead-mans-plate"],
  mr: ["force-of-nature", "maw-of-malmortius", "wits-end", "kaenic-rookern", "mercurys-treads"],
  antiheal: ["morellonomicon", "chempunk-chainsword", "mortal-reminder"],
  shieldcut: ["serpents-fang"],
  tenacity: ["quicksilver", "mercurys-treads", "amaranths-twinguard"],
  antiburst: ["guardian-angel", "maw-of-malmortius"],
  critcut: ["randuins-omen", "frozen-heart"],
};

/** Threat profile -> ranked situational counters for this specific enemy team. */
export function recommendCounters(t: ThreatProfile): CounterRec[] {
  const recs: CounterRec[] = [];
  if (t.adShare >= 0.6)
    recs.push({ key: "armor", label: "Stack armor", severity: t.adShare,
      reason: `${Math.round(t.adShare * 100)}% of enemy damage is physical`, items: COUNTER_ITEMS.armor });
  if (t.apShare >= 0.6)
    recs.push({ key: "mr", label: "Stack magic resist", severity: t.apShare,
      reason: `${Math.round(t.apShare * 100)}% of enemy damage is magic`, items: COUNTER_ITEMS.mr });
  if (t.healers.length >= 2)
    recs.push({ key: "antiheal", label: "Apply anti-heal", severity: Math.min(1, t.healers.length / 3),
      reason: `${t.healers.length} enemies have sustain (${t.healers.slice(0, 3).join(", ")})`, items: COUNTER_ITEMS.antiheal });
  if (t.shielders.length >= 2)
    recs.push({ key: "shieldcut", label: "Cut enemy shields", severity: Math.min(1, t.shielders.length / 3),
      reason: `${t.shielders.length} enemies shield (${t.shielders.slice(0, 3).join(", ")})`, items: COUNTER_ITEMS.shieldcut });
  if (t.ccCount >= 3)
    recs.push({ key: "tenacity", label: "Buy tenacity / cleanse", severity: Math.min(1, t.ccCount / 5),
      reason: `${t.ccCount} enemies bring crowd control`, items: COUNTER_ITEMS.tenacity });
  if (t.assassins.length >= 1)
    recs.push({ key: "antiburst", label: "Survive the burst", severity: Math.min(1, t.assassins.length / 2),
      reason: `enemy assassins (${t.assassins.join(", ")}) will dive you`, items: COUNTER_ITEMS.antiburst });
  if (t.marksmen.length >= 2)
    recs.push({ key: "critcut", label: "Cut crit damage", severity: Math.min(1, t.marksmen.length / 2),
      reason: `${t.marksmen.length} crit marksmen (${t.marksmen.join(", ")})`, items: COUNTER_ITEMS.critcut });
  return recs.sort((a, b) => b.severity - a.severity);
}

export interface CounterRecScored extends CounterRec {
  swap: CounterSwap | null; // best engine-scored swap into the given build
}

/** For a specific champion build, score each counter through the fight engine
 *  against the real enemy comp: which item to add, what it replaces, and the
 *  survival/kill-speed change. Keeps only counters that actually improve. */
export function counterSwaps(name: string, items: string[], runes: string[],
                             t: ThreatProfile, level = 15, protect: string[] = []): CounterRecScored[] {
  const opts = { carry: t.carry, adShare: t.adShare, apShare: t.apShare, level, protect };
  return recommendCounters(t)
    .map((rec) => ({ ...rec, swap: bestCounterSwap(name, items, runes, rec.items, opts) }))
    .filter((r) => r.swap) as CounterRecScored[];
}
