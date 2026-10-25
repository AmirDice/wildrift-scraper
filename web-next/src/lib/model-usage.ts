import { dayKey, kvGetNumbers, kvIncr } from "@/lib/kv";

/**
 * What each feature costs in model tokens, recorded per request.
 *
 * The advisor returns a `usage` tally beside every answer (start_usage in
 * web/build_advisor.py): calls made, input, output and thinking tokens, split
 * by thinking level, which in practice is the stage -- the judge runs at high,
 * authoring and repairs at medium, the site agent at low. Until 2026-10-25
 * the only cost figure was the monthly bill, about EUR 400 over 90 days, with
 * no way to tell how much of it the site's visitors caused.
 *
 * Only requests that reach the site's routes are counted, so this is visitor
 * cost by construction: local scripts and test runs call the advisor directly
 * and never pass through here. Tokens are stored, not money; prices change and
 * belong in the read-out, not in a counter that would silently go wrong.
 */

export const USAGE_FEATURES = ["build", "counter", "why_not", "agent", "overlay"] as const;
export type UsageFeature = (typeof USAGE_FEATURES)[number];

const FIELDS = ["calls", "input", "output", "thoughts"] as const;
type Field = (typeof FIELDS)[number];
const LEVELS = ["low", "medium", "high"] as const;

export interface ModelUsage {
  calls: number;
  input: number;
  output: number;
  thoughts: number;
  levels?: Record<string, Partial<Record<Field, number>>>;
}

const DAY_TTL = 60 * 60 * 24 * 100;

/**
 * Removes the advisor's `usage` field from a payload and returns it. The tally
 * is internal: it must not be cached with a build or sent to the browser.
 */
export function takeUsage(data: unknown): ModelUsage | null {
  if (!data || typeof data !== "object" || Array.isArray(data)) return null;
  const record = data as Record<string, unknown>;
  const raw = record.usage;
  delete record.usage;
  if (!raw || typeof raw !== "object") return null;
  const u = raw as Record<string, unknown>;
  const num = (v: unknown) => (typeof v === "number" && Number.isFinite(v) && v >= 0 ? Math.round(v) : 0);
  const usage: ModelUsage = { calls: num(u.calls), input: num(u.input), output: num(u.output), thoughts: num(u.thoughts) };
  if (u.levels && typeof u.levels === "object") {
    usage.levels = {};
    for (const [level, value] of Object.entries(u.levels as Record<string, unknown>)) {
      if (!(LEVELS as readonly string[]).includes(level) || !value || typeof value !== "object") continue;
      const v = value as Record<string, unknown>;
      usage.levels[level] = { calls: num(v.calls), input: num(v.input), output: num(v.output), thoughts: num(v.thoughts) };
    }
  }
  return usage.calls ? usage : null;
}

const key = (feature: UsageFeature, field: string, day?: string) =>
  day ? `stat:tokens:${feature}:${field}:day:${day}` : `stat:tokens:${feature}:${field}:total`;

/** Adds one request's tally to the day and lifetime counters. */
export async function recordModelUsage(feature: UsageFeature, usage: ModelUsage | null): Promise<void> {
  if (!usage) return;
  const day = dayKey();
  const writes: Promise<unknown>[] = [
    kvIncr(key(feature, "requests", day), 1, DAY_TTL),
    kvIncr(key(feature, "requests"), 1),
  ];
  for (const field of FIELDS) {
    if (!usage[field]) continue;
    writes.push(kvIncr(key(feature, field, day), usage[field], DAY_TTL), kvIncr(key(feature, field), usage[field]));
  }
  for (const [level, values] of Object.entries(usage.levels ?? {})) {
    for (const field of FIELDS) {
      const n = values[field] ?? 0;
      if (n) writes.push(kvIncr(key(feature, `${level}:${field}`, day), n, DAY_TTL));
    }
  }
  await Promise.all(writes).catch(() => undefined);
}

export interface UsageSummary {
  feature: UsageFeature;
  days: number;
  requests: number;
  calls: number;
  input: number;
  output: number;
  thoughts: number;
  /** Per request, the numbers a price is set from. */
  perRequest: { calls: number; input: number; output: number; thoughts: number } | null;
  levels: Record<string, Record<Field, number>>;
}

/** The last `days` days for every feature, for the admin read-out. */
export async function usageSummary(days = 30): Promise<UsageSummary[]> {
  const dates: string[] = [];
  for (let i = 0; i < days; i += 1) {
    const d = new Date();
    d.setUTCDate(d.getUTCDate() - i);
    dates.push(dayKey(d));
  }
  const fields = ["requests", ...FIELDS, ...LEVELS.flatMap((l) => FIELDS.map((f) => `${l}:${f}`))];
  return Promise.all(USAGE_FEATURES.map(async (feature) => {
    const keys = fields.flatMap((field) => dates.map((day) => key(feature, field, day)));
    const values = await kvGetNumbers(keys);
    const sum = (i: number) => values.slice(i * days, (i + 1) * days).reduce((a, b) => a + b, 0);
    const total = Object.fromEntries(fields.map((f, i) => [f, sum(i)])) as Record<string, number>;
    const requests = total.requests;
    const levels: UsageSummary["levels"] = {};
    for (const level of LEVELS) {
      const row = Object.fromEntries(FIELDS.map((f) => [f, total[`${level}:${f}`]])) as Record<Field, number>;
      if (row.calls) levels[level] = row;
    }
    return {
      feature, days, requests,
      calls: total.calls, input: total.input, output: total.output, thoughts: total.thoughts,
      perRequest: requests ? {
        calls: +(total.calls / requests).toFixed(2),
        input: Math.round(total.input / requests),
        output: Math.round(total.output / requests),
        thoughts: Math.round(total.thoughts / requests),
      } : null,
      levels,
    };
  }));
}
