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

/**
 * Whether a champion is played in a role.
 *
 * The scraped data allows one role each, which quietly hid every flex pick:
 * Olaf is listed Baron, so a jungle main was never shown the best answer in
 * the game to a crowd-control composition. `roles` carries every role the
 * champion is really played in, primary first.
 */
export function playsRole(c: Champion, role: string | null): boolean {
  if (!role) return true;
  const roles = (c as Champion & { roles?: string[] }).roles;
  return roles?.length ? roles.includes(role) : c.role === role;
}

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

/**
 * What your own half of the draft is still missing.
 *
 * The ranker used to ask three yes/no questions of the ally comp -- no
 * frontline, no AP, no AD -- and a team with one of each answered no to all
 * three. Measured against the same enemy comp, three deliberately different
 * allied drafts (a tanky team around Jinx, an all-in dive team, and a Malphite
 * wombo) produced the SAME five suggestions in the same order with identical
 * scores. Every ally term was contributing exactly nothing, so only the enemy
 * mattered, and the enemy was the thing held constant.
 *
 * These are degrees and shapes rather than absences, because "we have one
 * frontliner" and "we have three" are different drafts, and because who your
 * carry is decides whether the last pick should peel or engage.
 */
export interface AllyNeeds {
  size: number;
  frontline: number;
  ap: number;
  ad: number;
  /** Tanks specifically. A Bruiser counts as half a frontline and a Tank as a
   *  whole one, because `Tank || Bruiser` called Lee Sin and Yasuo the front
   *  line -- which is how three very different drafts all reported two
   *  frontliners and every frontline term cancelled out. */
  tanks: number;
  bruisers: number;
  /** Carries with no way out: a marksman or mage with no dash who is not
   *  himself a frontliner. This is who peel is FOR, and the reason a Jinx
   *  team and an Ezreal team want different support picks. */
  immobileCarries: string[];
  /** Allies who can START a fight: a frontliner who also brings hard crowd
   *  control. Two of them is a wombo that wants following up, not peeling. */
  engage: number;
  /** Allies who go in first and go in alone. */
  divers: number;
}

export function buildAllyNeeds(
  allies: string[],
  roster: TraitSource[],
  bySlug: Map<string, Champion>,
): AllyNeeds {
  const mech = (mech: string) =>
    new Set(roster.filter((c) => (c.mechanics ?? []).includes(mech)).map((c) => c.slug));
  const mobile = mech("dash");
  const lockdown = mech("cc");
  const needs: AllyNeeds = {
    size: 0, frontline: 0, ap: 0, ad: 0, tanks: 0, bruisers: 0,
    immobileCarries: [], engage: 0, divers: 0,
  };
  for (const slug of allies) {
    const c = bySlug.get(slug);
    if (!c) continue;
    needs.size += 1;
    const front = isFrontline(c);
    if (front) needs.frontline += 1;
    if (c.class === "Tank") needs.tanks += 1;
    else if (c.class === "Bruiser") needs.bruisers += 1;
    const dmg = damageKind(c);
    if (dmg === "AP") needs.ap += 1;
    if (dmg === "AD") needs.ad += 1;
    if (front && lockdown.has(slug)) needs.engage += 1;
    if (c.class === "Assassin"
        || (mobile.has(slug) && (c.class === "Bruiser" || c.class === "Fighter"))) {
      needs.divers += 1;
    }
    // NOT gated on the `dash` mechanic. That tag fires on words like
    // "charge" and currently claims Jinx, Ornn, Malphite and Viktor all have
    // a dash, so using it to decide who can escape a fight would be guessing.
    // A marksman is the champion who gets diven; that much is safe to say.
    if (c.class === "Marksman" && !front) needs.immobileCarries.push(c.name);
  }
  return needs;
}

export interface Suggestion {
  champion: Champion;
  score: number;
  /** Short human reasons, strongest first ("GOD tier", "your team has no AP"). */
  reasons: string[];
  offRole: boolean;
  inPool: boolean;
}

