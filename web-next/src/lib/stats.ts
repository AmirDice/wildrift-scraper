/**
 * Product counters: how much the site is actually used.
 *
 * Two questions this answers:
 *   - the public one, shown on the home page: how many builds have players
 *     generated? (EVENT_BUILD_GENERATED)
 *   - the internal one: are people using the build tools at all, or only
 *     reading the tier list? Every tracked event keeps a lifetime total and a
 *     per-UTC-day total, so usage can be compared day over day and feature by
 *     feature without adding an analytics vendor.
 *
 * All writes are fire-and-forget: a counter must never fail a user request.
 */
import { dayKey, kvGet, kvGetNumber, kvGetNumbers, kvIncr, kvPushCapped, kvSet, kvSetAdd, kvSetCount } from "@/lib/kv";

/** Events worth counting. Keep the list closed so a typo cannot create a key. */
export const TRACKED_EVENTS = [
  "build_generated",
  "build_saved",
  "build_shared",
  "build_liked",
  "build_feedback",
  "counter_generated",
  "tour_started",
  "tour_completed",
  "tour_skipped",
  "signed_in",
  // The bottom-right flagship nudge: shown / clicked / dismissed, so the
  // question "does the nudge move anyone" is answered by counters rather
  // than argued about.
  "nudge_shown",
  "nudge_clicked",
  "nudge_dismissed",
  // The Custom Build Lab is entirely client-side, so without these two it is
  // invisible to every counter: opened = the tab was shown, edited = the
  // visitor actually changed something in it.
  "custom_opened",
  "custom_edited",
  // Someone pressed Generate with nothing left in their allowance. The depth
  // histogram cannot show this: it counts generations that HAPPENED, and the
  // cap means a sixth never does. Demand above the ceiling is invisible
  // without recording the refusal itself.
  "limit_reached_anon",     // ...and signing in would give them 5 more
  "limit_reached_signed_in", // ...and there is nothing left to unlock
] as const;

export type TrackedEvent = (typeof TRACKED_EVENTS)[number];

export function isTrackedEvent(value: unknown): value is TrackedEvent {
  return typeof value === "string" && (TRACKED_EVENTS as readonly string[]).includes(value);
}

const DAY_SECONDS = 60 * 60 * 24;
/** Per-day buckets are kept for a quarter; the lifetime totals never expire. */
const DAY_BUCKET_TTL = DAY_SECONDS * 100;

const totalKey = (event: string) => `stat:${event}:total`;
const dailyKey = (event: string, day = dayKey()) => `stat:${event}:day:${day}`;

/** Records one occurrence of an event. Errors are swallowed by design. */
export async function trackEvent(event: TrackedEvent, by = 1): Promise<void> {
  try {
    await Promise.all([
      kvIncr(totalKey(event), by),
      kvIncr(dailyKey(event), by, DAY_BUCKET_TTL),
    ]);
  } catch {
    /* counters are never worth failing a request over */
  }
}

/** Lifetime count for one event. */
export async function eventTotal(event: TrackedEvent): Promise<number> {
  return kvGetNumber(totalKey(event));
}

/** Lifetime + last-N-days counts, for the usage read-out. */
export async function eventSummary(event: TrackedEvent, days = 7) {
  const dayKeys: string[] = [];
  for (let offset = 0; offset < days; offset += 1) {
    const date = new Date();
    date.setUTCDate(date.getUTCDate() - offset);
    dayKeys.push(dailyKey(event, dayKey(date)));
  }
  const [total, ...perDay] = await kvGetNumbers([totalKey(event), ...dayKeys]);
  return {
    event,
    total,
    today: perDay[0] ?? 0,
    lastDays: perDay,
    windowTotal: perDay.reduce((sum, value) => sum + value, 0),
  };
}

/* ── generation engagement ───────────────────────────────────────────────── */
//
// The aggregate counters above say HOW MANY generations happened; these say
// how people use their allowance. Recorded at consume time from the quota
// counter itself, so the depth is exact and costs no scan:
//
//   stat:gen_depth:<day>:<n>  people whose Nth generation of the day this was
//   gen:users:<day>           distinct identities that generated (set)
//   gen:users:all             every identity that has ever generated (set)
//   stat:gen_new / _returning per-day split, derived from gen:users:all at
//                             the moment of each identity's FIRST generation
//                             of the day (SADD's return value, no scanning)
//
// "Used exactly N" is depth[N] - depth[N+1]; "burned the whole allowance" is
// depth[limit]. Identity matches the quota key: Google sub when signed in,
// hashed IP otherwise -- visits, not people, with the same imprecision the
// quota itself already accepts.

/** Depths beyond the allowance (unlimited codes) all land in one bucket. */
const DEPTH_CAP = 6;

