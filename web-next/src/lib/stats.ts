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
import { dayKey, kvGetNumber, kvGetNumbers, kvIncr, kvPushCapped, kvSetAdd, kvSetCount } from "@/lib/kv";

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

export async function recordGenerationEngagement(identity: string, depth: number): Promise<void> {
  try {
    const day = dayKey();
    const bucket = Math.min(Math.max(depth, 1), DEPTH_CAP);
    const writes: Promise<unknown>[] = [
      kvIncr(`stat:gen_depth:${day}:${bucket}`, 1, DAY_BUCKET_TTL),
      kvSetAdd(`gen:users:${day}`, identity, DAY_BUCKET_TTL),
    ];
    if (depth === 1) {
      // First generation of the day: settle new-vs-returning once per day.
      writes.push((async () => {
        const neverSeenBefore = await kvSetAdd("gen:users:all", identity);
        await kvIncr(`stat:${neverSeenBefore ? "gen_new" : "gen_returning"}:day:${day}`, 1, DAY_BUCKET_TTL);
      })());
    }
    await Promise.all(writes);
  } catch {
    /* engagement is never worth failing a generation over */
  }
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
