import cnData from "@/data/cn.json";
import { getChampion, type Champion } from "@/lib/data";
import { getCnBySlug } from "@/lib/cn";

/**
 * Skill-bracket change: how a champion's win rate moves across Tencent's
 * cumulative regular-ranked samples. These are population brackets, not
 * isolated ranks: Diamond+ includes the higher regular ranks and Master+ does
 * too. Legendary is retained as a separate solo-queue benchmark.
 */

export const BRACKETS = [
  { key: "1", label: "Diamond+", short: "D+" },
  { key: "2", label: "Master+", short: "M+" },
  { key: "3", label: "Challenger", short: "Chal" },
] as const;

export const LEGENDARY_BRACKET = {
  key: "4",
  label: "Legendary",
  short: "Legendary",
} as const;

export interface BracketPoint {
  key: string;
  label: string;
  short: string;
  wr: number;
  pick: number;
  ban: number;
}

export interface EloSkew {
  champion: Champion;
  curve: BracketPoint[]; // cumulative regular-ranked samples
  legendary: BracketPoint | null; // separate Legendary solo-queue benchmark
  low: number; // win rate at Diamond+
  high: number; // win rate at Challenger
  skew: number; // Challenger - Diamond+
  climbing: boolean; // meaningfully better in higher elo
  stomper: boolean; // meaningfully worse in higher elo
}

interface CnEntry {
  winRate: number;
  pickRate: number;
  banRate: number;
  strength: number;
  position: string;
}
interface CnChamp {
  slug: string;
  byBracket: Record<string, CnEntry>;
}
const CN = cnData as unknown as { champions: CnChamp[] };

const round1 = (n: number) => Math.round(n * 10) / 10;

let _cache: EloSkew[] | null = null;

export function getEloSkews(): EloSkew[] {
  if (_cache) return _cache;
  const out: EloSkew[] = [];
  for (const c of CN.champions) {
    const eu = getChampion(c.slug) ?? getCnBySlug(c.slug);
    if (!eu) continue;
    if (!BRACKETS.every((b) => c.byBracket[b.key])) continue; // need the regular-ranked curve
    // Skip flex picks whose CN lane isn't the same across every bracket, since a
    // mixed-lane curve would give a misleading skew. Their tier data stays correct
    // elsewhere.
    if (new Set(BRACKETS.map((b) => c.byBracket[b.key].position)).size > 1) continue;
    const curve: BracketPoint[] = BRACKETS.map((b) => {
      const e = c.byBracket[b.key];
      return { key: b.key, label: b.label, short: b.short, wr: e.winRate, pick: e.pickRate, ban: e.banRate };
    });
    const low = curve[0].wr;
    const high = curve[curve.length - 1].wr;
    const skew = round1(high - low);
    const legendaryEntry = c.byBracket[LEGENDARY_BRACKET.key];
    const legendary = legendaryEntry
      && legendaryEntry.position === c.byBracket[BRACKETS[0].key].position
        ? {
            key: LEGENDARY_BRACKET.key,
            label: LEGENDARY_BRACKET.label,
            short: LEGENDARY_BRACKET.short,
            wr: legendaryEntry.winRate,
            pick: legendaryEntry.pickRate,
            ban: legendaryEntry.banRate,
          }
        : null;
    out.push({
      champion: eu,
      curve,
      legendary,
      low,
      high,
      skew,
      climbing: skew >= 1.5,
      stomper: skew <= -1.5,
    });
  }
  _cache = out.sort((a, b) => b.skew - a.skew);
  return _cache;
}

/** High-skill specialists: best in the hands of top players. */
export function climbingPicks(limit?: number): EloSkew[] {
  const r = getEloSkews().filter((s) => s.climbing);
  return limit ? r.slice(0, limit) : r;
}

/** Low-elo stompers: strong to climb with, weaker up top. */
export function stomperPicks(limit?: number): EloSkew[] {
  const r = getEloSkews()
    .filter((s) => s.stomper)
    .sort((a, b) => a.skew - b.skew);
  return limit ? r.slice(0, limit) : r;
}

let _bySlug: Map<string, EloSkew> | null = null;
export function getSkewBySlug(slug: string): EloSkew | undefined {
  if (!_bySlug) _bySlug = new Map(getEloSkews().map((s) => [s.champion.slug, s]));
  return _bySlug.get(slug);
}
