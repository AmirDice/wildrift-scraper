/**
 * Composition analysis for the draft assistant.
 *
 * The ranker used to be one number -- ladder strength plus a handful of small
 * situational bonuses -- and the ladder term was so much larger than the
 * bonuses that composition logic could not win an argument with it. Measured:
 * against a fixed enemy comp, three deliberately different allied drafts
 * returned identical suggestions in identical order; and across ten drafts
 * built so a specific problem had a specific answer, the intended answer was
 * top-five twice, because champions like Nautilus (bottom tier, 47.4%) start
 * four points behind Leona (A tier, 51.5%) and no bonus worth two could close
 * it.
 *
 * The fix is not a bigger bonus. It is separating three questions that were
 * being added together as though they were the same one:
 *
 *   1. how strong is this champion right now
 *   2. how well does it fit what MY four already are
 *   3. how specifically does it answer what THEY are trying to do
 *
 * Each is computed on its own 0-1 scale here and weighted once, in SCORE
 * below, so the balance between them is a single readable table instead of an
 * emergent property of where the numbers happened to land.
 *
 * Interactions are multiplicative where they should be. Anti-dive is not worth
 * a flat bonus; it is worth (what this champion offers) x (how much diving
 * they actually do), which is nothing against a poke comp and decisive against
 * a layered dive.
 */
import type { Champion } from "@/lib/data";

/** The roster row this module reads. A superset of what `Champion` carries,
 *  because class alone cannot express any of it. */
export interface KitSource {
  slug: string;
  name?: string;
  class?: string;
  mechanics?: string[];
  /** How many abilities apply HARD crowd control. */
  ccDepth?: number;
  /** A shield or heal that lands on somebody else. Blitzcrank's mana barrier
   *  is not this, and counting it made him the best "protect the carry" pick. */
  protectsAllies?: boolean;
  /** Curated draft tags: aoeUlt, duelist, globalPressure, poke. */
  archetypes?: string[];
  pctHpDamage?: boolean;
  trueDamage?: boolean;
  ccImmune?: boolean;
  primaryDamage?: string;
}

const clamp = (n: number) => (n < 0 ? 0 : n > 1 ? 1 : n);
const has = (k: KitSource, m: string) => (k.mechanics ?? []).includes(m);
const tagged = (k: KitSource, t: string) => (k.archetypes ?? []).includes(t);

/** What a champion can DO, on one scale, so it can be matched against what a
 *  draft needs. Every field is 0-1. */
export interface Kit {
  frontline: number;
  peel: number;
  engage: number;
  antiDive: number;
  antiTank: number;
  /** Breaking up a committed fight: interrupts, displacement, immunity. */
  disruption: number;
  disengage: number;
  sustained: number;
  magic: number;
  physical: number;
  globalPressure: number;
}

function damageOf(k: KitSource): "AP" | "AD" | "mixed" {
  if (k.primaryDamage === "magic") return "AP";
  if (k.primaryDamage === "physical") return "AD";
  const c = k.class;
  if (c === "Mage" || c === "Enchanter") return "AP";
  if (c === "Marksman" || c === "Assassin" || c === "Bruiser") return "AD";
  return "mixed";
}

export function kitOf(k: KitSource): Kit {
  const cls = k.class ?? "";
  const tank = cls === "Tank";
  const bruiser = cls === "Bruiser";
  const ench = cls === "Enchanter";
  const marksman = cls === "Marksman";
  const cc = has(k, "cc");
  const onHit = has(k, "onHit");
  const depth = Math.min(1, (k.ccDepth ?? 0) / 3);
  const protects = !!k.protectsAllies;

  const frontline = tank ? 1 : bruiser ? 0.6 : 0;
  // Peel is protection that lands on somebody else -- and how much of the
  // champion's kit is FOR that, which is what separates a Lulu from a Galio.
  //
  // Adding a flat bonus for protecting allies put a tank who happens to shield
  // at 0.8 against an enchanter's 1.0, and since anti-dive was derived from
  // peel plus frontline, the tank then out-scored the enchanter on the very
  // axis the enchanter exists to serve. Galio came top of eight of ten test
  // drafts on the back of it. An enchanter's whole kit is protection; a tank's
  // protection is a side effect of being hard to kill.
  const peel = clamp(
    (ench ? 0.55 : 0)
    + (protects ? (ench ? 0.45 : tank ? 0.3 : 0.4) : 0)
    + (cc && !tank ? 0.15 : 0)
    + (tank ? 0.1 : 0),
  );
  const engage = clamp(frontline * (cc ? 1 : 0.2) * (0.55 + 0.45 * depth));
  const dmg = damageOf(k);

  return {
    frontline,
    peel,
    engage,
    // Surviving a dive is mostly being protected through it. Lockdown and a
    // body help, but they are not the substance -- weighting them equally made
    // every tank a better answer to a dive than the enchanters who answer it.
    antiDive: clamp(0.7 * peel + 0.2 * depth + 0.1 * frontline),
    antiTank: clamp((k.pctHpDamage ? 0.5 : 0) + (k.trueDamage ? 0.3 : 0)
      + (marksman ? 0.25 : 0) + (onHit ? 0.2 : 0)),
    disruption: clamp(0.6 * depth + (tagged(k, "aoeUlt") ? 0.25 : 0)
      + (k.ccImmune ? 0.15 : 0)),
    disengage: clamp((protects ? 0.4 : 0) + (cc && !tank ? 0.3 : 0)
      + (ench ? 0.3 : 0)),
    sustained: marksman ? 0.9 : onHit ? 0.6 : bruiser ? 0.5 : 0.2,
    magic: dmg === "AP" ? 1 : dmg === "mixed" ? 0.5 : 0,
    physical: dmg === "AD" ? 1 : dmg === "mixed" ? 0.5 : 0,
    globalPressure: tagged(k, "globalPressure") ? 1 : 0,
  };
}

