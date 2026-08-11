import { getChampions, regionBoard, type Champion } from "@/lib/data";
import { getCnBySlug, CN_META } from "@/lib/cn";

/**
 * The cross-region layer: one champion, three servers, side by side.
 *
 * WHAT THESE NUMBERS ARE, because they are not the same kind of thing:
 *
 *   EU and NA are OUR measurement -- the top 50 players on each champion's
 *   leaderboard, each player's own win rate, read from the game through the
 *   same pipeline on the same device. A difference between them is a
 *   difference between the SERVERS, because nothing else differs.
 *
 *   CN is Tencent's published bracket aggregate: a whole-population sample of
 *   a different shape entirely. It is here because it is real signal about a
 *   third server, but an EU-vs-CN gap mixes region with methodology, and only
 *   an EU-vs-NA gap isolates region. Every consumer of this module is expected
 *   to say so rather than presenting three interchangeable columns.
 *
 * NA collection finished at 140 champions, so the gap now runs the other way:
 * Gragas has EU and NA but no CN ranked rows, only Legendary. A champion can
 * be missing any one region, so nothing here may assume all three are present.
 * Missing is `null`, never zero and never quietly averaged away.
 */

export type RegionKey = "EU" | "NA" | "CN";

export interface RegionRow {
  slug: string;
  name: string;
  icon: string;
  role: string;
  isHard: boolean;
  eu: number | null;
  na: number | null;
  cn: number | null;
  euTier: string | null;
  naTier: string | null;
  cnTier: string | null;
  /** Mean of the regions that HAVE a number, rounded to 0.1. */
  average: number | null;
  /** How many of the three contributed to `average`. */
  sampled: number;
  /** NA minus EU: the like-for-like regional gap, null unless both exist. */
  euNaGap: number | null;
}

const naBySlug = (() => {
  let cache: Map<string, Champion> | null = null;
  return (slug: string): Champion | undefined => {
    if (!cache) {
      cache = new Map(regionBoard("NA").champions.map((c) => [c.slug, c]));
    }
    return cache.get(slug);
  };
})();

const round1 = (n: number) => Math.round(n * 10) / 10;

export function getRegionRows(): RegionRow[] {
  const rows: RegionRow[] = [];
  for (const eu of getChampions()) {
    // A champion with no EU number at all is one we have never measured; the
    // pending-champion placeholders carry NaN precisely so they cannot be
    // rendered as data.
    const euWr = Number.isFinite(eu.wr) ? eu.wr : null;
    const na = naBySlug(eu.slug);
    const naWr = na && Number.isFinite(na.wr) ? na.wr : null;
    const cn = getCnBySlug(eu.slug);
    const cnWr = cn && Number.isFinite(cn.wr) ? cn.wr : null;

    const present = [euWr, naWr, cnWr].filter((v): v is number => v != null);
    rows.push({
      slug: eu.slug,
      name: eu.name,
      icon: eu.icon,
      role: eu.role,
      isHard: eu.isHard,
      eu: euWr,
      na: naWr,
      cn: cnWr,
      euTier: euWr == null ? null : eu.tier,
      naTier: naWr == null ? null : na!.tier,
      cnTier: cnWr == null ? null : cn!.tier,
      average: present.length ? round1(present.reduce((a, b) => a + b, 0) / present.length) : null,
      sampled: present.length,
      euNaGap: euWr != null && naWr != null ? round1(naWr - euWr) : null,
    });
  }
  return rows;
}

/** Rows where EU and NA both measured the champion, biggest divergence first.
 *  `minGap` filters out the noise floor: half a point between two 50-player
 *  samples is not a regional difference, it is sampling. */
export function getDivergence(minGap = 1.5): RegionRow[] {
  return getRegionRows()
    .filter((r) => r.euNaGap != null && Math.abs(r.euNaGap) >= minGap)
    .sort((a, b) => Math.abs(b.euNaGap!) - Math.abs(a.euNaGap!));
}

/** How much of the roster each region currently covers, for honest captions. */
export function regionCoverage() {
  const rows = getRegionRows();
  return {
    eu: rows.filter((r) => r.eu != null).length,
    na: rows.filter((r) => r.na != null).length,
    cn: rows.filter((r) => r.cn != null).length,
    euNaBoth: rows.filter((r) => r.eu != null && r.na != null).length,
    total: rows.length,
    cnBracket: CN_META.bracket,
  };
}
