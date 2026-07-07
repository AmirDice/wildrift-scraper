import cnData from "@/data/cn.json";
import { getChampion, type Champion } from "@/lib/data";

/**
 * Elo skew: how a champion's win rate moves from the whole ladder up to China's
 * top bracket (Challenger+, i.e. Challenger and above). Champions that climb are
 * high-skill specialists; champions that fall off are low-elo stompers that get
 * punished by better play.
 *
 * CN publishes win/pick/ban across cumulative rank brackets, from "All ranks" up
 * to Challenger+, giving a real skill gradient to plot against.
 */

export const BRACKETS = [
  { key: "0", label: "All ranks", short: "All" },
  { key: "1", label: "Diamond+", short: "D+" },
  { key: "2", label: "Master+", short: "M+" },
  { key: "3", label: "Challenger+", short: "Chal+" },
] as const;

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
  curve: BracketPoint[]; // one point per bracket, All ranks up to Challenger+
  low: number; // win rate at "All ranks"
  high: number; // win rate at "Challenger+"
  skew: number; // high - low; >0 scales with elo, <0 falls off
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
    const eu = getChampion(c.slug);
    if (!eu) continue;
    if (!BRACKETS.every((b) => c.byBracket[b.key])) continue; // need the full curve
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
    out.push({
      champion: eu,
      curve,
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