/**
 * A build was delivered to someone.
 *
 * `depth` is which generation of their daily allowance this was.
 *
 * A cache hit still counts as usage. It was invisible here until 2026-08-09,
 * because the route returned cached builds before any tracking ran, which
 * undercounted the public "builds generated" figure and, worse, could not see
 * a returning player whose builds all came from cache -- exactly the person
 * retention is trying to measure.
 *
 * The depth histogram used to exclude cache hits, on the reasoning that depth
 * measures consumption of an allowance a cache hit never touched. That stopped
 * being true on 2026-08-10, when cache hits began spending the allowance like
 * any other build: the quota is there to measure demand, not to bill for model
 * calls, so a served build counts whoever served it. Depth is therefore passed
 * for cache hits too, and NULL now means only "not counted against a quota"
 * (unlimited-code holders), not "came from cache".
 */
export async function recordGenerationEngagement(
  identity: string,
  depth: number | null,
): Promise<void> {
  try {
    const day = dayKey();
    const writes: Promise<unknown>[] = [recordCohort(identity)];
    if (depth != null) {
      const bucket = Math.min(Math.max(depth, 1), DEPTH_CAP);
      writes.push(kvIncr(`stat:gen_depth:${day}:${bucket}`, 1, DAY_BUCKET_TTL));
    }
    // New-vs-returning keys off the DAILY set rather than depth === 1: a
    // cache-hit-only visit has no depth, and gating on depth silently dropped
    // those people from the split entirely.
    writes.push((async () => {
      const firstUseToday = await kvSetAdd(`gen:users:${day}`, identity, DAY_BUCKET_TTL);
      if (!firstUseToday) return;
      const neverSeenBefore = await kvSetAdd("gen:users:all", identity);
      await kvIncr(`stat:${neverSeenBefore ? "gen_new" : "gen_returning"}:day:${day}`, 1, DAY_BUCKET_TTL);
    })());
    await Promise.all(writes);
  } catch {
    /* engagement is never worth failing a generation over */
  }
}

/* ── cohort retention ────────────────────────────────────────────────────── */
//
// The depth histogram says how hard someone used the tool on one day. It says
// nothing about whether they came back, which is the question that decides
// whether the Build Studio is worth marketing.
//
// So each identity's FIRST generation stamps them with a date and files them
// into that ISO week's cohort. Every later generation measures the gap and
// files them into the d1 / d7 / d30 bucket of the cohort they started in.
// Retention is then a plain set ratio: |cohort:W:d7| / |cohort:W:new|.
//
// Sets, not counters, because a person who returns three times in week one
// must count once. TTLs are long enough to see a 30-day window through.

const COHORT_TTL = DAY_SECONDS * 200;

/** ISO-week key (YYYY-Www) -- weekly buckets, because at ~40 generators a day
 *  a daily cohort is too small to read a percentage off. */
function weekKey(date = new Date()): string {
  const d = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()));
  // ISO weeks start Monday and week 1 contains the first Thursday.
  const dayNum = (d.getUTCDay() + 6) % 7;
  d.setUTCDate(d.getUTCDate() - dayNum + 3);
  const firstThursday = new Date(Date.UTC(d.getUTCFullYear(), 0, 4));
  const week = 1 + Math.round(
    ((d.getTime() - firstThursday.getTime()) / 86400000 - 3 + ((firstThursday.getUTCDay() + 6) % 7)) / 7,
  );
  return `${d.getUTCFullYear()}-W${String(week).padStart(2, "0")}`;
}

async function recordCohort(identity: string): Promise<void> {
  const firstKey = `gen:first:${identity}`;
  const seen = await kvGet(firstKey);
  const today = dayKey();
  if (!seen) {
    // Brand new generator: stamp them and open their cohort.
    await Promise.all([
      kvSet(firstKey, today, COHORT_TTL),
      kvSetAdd(`cohort:${weekKey()}:new`, identity, COHORT_TTL),
    ]);
    return;
  }
  const firstDate = new Date(`${seen}T00:00:00Z`);
  if (Number.isNaN(firstDate.getTime())) return;
  const days = Math.floor((Date.now() - firstDate.getTime()) / 86400000);
  if (days < 1) return;             // same day as their first: not a return
  const cohort = weekKey(firstDate); // always the cohort they STARTED in
  const writes: Promise<unknown>[] = [];
  if (days <= 2) writes.push(kvSetAdd(`cohort:${cohort}:d1`, identity, COHORT_TTL));
  if (days <= 7) writes.push(kvSetAdd(`cohort:${cohort}:d7`, identity, COHORT_TTL));
  if (days <= 30) writes.push(kvSetAdd(`cohort:${cohort}:d30`, identity, COHORT_TTL));
  await Promise.all(writes);
}

export interface CohortRow {
  week: string;
  size: number;
  d1: number;
  d7: number;
  d30: number;
}

/** The last N weekly cohorts, newest first. */
export async function cohortSummary(weeks = 6): Promise<CohortRow[]> {
  const out: CohortRow[] = [];
  for (let back = 0; back < weeks; back += 1) {
    const when = new Date();
    when.setUTCDate(when.getUTCDate() - back * 7);
    const week = weekKey(when);
    const [size, d1, d7, d30] = await Promise.all([
      kvSetCount(`cohort:${week}:new`),
      kvSetCount(`cohort:${week}:d1`),
      kvSetCount(`cohort:${week}:d7`),
      kvSetCount(`cohort:${week}:d30`),
    ]);
    out.push({ week, size, d1, d7, d30 });
  }
  return out;
}

