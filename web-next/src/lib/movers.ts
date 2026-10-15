import moversData from "@/data/cn_movers.json";
import type { CnBracketKey } from "@/lib/cn";

const FALLBACK_BRACKET: CnBracketKey = "3";

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
  /** First day of games on `patch`, yyyymmdd. */
  patchLive?: string;
  /** Days of games on `patch` inside the after-snapshot. 0 = none yet. */
  postPatchDays?: number;
  scope: string;
  defaultBracket?: CnBracketKey;
  champions: Mover[];
  byBracket?: Partial<Record<CnBracketKey, Mover[]>>;
};

export const MOVERS_META = {
  patch: DATA.patch,
  patchLive: DATA.patchLive ?? "",
  postPatchDays: DATA.postPatchDays ?? 0,
  scope: DATA.scope,
  before: DATA.beforeDate,
  after: DATA.afterDate,
  /**
   * Does this window measure its patch at all?
   *
   * The labels used to come from the site's CURRENT_PATCH, so the moment the
   * data moved to 7.3b the page announced "Patch 7.3b Movers" over a window
   * that ran from 25 August to 21 September. The window now names its own
   * patch, and until it holds at least one day of games on that patch it is
   * pre-patch drift, which must not be presented as the patch's verdict.
   */
  measuresPatch: Boolean(DATA.patch) && (DATA.postPatchDays ?? 0) >= 1,
};

const bracketRows = (bracket: CnBracketKey) => DATA.byBracket?.[bracket]
  ?? (bracket === (DATA.defaultBracket ?? FALLBACK_BRACKET) ? DATA.champions : []);
const BY_BRACKET_SLUG = new Map<CnBracketKey, Map<string, Mover>>();

/** China win-rate change for a champion between scrapes, or null. */
export function moverBySlug(
  slug: string,
  bracket: CnBracketKey = DATA.defaultBracket ?? FALLBACK_BRACKET,
): Mover | null {
  let bySlug = BY_BRACKET_SLUG.get(bracket);
  if (!bySlug) {
    bySlug = new Map(bracketRows(bracket).map((m) => [m.slug, m]));
    BY_BRACKET_SLUG.set(bracket, bySlug);
  }
  return bySlug.get(slug) ?? null;
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