export function buildKits(roster: KitSource[]): Map<string, Kit> {
  return new Map(roster.map((r) => [r.slug, kitOf(r)]));
}

// ------------------------------------------------------------------ enemy

/** What the enemy composition threatens, each 0-1. */
export interface Threats {
  dive: number;
  burst: number;
  backline: number;
  poke: number;
  frontline: number;
  hardCc: number;
  splitPush: number;
  wombo: number;
}

/** The single thing they are most trying to do. */
export type GamePlan = "dive" | "wombo" | "splitPush" | "poke" | "teamfight";

export interface EnemyRead {
  threats: Threats;
  plan: GamePlan;
  /** How pronounced the plan is, 0-1. A weak plan should not dominate. */
  planStrength: number;
}

export function readEnemy(slugs: string[], src: Map<string, KitSource>): EnemyRead {
  let tanks = 0, bruisers = 0, assassins = 0, mages = 0, mobile = 0;
  let depth = 0, duelists = 0, global_ = 0, poke = 0, aoe = 0;
  for (const s of slugs) {
    const k = src.get(s);
    if (!k) continue;
    const cls = k.class ?? "";
    if (cls === "Tank") tanks++;
    else if (cls === "Bruiser") bruisers++;
    if (cls === "Assassin") assassins++;
    if (cls === "Mage") mages++;
    if (has(k, "dash")) mobile++;
    depth += k.ccDepth ?? 0;
    if (tagged(k, "duelist")) duelists++;
    if (tagged(k, "globalPressure")) global_++;
    if (tagged(k, "poke")) poke++;
    if (tagged(k, "aoeUlt")) aoe++;
  }
  // A diver is an assassin or a bruiser who can close the gap. `dash` is not
  // trusted on its own -- that tag fires on words like "charge" and claims
  // Jinx and Ornn have one -- so it only ever refines a class signal.
  const divers = assassins + bruisers * 0.5;
  const threats: Threats = {
    dive: clamp((divers + mobile * 0.25) / 3),
    burst: clamp((assassins + mages * 0.6) / 3),
    backline: clamp((divers + mobile * 0.3) / 3),
    poke: clamp(poke / 2.5),
    frontline: clamp((tanks + bruisers * 0.5) / 2.5),
    hardCc: clamp(depth / 9),
    splitPush: clamp((duelists * 0.7 + global_ * 0.5) / 1.6),
    wombo: clamp(aoe / 3),
  };
  // The plan is whichever reading stands out, and it has to stand out: a comp
  // that is mildly everything is a teamfight comp, and saying otherwise would
  // invent a strategy to counter.
  const named: [GamePlan, number][] = [
    ["dive", threats.dive],
    ["wombo", threats.wombo],
    ["splitPush", threats.splitPush],
    ["poke", threats.poke],
  ];
  named.sort((a, b) => b[1] - a[1]);
  const [plan, strength] = named[0];
  return strength >= 0.5
    ? { threats, plan, planStrength: strength }
    : { threats, plan: "teamfight", planStrength: 0.4 };
}

// ------------------------------------------------------------------ allies

/** What your own four still need, each 0-1. */
export interface Needs {
  frontline: number;
  peel: number;
  engage: number;
  antiTank: number;
  sustained: number;
  magic: number;
  physical: number;
  antiDive: number;
  disengage: number;
}

export interface AllyRead {
  needs: Needs;
  size: number;
  tanks: number;
  /** The carry this draft is built around, if there is one to protect. */
  winCondition: string | null;
}

