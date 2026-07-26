/**
 * Daily build-generation quota.
 *
 * Everyone gets 10 generations a day. Signing in with Google grants a second
 * allowance of 10 counted against the Google account instead of the IP, so a
 * visitor who burns through the anonymous ten can sign in and keep going --
 * 20 in a day, total.
 *
 * Counters live in the shared KV store (src/lib/kv.ts) keyed by UTC day, so
 * they survive redeploys and are shared across serverless instances whenever
 * KV is configured.
 */
import crypto from "node:crypto";
import { dayKey, kvGetNumber, kvIncr } from "@/lib/kv";
import type { SessionUser } from "@/lib/session";

/** Anonymous allowance, per IP per UTC day. */
export const ANON_DAILY_BUILDS = 10;
/** Extra allowance unlocked by signing in, per Google account per UTC day. */
export const SIGNED_IN_DAILY_BUILDS = 10;

const DAY_SECONDS = 60 * 60 * 24;

export interface QuotaState {
  used: number;
  limit: number;
  remaining: number;
  signedIn: boolean;
  /** True when the anonymous allowance is spent and signing in would add more. */
  canUnlockBySigningIn: boolean;
  /** Epoch ms when the window rolls over (next UTC midnight). */
  resetAt: number;
  /** Set for holders of an unlimited access code; the cap does not apply. */
  unlimited?: boolean;
}

/** The state returned to someone whose access code lifts the cap entirely. */
function unlimitedState(used: number, signedIn: boolean): QuotaState {
  return {
    used,
    limit: Number.POSITIVE_INFINITY,
    remaining: Number.POSITIVE_INFINITY,
    signedIn,
    canUnlockBySigningIn: false,
    resetAt: nextUtcMidnight(),
    unlimited: true,
  };
}

/** IPs are hashed before they become keys: we count visits, not people. */
function ipKey(ip: string): string {
  return crypto.createHash("sha256").update(ip).digest("hex").slice(0, 20);
}

export function clientIp(request: Request): string {
  const forwarded = request.headers.get("x-forwarded-for");
  if (forwarded) return forwarded.split(",")[0].trim();
  return request.headers.get("x-real-ip") || "unknown";
}

function keyFor(user: SessionUser | null, ip: string): string {
  const day = dayKey();
  return user ? `quota:build:u:${user.sub}:${day}` : `quota:build:ip:${ipKey(ip)}:${day}`;
}

function nextUtcMidnight(): number {
  const now = new Date();
  return Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1);
}

function state(used: number, user: SessionUser | null): QuotaState {
  const limit = user ? SIGNED_IN_DAILY_BUILDS : ANON_DAILY_BUILDS;
  const remaining = Math.max(0, limit - used);
  return {
    used,
    limit,
    remaining,
    signedIn: Boolean(user),
    canUnlockBySigningIn: !user && remaining === 0,
    resetAt: nextUtcMidnight(),
  };
}

/** Reads the current window without spending anything. */
export async function peekQuota(
  user: SessionUser | null,
  ip: string,
  unlimited = false,
): Promise<QuotaState> {
  const used = await kvGetNumber(keyFor(user, ip));
  return unlimited ? unlimitedState(used, Boolean(user)) : state(used, user);
}

/**
 * Spends one generation. Returns `ok: false` (and does not increment) when the
 * window is already exhausted.
 *
 * Unlimited holders still have their usage counted -- knowing how much a beta
 * tester or a sponsored creator actually generates is the point of giving them
 * the code -- they just are not stopped by it.
 */
export async function consumeQuota(
  user: SessionUser | null,
  ip: string,
  unlimited = false,
): Promise<{ ok: boolean; quota: QuotaState }> {
  const key = keyFor(user, ip);
  const used = await kvGetNumber(key);
  if (unlimited) {
    const next = await kvIncr(key, 1, DAY_SECONDS);
    return { ok: true, quota: unlimitedState(next, Boolean(user)) };
  }
  const limit = user ? SIGNED_IN_DAILY_BUILDS : ANON_DAILY_BUILDS;
  if (used >= limit) return { ok: false, quota: state(used, user) };
  const next = await kvIncr(key, 1, DAY_SECONDS);
  return { ok: true, quota: state(next, user) };
}

/**
 * Restores one generation after a confirmed pre-generation infrastructure
 * failure (for example, the local Python process could not be launched).
 *
 * This must not be used for advisor, model, validation, or timeout failures:
 * those requests may already have incurred the generation cost. The caller is
 * responsible for making that distinction.
 */
export async function refundQuota(
  user: SessionUser | null,
  ip: string,
  unlimited = false,
): Promise<QuotaState> {
  const key = keyFor(user, ip);
  let next = await kvIncr(key, -1, DAY_SECONDS);

  // A day rollover or duplicate recovery must never leave a negative counter.
  // Restore only the amount below zero so concurrent legitimate usage remains.
  if (next < 0) {
    await kvIncr(key, -next, DAY_SECONDS);
    next = 0;
  }

  return unlimited ? unlimitedState(next, Boolean(user)) : state(next, user);
}
