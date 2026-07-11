import moversData from "@/data/cn_movers.json";

export interface Mover {
  slug: string;
  name: string;
  oldWr: number;
  newWr: number;
  delta: number;
  pickRate: number;
}

const DATA = moversData as unknown as {
  beforeDate: string;
  afterDate: string;
  patch: string;
  scope: string;
  champions: Mover[];
};

export const MOVERS_META = {
  patch: DATA.patch,
  scope: DATA.scope,
  before: DATA.beforeDate,
  after: DATA.afterDate,
};

const BY_SLUG = new Map(DATA.champions.map((m) => [m.slug, m]));

/** China win-rate change for a champion across the patch, or null. */
export function moverBySlug(slug: string): Mover | null {
  return BY_SLUG.get(slug) ?? null;
}

/** Biggest risers, highest delta first. Optionally require a minimum pick rate
 *  so we don't surface noise from rarely-played champions. */
export function topWinners(n = 10, minPick = 0.5): Mover[] {
  return DATA.champions.filter((m) => m.pickRate >= minPick && m.delta > 0).slice(0, n);
}

/** Biggest fallers, steepest drop first. */
export function topLosers(n = 10, minPick = 0.5): Mover[] {
  return DATA.champions
    .filter((m) => m.pickRate >= minPick && m.delta < 0)
    .slice()
    .reverse()
    .slice(0, n);
}