export interface EngagementDay {
  day: string;
  unique: number;
  newUsers: number;
  returning: number;
  depth: number[]; // index 0 = reached depth 1, ... index 5 = reached 6+
}

/** Last-N-days engagement, newest first. */
export async function engagementSummary(days = 7): Promise<EngagementDay[]> {
  const out: EngagementDay[] = [];
  for (let offset = 0; offset < days; offset += 1) {
    const date = new Date();
    date.setUTCDate(date.getUTCDate() - offset);
    const day = dayKey(date);
    const [unique, counts] = await Promise.all([
      kvSetCount(`gen:users:${day}`),
      kvGetNumbers([
        `stat:gen_new:day:${day}`,
        `stat:gen_returning:day:${day}`,
        ...Array.from({ length: DEPTH_CAP }, (_, i) => `stat:gen_depth:${day}:${i + 1}`),
      ]),
    ]);
    out.push({
      day,
      unique,
      newUsers: counts[0] ?? 0,
      returning: counts[1] ?? 0,
      depth: counts.slice(2),
    });
  }
  return out;
}

/* ── who saves and who shares ────────────────────────────────────────────── */
//
// TRACKED_EVENTS counts ACTIONS: one person sharing the same build into four
// group chats registers four. That is the right number for "is the button
// used" and the wrong one for "how many people share", which is the question
// that decides whether sharing is a growth channel worth building on. Three
// albums against 760 generations was only alarming once it was clear it meant
// three PEOPLE.
//
// So savers and sharers also land in sets, daily and lifetime, under the same
// identity unit as the quota and the cohorts -- Google sub when signed in,
// hashed IP otherwise -- so these figures can sit beside those without
// quietly comparing two different things.

export type ActorAction = "saved" | "shared";

export const ACTOR_ACTIONS: readonly ActorAction[] = ["saved", "shared"];

const actorDayKey = (action: ActorAction, day = dayKey()) => `actor:${action}:day:${day}`;
const actorAllKey = (action: ActorAction) => `actor:${action}:all`;

/** Files one person under an action. Repeats by the same person collapse. */
export async function recordActor(action: ActorAction, identity: string): Promise<void> {
  try {
    await Promise.all([
      kvSetAdd(actorDayKey(action), identity, DAY_BUCKET_TTL),
      kvSetAdd(actorAllKey(action), identity),
    ]);
  } catch {
    /* a counter is never worth failing the interaction over */
  }
}

export interface ActorSummary {
  action: ActorAction;
  /** Distinct people who did it ever, and today. */
  allTime: number;
  today: number;
  /** Distinct people per day, newest first. Not summable: the same person
   *  appearing on three days is three entries but one human. */
  daily: { day: string; unique: number }[];
}

export async function actorSummary(action: ActorAction, days = 7): Promise<ActorSummary> {
  const daily: { day: string; unique: number }[] = [];
  for (let offset = 0; offset < days; offset += 1) {
    const date = new Date();
    date.setUTCDate(date.getUTCDate() - offset);
    const day = dayKey(date);
    daily.push({ day, unique: await kvSetCount(actorDayKey(action, day)) });
  }
  const allTime = await kvSetCount(actorAllKey(action));
  return { action, allTime, today: daily[0]?.unique ?? 0, daily };
}

/* ── likes ───────────────────────────────────────────────────────────────── */

const likeKey = (buildId: string) => `like:${buildId}`;

export async function likeCount(buildId: string): Promise<number> {
  return kvGetNumber(likeKey(buildId));
}

export async function likeCounts(buildIds: string[]): Promise<Record<string, number>> {
  const values = await kvGetNumbers(buildIds.map(likeKey));
  return Object.fromEntries(buildIds.map((id, index) => [id, values[index] ?? 0]));
}

export async function addLike(buildId: string, delta: 1 | -1): Promise<number> {
  const next = await kvIncr(likeKey(buildId), delta);
  return Math.max(0, next);
}

/* ── build feedback (thumbs up / down on generated builds) ───────────────── */

export interface BuildFeedback {
  verdict: "up" | "down";
  reasons: string[];
  note?: string;
  champion?: string;
  at: string;
}

export async function recordFeedback(feedback: BuildFeedback): Promise<void> {
  const writes: Promise<unknown>[] = [
    kvIncr(`feedback:build:${feedback.verdict}`),
    kvPushCapped("feedback:build:log", JSON.stringify(feedback), 500),
  ];
  for (const reason of feedback.reasons.slice(0, 4)) {
    writes.push(kvIncr(`feedback:build:reason:${reason}`));
  }
  try {
    await Promise.all(writes);
  } catch {
    /* ignore */
  }
}
