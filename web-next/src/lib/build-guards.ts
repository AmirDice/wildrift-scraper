/**
 * Abuse guards for build generation, on top of the daily quota.
 *
 * The daily quota answers "how much may one person have today". It does not
 * answer "is this a person". Every generation is a real DeepSeek call that we
 * pay for and that occupies a function slot for up to a minute, so before
 * launch the endpoint needs to survive someone pointing a loop at it.
 *
 * Three separate problems, three guards:
 *
 *  1. BURST. The quota is a daily counter, so ten requests fired in one second
 *     all pass it. A short sliding window stops a script from consuming a whole
 *     allowance (and ten concurrent function invocations) instantly.
 *  2. CONCURRENCY. A generation runs for 30-60 seconds. Without a cap, one
 *     client can hold several in flight at once, multiplying cost and latency
 *     for everyone else.
 *  3. IDENTITY CHURN. Quota keys off IP or account. A rotating proxy defeats
 *     that, so the whole endpoint also has a global ceiling: past it, everyone
 *     is asked to come back later rather than us paying an unbounded bill.
 *
 * All three fail OPEN on a storage error. A KV blip should slow nobody down;
 * the daily quota is still behind this, and a spender who gets through during
 * an outage still hits that.
 */
import { kvGetJson, kvSetJson } from "@/lib/kv";

/** Requests one client may start in the burst window. */
export const BURST_LIMIT = 3;
export const BURST_WINDOW_SECONDS = 60;

/** Generations one client may have running at once. */
export const CONCURRENCY_LIMIT = 2;
/** Slightly longer than the advisor's own timeout, so a crashed run expires. */
const INFLIGHT_TTL_SECONDS = 300;

/** Site-wide ceiling per hour, the backstop against rotating identities. */
export const GLOBAL_HOURLY_LIMIT = 400;

export type GuardVerdict = { ok: true } | { ok: false; reason: string; retryAfter: number };

const OK: GuardVerdict = { ok: true };

function hourBucket(): string {
  return new Date().toISOString().slice(0, 13); // YYYY-MM-DDTHH
}

/**
 * Sliding-ish window: a bucketed counter per client. Cheap, and precise enough
 * for the job -- the worst case is a client getting up to double the limit
 * across a bucket boundary, which is not the attack we care about.
 */
export async function checkBurst(clientKey: string): Promise<GuardVerdict> {
  const bucket = Math.floor(Date.now() / (BURST_WINDOW_SECONDS * 1000));
  const key = `guard:burst:${clientKey}:${bucket}`;
  try {
    const used = (await kvGetJson<number>(key, 0)) ?? 0;
    if (used >= BURST_LIMIT) {
      return {
        ok: false,
        retryAfter: BURST_WINDOW_SECONDS,
        reason: `That is ${BURST_LIMIT} builds in under a minute. Give it a moment and try again.`,
      };
    }
    await kvSetJson(key, used + 1, BURST_WINDOW_SECONDS * 2);
  } catch {
    return OK; // fail open: never block a real player over a storage blip
  }
  return OK;
}

/** Claim an in-flight slot. Returns a release function to call when finished. */
export async function claimInflight(
  clientKey: string,
): Promise<{ verdict: GuardVerdict; release: () => Promise<void> }> {
  const key = `guard:inflight:${clientKey}`;
  const noop = async () => {};
  try {
    const running = (await kvGetJson<number>(key, 0)) ?? 0;
    if (running >= CONCURRENCY_LIMIT) {
      return {
        verdict: {
          ok: false,
          retryAfter: 30,
          reason: "You already have builds generating. Wait for those to finish first.",
        },
        release: noop,
      };
    }
    await kvSetJson(key, running + 1, INFLIGHT_TTL_SECONDS);
    return {
      verdict: OK,
      release: async () => {
        try {
          const current = (await kvGetJson<number>(key, 0)) ?? 0;
          await kvSetJson(key, Math.max(0, current - 1), INFLIGHT_TTL_SECONDS);
        } catch {
          /* the TTL cleans this up regardless */
        }
      },
    };
  } catch {
    return { verdict: OK, release: noop };
  }
}

/**
 * The backstop. Quota and burst both key off an identity; this one does not,
 * so it is what stands between us and an unbounded bill when the identity is
 * the thing being rotated.
 */
export async function checkGlobalCeiling(): Promise<GuardVerdict> {
  const key = `guard:global:${hourBucket()}`;
  try {
    const used = (await kvGetJson<number>(key, 0)) ?? 0;
    if (used >= GLOBAL_HOURLY_LIMIT) {
      return {
        ok: false,
        retryAfter: 900,
        reason: "Build generation is unusually busy right now. Please try again shortly.",
      };
    }
    await kvSetJson(key, used + 1, 3600 * 2);
  } catch {
    return OK;
  }
  return OK;
}

/**
 * Everything except the daily quota, in the order that fails cheapest first.
 * The caller runs this BEFORE spending a generation and before calling the
 * advisor.
 */
export async function checkAbuseGuards(clientKey: string): Promise<{
  verdict: GuardVerdict;
  release: () => Promise<void>;
}> {
  const noop = async () => {};

  const burst = await checkBurst(clientKey);
  if (!burst.ok) return { verdict: burst, release: noop };

  const global = await checkGlobalCeiling();
  if (!global.ok) return { verdict: global, release: noop };

  return await claimInflight(clientKey);
}
