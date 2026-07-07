import { getChampions, type Champion } from "@/lib/data";
import { getCnBySlug, getCnChampions } from "@/lib/cn";

/**
 * Cross-server "meta gap": where China's top elo (峡谷之巅 / Sovereign) disagrees with
 * the EU tracker. CN's highest bracket usually runs a patch or two ahead of the
 * West, so champions much stronger in CN than EU are a leading indicator — and
 * champions the reverse way are ones EU still overrates.
 *
 * Both win rates are compared against their OWN server's average so the gap is
 * unbiased: EU is already 50%-centered, CN Sovereign sits a touch above 50, so we
 * center CN on its own pool mean.
 */
export interface MetaGap {
  champion: Champion; // EU-shaped champion (name/slug/icon/role/class)
  euWr: number; // EU win rate (50%-centered)
  cnWr: number; // CN Sovereign win rate (raw official)
  euEdge: number; // euWr - 50
  cnEdge: number; // cnWr - CN pool mean
  gap: number; // cnEdge - euEdge; >0 => stronger in China's top elo
  contest: number; // CN pick% + ban% — how much Sovereign prioritises it
  cnPick: number;
  cnBan: number;
  euTier: string;
  cnTier: string;
  rising: boolean; // stronger in CN and genuinely contested there
}

const round1 = (n: number) => Math.round(n * 10) / 10;

/** Average CN Sovereign win rate across champions present on both servers. */
function cnMean(): number {
  const wrs = getCnChampions().map((c) => c.wr);
  return wrs.reduce((a, b) => a + b, 0) / (wrs.length || 1);
}

let _cache: MetaGap[] | null = null;

export function getMetaGaps(): MetaGap[] {
  if (_cache) return _cache;
  const mean = cnMean();
  const out: MetaGap[] = [];
  for (const eu of getChampions()) {
    const cn = getCnBySlug(eu.slug);
    if (!cn) continue;
    const euEdge = round1(eu.wr - 50);
    const cnEdge = round1(cn.wr - mean);
    const gap = round1(cnEdge - euEdge);
    const contest = round1(cn.cnPickRate + cn.cnBanRate);
    out.push({
      champion: eu,
      euWr: eu.wr,
      cnWr: cn.wr,
      euEdge,
      cnEdge,
      gap,
      contest,
      cnPick: cn.cnPickRate,
      cnBan: cn.cnBanRate,
      euTier: eu.tier,
      cnTier: cn.tier,
      // "rising" needs both a real CN edge AND top players actually picking it,
      // so a low-sample CN champ with a fluky win rate doesn't sneak in.
      rising: gap >= 1.5 && cn.cnPickRate >= 1,
    });
  }
  _cache = out.sort((a, b) => b.gap - a.gap);
  return _cache;
}

/** Champions China's top elo rates far higher than EU (undervalued in EU). */
export function risingPicks(limit?: number): MetaGap[] {
  const r = getMetaGaps().filter((g) => g.rising);
  return limit ? r.slice(0, limit) : r;
}

/** Champions EU rates higher than China's top elo does (overrated in EU). */
export function overratedInEu(limit?: number): MetaGap[] {
  const r = getMetaGaps()
    .filter((g) => g.gap <= -1.5)
    .sort((a, b) => a.gap - b.gap);
  return limit ? r.slice(0, limit) : r;
}