export function readAllies(
  slugs: string[],
  src: Map<string, KitSource>,
  enemy: Threats,
): AllyRead {
  let tanks = 0, bruisers = 0, ap = 0, ad = 0, size = 0;
  let peel = 0, engage = 0, antiTank = 0, sustained = 0;
  let carry: { name: string; score: number } | null = null;
  for (const s of slugs) {
    const k = src.get(s);
    if (!k) continue;
    size++;
    const cls = k.class ?? "";
    if (cls === "Tank") tanks++;
    else if (cls === "Bruiser") bruisers++;
    const kit = kitOf(k);
    const dmg = damageOf(k);
    if (dmg === "AP") ap++;
    if (dmg === "AD") ad++;
    peel += kit.peel;
    engage += kit.engage;
    antiTank += kit.antiTank;
    sustained += kit.sustained;
    // The win condition is the carry who most needs the team to work: a
    // marksman first, and the one with the least ability to save himself.
    if (cls === "Marksman" || cls === "Mage") {
      const claim = (cls === "Marksman" ? 1 : 0.6) * (1 - kit.frontline);
      if (!carry || claim > carry.score) carry = { name: k.name ?? s, score: claim };
    }
  }
  const front = tanks + bruisers * 0.5;
  const needs: Needs = {
    frontline: clamp(1 - front / 2),
    // Peel is needed in proportion to how hard they dive, less whatever peel
    // is already in the draft. Multiplicative on purpose: peel against a poke
    // comp is close to worthless and should score that way.
    peel: clamp(enemy.backline * (1 - peel / 2)),
    engage: clamp(1 - engage / 1.6),
    antiTank: clamp(enemy.frontline * (1 - antiTank / 1.8)),
    sustained: clamp(enemy.frontline * (1 - sustained / 2.2)),
    magic: ap === 0 ? 1 : clamp(1 - ap / 2),
    physical: ad === 0 ? 1 : clamp(1 - ad / 2),
    antiDive: clamp(enemy.dive * (1 - peel / 2)),
    disengage: clamp(Math.max(enemy.wombo, enemy.poke) * (1 - peel / 2.5)),
  };
  return { needs, size, tanks, winCondition: carry?.name ?? null };
}

// ------------------------------------------------------------------ scoring

/**
 * What each half of the answer is worth.
 *
 * Written down in one place, on one scale, because the old balance was an
 * accident: ladder strength spanned about fourteen points and every
 * composition signal was worth one or two, so the reasons printed under a
 * suggestion were decoration on a decision win rate had already made.
 */
export const WEIGHTS = {
  meta: 20,
  matchup: 20,
  needs: 40,
  plan: 20,
} as const;

export interface Breakdown {
  meta: number;
  matchup: number;
  needs: number;
  plan: number;
  total: number;
}

/** How well a kit covers a set of needs: a weighted average, so a champion is
 *  judged on the needs that are actually urgent rather than on all of them. */
function cover(needs: Needs, kit: Kit): number {
  const pairs: [number, number][] = [
    [needs.frontline, kit.frontline],
    [needs.peel, kit.peel],
    [needs.engage, kit.engage],
    [needs.antiTank, kit.antiTank],
    [needs.sustained, kit.sustained],
    [needs.magic, kit.magic],
    [needs.physical, kit.physical],
    [needs.antiDive, kit.antiDive],
    [needs.disengage, kit.disengage],
  ];
  let weight = 0, got = 0;
  for (const [need, have] of pairs) {
    weight += need;
    got += need * have;
  }
  return weight <= 0.01 ? 0 : got / weight;
}

/**
 * How well a kit answers what they threaten.
 *
 * The threat that DEFINES their game plan is excluded, because the plan
 * component below already scores exactly that and counting it twice is how
 * this went wrong the first time: against a dive comp, matchup, plan and win
 * condition all reduced to "has peel", so 45 of the 100 available points were
 * one axis measured three times and whichever support had the most peel won
 * every scenario in the benchmark.
 */
function answers(threats: Threats, kit: Kit, plan: GamePlan): number {
  const all: [GamePlan | null, number, number][] = [
    ["dive", threats.dive, kit.antiDive],
    // Burst and backline access are the same demand on the same answer, and
    // listing them separately weighted peel twice inside a single component.
    [null, Math.max(threats.burst, threats.backline), kit.peel],
    ["poke", threats.poke, kit.engage],
    [null, threats.frontline, kit.antiTank],
    [null, threats.hardCc, kit.disengage],
    ["splitPush", threats.splitPush, Math.max(kit.globalPressure, kit.frontline * 0.4)],
    ["wombo", threats.wombo, kit.disruption],
  ];
  const pairs: [number, number][] = all
    .filter(([owner]) => owner !== plan)
    .map(([, threat, have]) => [threat, have]);
  let weight = 0, got = 0;
  for (const [threat, have] of pairs) {
    weight += threat;
    got += threat * have;
  }
  return weight <= 0.01 ? 0 : got / weight;
}