/**
 * Meta-strength baseline shared by pick and ban ranking.
 *
 * It used to be tier*2 + (wr-50)*0.6, which spans about fourteen points while
 * every contextual signal below is worth between one and four. Meta strength
 * therefore decided the order outright and the stated reasons were decoration:
 * the suggestion against a five-man lockdown comp was whoever had the best win
 * rate, and the champion who walks through lockdown ranked under them.
 *
 * Compressed to about six points, so an actual answer to what the enemy is
 * doing can outrank a tier of ladder performance. Win rate is a nudge rather
 * than a driver now -- and since the tier is itself derived from win rate, it
 * was being counted twice.
 *
 * Kept deliberately identical to DraftState.metaScore in the overlay. The two
 * rank the same champions from the same data and users compare them.
 */
function metaScore(c: Champion): number {
  const wr = typeof c.wr === "number" ? c.wr : 50;
  return tierScore(c.tier) * 1.2 + (wr - 50) * 0.10;
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
  allyNeeds?: AllyNeeds,
): Suggestion[] {
  const gone = unavailable(state);
  const poolSet = new Set(pool);
  const fromPool = pool.length > 0;
  const protective = enemyTraits?.protective ?? new Set<string>();
  const allyProfile = compProfile(state.allies, bySlug);
  const enemyProfile = compProfile(state.enemies, bySlug);
  const lane = state.myRole
    ? state.enemies.map((s) => bySlug.get(s)).find((e) => e && playsRole(e, state.myRole))
    : undefined;

  const out: Suggestion[] = [];
  for (const c of champions) {
    if (gone.has(c.slug)) continue;
    if (fromPool && !poolSet.has(c.slug)) continue;
    const offRole = !playsRole(c, state.myRole);
    if (!fromPool && offRole) continue; // full-roster mode stays on-role
    let score = metaScore(c);
    const reasons = metaReason(c);

    if (offRole) score -= 4;

    // what your team still needs
    const needs: AllyNeeds = allyNeeds ?? {
      ...allyProfile, tanks: 0, bruisers: 0,
      immobileCarries: [], engage: 0, divers: 0,
    };
    if (needs.size >= 2) {
      // FRONTLINE, WEIGHTED. A Tank is a frontline; a Bruiser is half of one.
      // Counting them equally made a Malphite team and a Camille/Yasuo team
      // look identical, and they want opposite things from the last pick.
      const front = needs.tanks + needs.bruisers * 0.5;
      const frontNeed = Math.max(0, 1.5 - front);
      if (frontNeed > 0.01 && isFrontline(c)) {
        score += frontNeed * 1.1;
        reasons.push(needs.tanks === 0
          ? "nobody on your team holds the front" : "your frontline is thin");
      }
      // DAMAGE BALANCE, BY RATIO. A team of three physical and one magic is
      // itemised against as cheaply as a team of four, and it answered "no"
      // to the old question because AP was not literally zero.
      const dmg = damageKind(c);
      if (needs.ap === 0 && dmg === "AP") {
        score += 1.4;
        reasons.push("your team has no AP");
      } else if (needs.ad === 0 && dmg === "AD") {
        score += 1.1;
        reasons.push("your team has no AD");
      } else if (needs.ad >= needs.ap * 2 && dmg === "AP") {
        score += 0.8;
        reasons.push("your damage is nearly all physical");
      } else if (needs.ap >= needs.ad * 2 && dmg === "AD") {
        score += 0.7;
        reasons.push("your damage is nearly all magic");
      }
      // PEEL vs ENGAGE -- the two answers a last pick can be, and the whole
      // reason the old ranking could not tell three drafts apart. Every
      // candidate had crowd control, so a bonus keyed on crowd control lifted
      // all of them equally and moved nobody. These key on what the champion
      // brings INSTEAD: a shield or a heal is protection, a frontliner with
      // lockdown is an opener.
      const protects = protective.has(c.slug);
      const opens = isFrontline(c) && (enemyTraits?.lockdown.has(c.slug) ?? false);

      if (needs.tanks === 0 && needs.size >= 3 && opens) {
        // Nobody to start a fight and nobody to survive being in one. This
        // outranks peel: protecting a carry behind a line that does not exist
        // is protecting them in the open.
        score += 1.8;
        reasons.push("your team has nobody to open a fight");
      } else if (needs.immobileCarries.length > 0 && protects) {
        // The front is held, so the last pick's job is keeping the carry
        // alive behind it -- and it names who.
        const dived = (enemyTraits?.divers ?? 0) >= 2;
        score += dived ? 1.6 : 1.0;
        reasons.push(dived
          ? `peel for ${needs.immobileCarries[0]} against their dive`
          : `peel for ${needs.immobileCarries[0]}`);
      }
      // A wombo wants more of itself on top, whoever else is picked.
      if (needs.engage >= 2 && opens) {
        score += 0.9;
        reasons.push("follow-up for your engage");
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
    // Ignoring the enemy's entire win condition is worth more than being a
    // tier stronger. This is the exact mirror of the "no escape from their
    // dive" penalty below, and it is weighted the same: two tiers. Without it
    // a five-enemy lockdown composition produced Hecarim, Pantheon and Diana
    // ABOVE Olaf, whose ultimate removes every debuff and makes him immune --
    // the best answer in the game to that draft, ranked fourth on tier alone.
    // Gated on DEPTH as well as head count. Three champions with one stun
    // each is an ordinary team, and it was reading as a lockdown composition
    // worth throwing the draft at -- which, back when the `cc` trait fired on
    // the word "slow" and covered two thirds of the roster, was most teams.
    if (enemyTraits && enemyTraits.ccEnemies >= 3 && enemyTraits.ccDepth >= 6
        && enemyTraits.ccImmune.has(c.slug)) {
      score += enemyTraits.ccDepth >= 9 ? 4 : 2.5;
      reasons.push(`${enemyTraits.ccEnemies} of them lock you down, you clear it`);
    }
    // A heavy enemy frontline is answered by damage that ignores how much
    // health they stacked, whether that is percent-health or true damage.
    // True damage was missing, which is why Olaf never registered against a
    // team of tanks: he carries no percent-health damage at all.
    if (enemyTraits && enemyProfile.frontline >= 2
        && (enemyTraits.pctHp.has(c.slug) || enemyTraits.trueDamage.has(c.slug))) {
      score += 1.5;
      const how = enemyTraits.pctHp.has(c.slug) ? "you cut max health" : "your damage is true";
      reasons.push(`${enemyProfile.frontline} durable enemies, ${how}`);
    }
    // Being dived is survived by being hard to kill, not by out-damaging it.
    if (enemyTraits && enemyTraits.assassins >= 2 && isFrontline(c)) {
      score += 0.8;
      reasons.push("they have multiple divers");
    }
    // A carry with no way out of a dive composition is a sitting duck, and
    // ranking on tier alone kept offering exactly that: a immobile marksman
    // into three champions built to jump on it. Win rate is measured across
    // all games, not across this one.
    if (enemyTraits && enemyTraits.divers >= 3 && !isFrontline(c)
        && !enemyTraits.mobile.has(c.slug)) {
      // Two tiers' worth. Being unable to survive the enemy's whole plan is a
      // bigger problem than being one tier weaker, and at half this weight an
      // S-tier immobile marksman still came second into a three-diver comp.
      score -= 4;
      reasons.push("no escape from their dive");
    }
    // Skillshots miss champions who can dash out of them, so a comp full of
    // mobility is caught by lockdown that does not have to be aimed.
    if (enemyTraits && enemyTraits.mobileEnemies >= 3 && enemyTraits.lockdown.has(c.slug)) {
      score += 1.0;
      reasons.push("lockdown for a mobile comp");
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
  // On-role FIRST, always. A pool spans several roles, so a support main's
  // Nami outscored their own junglers for a jungle game on tier alone: a -4
  // points penalty cannot survive a two-tier gap, and no numeric weight
  // should decide whether you are allowed to play a support in the jungle.
  // Off-role stays listed, because flexing is real, but it stays underneath.
  out.sort((a, b) => Number(a.offRole) - Number(b.offRole) || b.score - a.score);
  return out.slice(0, limit);
}

/** Kit facts that class alone cannot express, for both sides of the draft. */
export interface EnemyTraits {
  /** Slugs of candidates whose damage scales with the target's max health. */
  pctHp: Set<string>;
  /** Slugs whose damage ignores resistances outright. Olaf answers a stacked
   *  frontline this way and carries no percent-health damage at all, so
   *  without this he registered as no answer to a team of tanks. */
  trueDamage: Set<string>;
  /** Slugs whose kit removes or ignores crowd control (Olaf's ultimate,
   *  Sivir's spell shield). The single most decision-relevant fact against a
   *  lockdown composition, and invisible to class. */
  ccImmune: Set<string>;
  /** Slugs of champions with a dash or blink, on either team. */
  mobile: Set<string>;
  /** Slugs with hard crowd control, for judging whether a pick can catch. */
  lockdown: Set<string>;
  /** Champions who can protect somebody: a shield, a heal, or an enchanter's
   *  kit. Distinct from `lockdown`, which is nearly the whole roster and so
   *  cannot tell a Janna from a Leona -- the exact confusion that made three
   *  different allied drafts produce one answer. */
  protective: Set<string>;
  assassins: number;
  /** How many enemies can close the gap onto a backline. */
  divers: number;
  /** How many enemies can dash out of a skillshot. */
  mobileEnemies: number;
  /** How many enemies can lock you down. */
  ccEnemies: number;
  /** How many enemy ABILITIES lock you down, not how many champions carry one.
   *  Presence alone put Sona -- a single stun on her ultimate -- level with
   *  Alistar, who has three and lands them on demand. */
  ccDepth: number;
}

/** The roster fields the trait builder reads. Passed in rather than imported
 *  so this module stays free of data imports and testable with fixtures. */
export interface TraitSource {
  slug: string;
  class?: string;
  pctHpDamage?: boolean;
  trueDamage?: boolean;
  ccImmune?: boolean;
  mechanics?: string[];
  ccDepth?: number;
}

/**
 * Build the enemy-trait bundle from the roster.
 *
 * Lives here because it was written twice -- once in the draft page and once
 * in the report harness -- and the two drifted, so a trait added for one was
 * missing from the other.
 */
export function buildEnemyTraits(
  enemies: string[],
  roster: TraitSource[],
  bySlug: Map<string, Champion>,
): EnemyTraits {
  const withMech = (mech: string) =>
    new Set(roster.filter((c) => (c.mechanics ?? []).includes(mech)).map((c) => c.slug));
  const flagged = (key: keyof TraitSource) =>
    new Set(roster.filter((c) => c[key]).map((c) => c.slug));
  const mobile = withMech("dash");
  const lockdown = withMech("cc");
  const depthBySlug = new Map(roster.map((c) => [c.slug, c.ccDepth ?? 0]));
  return {
    pctHp: flagged("pctHpDamage"),
    trueDamage: flagged("trueDamage"),
    ccImmune: flagged("ccImmune"),
    mobile,
    lockdown,
    protective: new Set(
      roster.filter((c) => c.class === "Enchanter"
        || (c.mechanics ?? []).includes("shield")
        || (c.mechanics ?? []).includes("heal")).map((c) => c.slug)),
    assassins: enemies.filter((s) => bySlug.get(s)?.class === "Assassin").length,
    // Anyone who can reach a backline: an assassin, or a bruiser with a gap
    // closer. Class alone called Camille a bruiser and missed the dive.
    divers: enemies.filter((s) => {
      const c = bySlug.get(s);
      return c?.class === "Assassin"
        || (mobile.has(s) && (c?.class === "Bruiser" || c?.class === "Fighter"));
    }).length,
    mobileEnemies: enemies.filter((s) => mobile.has(s)).length,
    ccEnemies: enemies.filter((s) => lockdown.has(s)).length,
    ccDepth: enemies.reduce((n, s) => n + (depthBySlug.get(s) ?? 0), 0),
  };
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
    if (state.myRole && playsRole(c, state.myRole)) {
      score += 1.0;
      reasons.push("your lane");
    }
    if (score < 6) continue; // only real threats deserve a ban slot
    out.push({ champion: c, score, reasons: reasons.slice(0, 2), offRole: false, inPool: false });
  }
  out.sort((a, b) => b.score - a.score);
  return out.slice(0, limit);
}
