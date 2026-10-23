import partnerData from "@/data/cn_partners.json";
import siteData from "@/data/site.json";

/**
 * Best duo partners from the CN companion app's 最佳拍档 lists
 * (scripts/walk_partners.py -> export_partners_for_web.py).
 *
 * Each pair's appearance rate is tiny (around 1% of games), so ranking by
 * win rate alone would crown pairs seen a handful of times. Each list is
 * ranked by win rate pulled toward that list's average, by as much as the
 * list's median appearance rate: a pair played that often counts half its
 * own rate, half the average. The same shrinkage as the loadouts, with the
 * prior taken from the data because these shares run two orders of
 * magnitude below a loadout row's.
 */
type Pair = { a: string; aLane: string; b: string; bLane: string; winRate: number; pickRate: number };
const DATA = partnerData as unknown as { capturedAt: string | null; bracket: string | null; pairs: Pair[] };
const CHAMPS = new Map((siteData.champions as { slug: string; name: string; icon: string }[]).map((c) => [c.slug, c]));

export type Partner = { slug: string; name: string; icon: string; lane: string; winRate: number; pickRate: number; score: number };

export const LANE_ORDER = ["baron", "jungle", "mid", "dragon", "support"];

function rank(list: { winRate: number; pickRate: number }[]) {
  const total = list.reduce((s, p) => s + p.pickRate, 0);
  const average = total ? list.reduce((s, p) => s + p.winRate * p.pickRate, 0) / total : 50;
  const sorted = [...list].map((p) => p.pickRate).sort((x, y) => x - y);
  const prior = sorted.length ? sorted[Math.floor(sorted.length / 2)] : 1;
  return (p: { winRate: number; pickRate: number }) => (p.winRate * p.pickRate + average * prior) / (p.pickRate + prior);
}

export function partnersCapturedAt(): string | null {
  return DATA.pairs.length ? DATA.capturedAt : null;
}

/** A champion's partners in one of its lanes, grouped by the partner's lane, best first. */
export function partnersFor(slug: string, lane: string, perLane = 5): { lane: string; partners: Partner[] }[] {
  const mine = DATA.pairs.flatMap((p) => {
    if (p.a === slug && p.aLane === lane) return [{ slug: p.b, lane: p.bLane, winRate: p.winRate, pickRate: p.pickRate }];
    if (p.b === slug && p.bLane === lane) return [{ slug: p.a, lane: p.aLane, winRate: p.winRate, pickRate: p.pickRate }];
    return [];
  });
  return LANE_ORDER.filter((l) => l !== lane).flatMap((partnerLane) => {
    const list = mine.filter((p) => p.lane === partnerLane);
    if (!list.length) return [];
    const score = rank(list);
    const partners = list
      .map((p) => {
        const champ = CHAMPS.get(p.slug);
        return champ ? { ...p, name: champ.name, icon: champ.icon, score: Math.round(score(p) * 10) / 10 } : null;
      })
      .filter((p): p is Partner => p != null)
      .sort((x, y) => y.score - x.score)
      .slice(0, perLane);
    return partners.length ? [{ lane: partnerLane, partners }] : [];
  });
}

export type Duo = { a: Partner; b: Partner; winRate: number; pickRate: number; score: number };

/** The best pairs for each lane pairing (Dragon + Support, Jungle + Mid, ...). */
export function bestDuos(perPair = 8): { lanes: [string, string]; duos: Duo[] }[] {
  const groups = new Map<string, Pair[]>();
  for (const p of DATA.pairs) {
    const lanes = [p.aLane, p.bLane].sort((x, y) => LANE_ORDER.indexOf(x) - LANE_ORDER.indexOf(y));
    const key = lanes.join("+");
    groups.set(key, [...(groups.get(key) ?? []), p]);
  }
  return [...groups.entries()].map(([key, list]) => {
    const score = rank(list);
    const duos = list.flatMap((p) => {
      const a = CHAMPS.get(p.a); const b = CHAMPS.get(p.b);
      if (!a || !b) return [];
      const s = Math.round(score(p) * 10) / 10;
      const mk = (c: { slug: string; name: string; icon: string }, lane: string): Partner => ({ slug: c.slug, name: c.name, icon: c.icon, lane, winRate: p.winRate, pickRate: p.pickRate, score: s });
      // Lane order inside the duo, so Dragon + Support always reads that way.
      const first = LANE_ORDER.indexOf(p.aLane) <= LANE_ORDER.indexOf(p.bLane);
      return [{ a: first ? mk(a, p.aLane) : mk(b, p.bLane), b: first ? mk(b, p.bLane) : mk(a, p.aLane), winRate: p.winRate, pickRate: p.pickRate, score: s }];
    }).sort((x, y) => y.score - x.score).slice(0, perPair);
    return { lanes: key.split("+") as [string, string], duos };
  }).filter((g) => g.duos.length)
    .sort((x, y) => (x.lanes.join() === "dragon,support" ? -1 : y.lanes.join() === "dragon,support" ? 1 : 0));
}