/** The specific answer to what they are trying to DO, as opposed to what they
 *  are made of. This is the layer that reads Fiora + Twisted Fate as side-lane
 *  pressure rather than as a bruiser and a mage. */
function planAnswer(plan: GamePlan, kit: Kit): number {
  switch (plan) {
    case "dive": return kit.antiDive;
    case "wombo": return Math.max(kit.disruption, kit.disengage);
    case "splitPush": return Math.max(kit.globalPressure, kit.frontline * 0.5);
    // Forcing the fight. Disengage does not answer poke -- it is what you do
    // when you have ALREADY lost the spacing -- and allowing it here let peel
    // supports claim credit for solving a problem they do not solve.
    case "poke": return kit.engage;
    default: return 0.4 * kit.frontline + 0.3 * kit.peel + 0.3 * kit.antiTank;
  }
}

export function scoreCandidate(
  kit: Kit,
  meta01: number,
  ally: AllyRead,
  enemy: EnemyRead,
): Breakdown {
  // Four components, not six.
  //
  // `synergy` scored 1.00 for every candidate in the support seat -- almost
  // every support deals magic damage -- so fifteen points went to everyone
  // equally and bought no discrimination at all. Its content, damage balance,
  // is already two entries in the needs vector.
  //
  // `winCondition` was `peel`, scaled by how reachable the carry is. That is
  // the definition of `needs.peel`, so it was paying the same champion twice
  // for the same property; between it and the burst/backline pair inside
  // matchup, whichever support had the most peel collected three components
  // and won all ten benchmark drafts regardless of what the enemy was doing.
  const parts = {
    meta: meta01,
    matchup: answers(enemy.threats, kit, enemy.plan),
    needs: cover(ally.needs, kit),
    // Scaled by how pronounced the plan actually is: a comp that is only
    // mildly a dive comp should not hand its whole plan budget to a peeler.
    plan: planAnswer(enemy.plan, kit) * enemy.planStrength,
  };
  const total =
    WEIGHTS.meta * parts.meta
    + WEIGHTS.matchup * parts.matchup
    + WEIGHTS.needs * parts.needs
    + WEIGHTS.plan * parts.plan;
  return { ...parts, total: total / 10 };
}

/** Ladder strength on 0-1, so it is one component among several rather than
 *  the axis everything else is a rounding error on. */
export function metaUnit(c: Pick<Champion, "tier" | "wr">, tierScore: (t: string) => number): number {
  const wr = typeof c.wr === "number" ? c.wr : 50;
  // tier 0-5 and win rate roughly 44-56 -> a 0-1 band with the tier leading.
  return clamp((tierScore(c.tier) / 5) * 0.75 + clamp((wr - 45) / 11) * 0.25);
}

/**
 * Why this candidate scored what it did, in words.
 *
 * Derived from the same numbers as the score rather than written alongside it,
 * because the old reasons were generated by a separate ladder of if-statements
 * and could therefore disagree with the ranking they were printed under -- a
 * suggestion could say "no frontline yet" while the frontline term had
 * contributed almost nothing to why it won.
 */
export function explain(kit: Kit, ally: AllyRead, enemy: EnemyRead): string[] {
  const claims: [number, string][] = [];
  const n = ally.needs;

  claims.push([n.frontline * kit.frontline,
    ally.tanks === 0 ? "nobody on your team holds the front" : "your frontline is thin"]);
  claims.push([n.peel * kit.peel,
    ally.winCondition ? `peel for ${ally.winCondition}` : "peel for your carries"]);
  claims.push([n.engage * kit.engage, "your team cannot open a fight"]);
  claims.push([n.antiTank * kit.antiTank, "they stack health and you cannot cut it"]);
  claims.push([n.sustained * kit.sustained, "you need damage that lasts a fight"]);
  claims.push([n.magic * kit.magic, "your damage is nearly all physical"]);
  claims.push([n.physical * kit.physical, "your damage is nearly all magic"]);
  claims.push([n.antiDive * kit.antiDive, "answers the dive"]);
  claims.push([n.disengage * kit.disengage, "breaks up their engage"]);

  const plan = planAnswer(enemy.plan, kit) * enemy.planStrength;
  const planWord: Record<GamePlan, string> = {
    dive: "their comp is built to dive you",
    wombo: "they want one big teamfight, you interrupt it",
    splitPush: "they will split the map, you can answer it",
    poke: "they poke, you force the fight",
    teamfight: "straight teamfight comp",
  };
  claims.push([plan * 1.2, planWord[enemy.plan]]);

  return claims
    .filter(([w]) => w >= 0.22)
    .sort((a, b) => b[0] - a[0])
    .slice(0, 3)
    .map(([, text]) => text);
}
