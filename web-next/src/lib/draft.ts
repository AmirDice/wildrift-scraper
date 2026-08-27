import type { Champion } from "@/lib/data";

/**
 * Draft-assistant logic: availability, comp profiling and pick/ban ranking.
 *
 * Pure functions over the champion rows the site already ships -- no network,
 * no LLM -- so suggestions re-rank instantly on every tap during a live
 * draft. The deep matchup reasoning stays where it belongs, in the counter
 * build the advisor generates; nothing here claims a hard counter, because
 * the site has no per-matchup win rates to back such a claim.
 */

export type DraftRole = "Baron" | "Jungle" | "Mid" | "Dragon" | "Support";
export const DRAFT_ROLES: DraftRole[] = ["Baron", "Jungle", "Mid", "Dragon", "Support"];

/** Wild Rift drafts: 5 bans per team, and both teams may ban the same champion. */
export const MAX_BANS = 10;

export interface DraftState {
  /** Ban list, not a set: a duplicate ban really happens in the lobby and
   *  should be recorded as seen. Availability derives from the unique set. */
  bans: string[];
  /** Teammates other than the player (up to 4). */
  allies: string[];
  enemies: string[];
  me: string | null;
  myRole: DraftRole | null;
}

export const EMPTY_DRAFT: DraftState = {
  bans: [],
  allies: [],
  enemies: [],
  me: null,
  myRole: null,
};

/** Every champion no longer pickable: banned by anyone, or already locked. */
export function unavailable(state: DraftState): Set<string> {
  const out = new Set(state.bans);
  for (const s of state.allies) out.add(s);
  for (const s of state.enemies) out.add(s);
  if (state.me) out.add(state.me);
  return out;
}

const TIER_SCORE: Record<string, number> = { GOD: 5, S: 4, A: 3, B: 2, C: 1, Ass: 0 };

export function tierScore(tier: string): number {
  return TIER_SCORE[tier] ?? 1.5;
}

/** Champions whose damage is magic despite a non-mage class label. The class
 *  field alone calls Gwen and Mordekaiser "Bruiser"; comp advice about AP/AD
 *  balance needs to know better for the famous cases. */
const AP_OUTLIERS = new Set([
  "gwen", "mordekaiser", "vladimir", "singed", "diana", "akali", "katarina",
  "ekko", "fizz", "evelynn", "elise", "nidalee", "teemo", "kennen", "rumble",
  "lillia", "amumu", "maokai", "galio", "volibear",
]);

export type DamageKind = "AP" | "AD" | "mixed";

export function damageKind(c: Pick<Champion, "slug" | "class">): DamageKind {
  if (AP_OUTLIERS.has(c.slug)) return "AP";
  if (c.class === "Mage" || c.class === "Enchanter") return "AP";
  if (c.class === "Marksman" || c.class === "Assassin" || c.class === "Bruiser") return "AD";
  return "mixed"; // tanks: their damage is not why you pick them
}

export function isFrontline(c: Pick<Champion, "class">): boolean {
  return c.class === "Tank" || c.class === "Bruiser";
}

export interface CompProfile {
  frontline: number;
  ap: number;
  ad: number;
  size: number;
}

export function compProfile(slugs: string[], bySlug: Map<string, Champion>): CompProfile {
  const p: CompProfile = { frontline: 0, ap: 0, ad: 0, size: 0 };
  for (const slug of slugs) {
    const c = bySlug.get(slug);
    if (!c) continue;
    p.size += 1;
    if (isFrontline(c)) p.frontline += 1;
    const dmg = damageKind(c);
    if (dmg === "AP") p.ap += 1;
    if (dmg === "AD") p.ad += 1;
  }
  return p;
}

export interface Suggestion {
  champion: Champion;
  score: number;
  /** Short human reasons, strongest first ("GOD tier", "your team has no AP"). */
  reasons: string[];
  offRole: boolean;
  inPool: boolean;
}

/** Meta-strength baseline shared by pick and ban ranking. */
function metaScore(c: Champion): number {
  const wr = typeof c.wr === "number" ? c.wr : 50;
  return tierScore(c.tier) * 2 + (wr - 50) * 0.6;
}

function metaReason(c: Champion): string[] {
  const out: string[] = [];
  if (c.tier === "GOD" || c.tier === "S") out.push(`${c.tier} tier`);
  if (typeof c.wr === "number" && c.wr >= 53) out.push(`${c.wr}% win rate`);
  return out;
}

/**
 * Rank what the player should pick right now.
 *
 * Two questions, not one. "What is the strongest pick for this game" and
 * "what is the strongest pick I can actually play" have different answers,
 * and only the second one is actionable for most players -- nobody has all
 * 141 champions. Pass a pool to answer the second, pass an empty pool to
 * answer the first; the draft page asks both and shows them side by side.
 *
 * Scoring is meta strength, then what the ally comp still needs, then what
 * the enemy comp is actually made of. Off-role pool champions stay listed --
 * flexing is real -- but marked and behind on points.
 *
 * What it deliberately does NOT do is claim a matchup. The site has no
 * per-matchup win rates, so nothing here says "this beats that"; the lane
 * note compares two measured ladder win rates and says exactly that much.
 */
