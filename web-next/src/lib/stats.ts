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
import { dayKey, kvGetNumber, kvGetNumbers, kvIncr, kvPushCapped } from "@/lib/kv";

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