export function suggestPicks(
  state: DraftState,
  pool: string[],
  champions: Champion[],
  bySlug: Map<string, Champion>,
  limit = 6,
  enemyTraits?: EnemyTraits,
): Suggestion[] {
  const gone = unavailable(state);
  const poolSet = new Set(pool);
  const fromPool = pool.length > 0;
  const allyProfile = compProfile(state.allies, bySlug);
  const enemyProfile = compProfile(state.enemies, bySlug);
  const lane = state.myRole
    ? state.enemies.map((s) => bySlug.get(s)).find((e) => e && e.role === state.myRole)
    : undefined;

  const out: Suggestion[] = [];
  for (const c of champions) {
    if (gone.has(c.slug)) continue;
    if (fromPool && !poolSet.has(c.slug)) continue;
    const offRole = state.myRole != null && c.role !== state.myRole;
    if (!fromPool && offRole) continue; // full-roster mode stays on-role
    let score = metaScore(c);
    const reasons = metaReason(c);

    if (offRole) score -= 4;

    // what your team still needs
    if (allyProfile.size >= 2) {
      if (allyProfile.frontline === 0 && isFrontline(c)) {
        score += 1.6;
        reasons.push("your team has no frontline");
      }
      const dmg = damageKind(c);
      if (allyProfile.ap === 0 && dmg === "AP") {
        score += 1.4;
        reasons.push("your team has no AP");
      } else if (allyProfile.ad === 0 && dmg === "AD") {
        score += 1.1;
        reasons.push("your team has no AD");
      }
    }

    // what their comp is made of
    if (enemyProfile.size >= 3) {
      if (enemyProfile.ad >= 3 && isFrontline(c)) {
        score += 1.2;
        reasons.push("they are AD heavy");
      } else if (enemyProfile.ap >= 3 && isFrontline(c)) {
        score += 0.9;
        reasons.push("they are AP heavy");
      }
    }
    // A heavy enemy frontline is answered by damage that scales with their
    // health, and that is a property of the kit rather than the class: Fiora
    // and Gwen carry it where most bruisers do not.
    if (enemyTraits && enemyProfile.frontline >= 2 && enemyTraits.pctHp.has(c.slug)) {
      score += 1.5;
      reasons.push(`${enemyProfile.frontline} durable enemies, you cut max health`);
    }
    // Being dived is survived by being hard to kill, not by out-damaging it.
    if (enemyTraits && enemyTraits.assassins >= 2 && isFrontline(c)) {
      score += 0.8;
      reasons.push("they have multiple divers");
    }

    // The lane note is a comparison of two MEASURED ladder win rates, never a
    // matchup claim -- we have no per-matchup data and must not imply we do.
    if (lane && !offRole && typeof c.wr === "number" && typeof lane.wr === "number"
        && c.wr > lane.wr + 2) {
      reasons.push(`ahead of ${lane.name} on the ladder (${c.wr}% vs ${lane.wr}%)`);
    }

    out.push({
      champion: c,
      score,
      reasons: reasons.slice(0, 2).concat(offRole ? ["off-role"] : []),
      offRole,
      inPool: poolSet.has(c.slug),
    });
  }
  out.sort((a, b) => b.score - a.score);
  return out.slice(0, limit);
}

/** Kit facts about the enemy comp that class alone cannot express. */
export interface EnemyTraits {
  /** Slugs of candidates whose damage scales with the target's max health. */
  pctHp: Set<string>;
  assassins: number;
}

/**
 * Rank ban targets: the strongest champions still on the table. A champion
 * anyone already banned is excluded -- duplicate bans happen and are recorded,
 * but suggesting one would be suggesting a wasted ban. The player's own pool
 * is protected: never suggest banning a champion they want to play.
 */
export function suggestBans(
  state: DraftState,
  pool: string[],
  champions: Champion[],
  limit = 6,
): Suggestion[] {
  const gone = unavailable(state);
  const poolSet = new Set(pool);
  const out: Suggestion[] = [];
  for (const c of champions) {
    if (gone.has(c.slug) || poolSet.has(c.slug)) continue;
    let score = metaScore(c);
    const reasons = metaReason(c);
    if (state.myRole && c.role === state.myRole) {
      score += 1.0;
      reasons.push("your lane");
    }
    if (score < 6) continue; // only real threats deserve a ban slot
    out.push({ champion: c, score, reasons: reasons.slice(0, 2), offRole: false, inPool: false });
  }
  out.sort((a, b) => b.score - a.score);
  return out.slice(0, limit);
}
