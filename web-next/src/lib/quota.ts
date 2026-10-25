/**
 * Daily build-generation quota.
 *
 * Anonymous visitors get 1 generation a day. Signing in with Google grants a
 * separate allowance of 3 counted against the Google account instead of the
 * IP, so a visitor can try one build and then sign in for three more.
 *
 * Counters live in the shared KV store (src/lib/kv.ts) keyed by UTC day, so
 * they survive redeploys and are shared across serverless instances whenever
 * KV is configured.
 */
import crypto from "node:crypto";
import { dayKey, kvGetNumber, kvIncr } from "@/lib/kv";
import type { SessionUser } from "@/lib/session";

// Defined in lib/quota-limits.ts, which has no node-only imports, so client
// components can read the same numbers instead of restating them in prose.
export { ANON_DAILY_BUILDS, SIGNED_IN_DAILY_BUILDS } from "@/lib/quota-limits";
import { ANON_DAILY_BUILDS, SIGNED_IN_DAILY_BUILDS } from "@/lib/quota-limits";
import { stripeConfigured } from "@/lib/stripe";
import { creditsConfigured, getCredits, refundCredit, spendCredit } from "@/lib/credits";

const DAY_SECONDS = 60 * 60 * 24;

export interface QuotaState {
  used: number;
  limit: number;
  remaining: number;
  signedIn: boolean;
  /** The paid tier that supplied this limit, when applicable. */
  plan?: "free" | "plus" | "pro";
  /** A signed-in free player on a deployment that can sell Plus: the limit
   *  wall offers it. False until Stripe is configured, so nothing advertises
   *  a subscription that cannot be bought. */
  plusAvailable?: boolean;
  /** Paid generation credits held by this signed-in player (lib/credits.ts).
   *  Spent only after the free daily allowance runs out. */
  credits?: number;
  /** Credit packs can be bought on this deployment, so the limit wall offers
   *  them to a signed-in player. False until Stripe and a pack price exist. */
  creditsAvailable?: boolean;
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

/** The stable identity the quota is counted against -- Google sub when signed
 *  in, hashed IP otherwise. Exported so engagement tracking attributes usage
 *  to exactly the same person-ish unit the allowance itself uses. */
export function quotaIdentity(user: SessionUser | null, ip: string): string {
  return user ? `u:${user.sub}` : `ip:${ipKey(ip)}`;
}

function nextUtcMidnight(): number {
  const now = new Date();
  return Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1);
}

function state(used: number, user: SessionUser | null, limitOverride?: number, credits = 0): QuotaState {
  const limit = limitOverride ?? (user ? SIGNED_IN_DAILY_BUILDS : ANON_DAILY_BUILDS);
  const remaining = Math.max(0, limit - used);
  return {
    credits: user ? credits : 0,
    // Offered to anyone who could use them, signed in or not: an anonymous
    // visitor sees "sign in, then buy", which is still the right wall.
    creditsAvailable: creditsConfigured(),
    used,
    limit,
    remaining,
    signedIn: Boolean(user),
    plan: limitOverride != null ? "plus" : "free",
    plusAvailable: Boolean(user) && limitOverride == null && stripeConfigured(),
    canUnlockBySigningIn: !user && remaining === 0,
    resetAt: nextUtcMidnight(),
  };
}

/** Reads the current window without spending anything. */
export async function peekQuota(
  user: SessionUser | null,
  ip: string,
  unlimited = false,
  limitOverride?: number,
): Promise<QuotaState> {
  const [used, credits] = await Promise.all([
    kvGetNumber(keyFor(user, ip)),
    user ? getCredits(user.sub) : Promise.resolve(0),
  ]);
  return unlimited ? unlimitedState(used, Boolean(user)) : state(used, user, limitOverride, credits);
}

/** What paid for a generation, so a refund returns the right thing. */
export type QuotaSource = "daily" | "credit" | "unlimited";

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
  // An explicit ceiling for callers who have earned a different one -- today
  // that is an alpha tester, whose device is on the invite register and who
  // would otherwise share the anonymous allowance with the public.
  limitOverride?: number,
): Promise<{ ok: boolean; quota: QuotaState; source?: QuotaSource }> {
  const key = keyFor(user, ip);
  const used = await kvGetNumber(key);
  if (unlimited) {
    const next = await kvIncr(key, 1, DAY_SECONDS);
    return { ok: true, quota: unlimitedState(next, Boolean(user)), source: "unlimited" };
  }
  const limit = limitOverride
    ?? (user ? SIGNED_IN_DAILY_BUILDS : ANON_DAILY_BUILDS);
  if (used >= limit) {
    // The free allowance is spent: a signed-in player with credits pays one.
    // The daily counter is left alone, so tomorrow's free generations are
    // still theirs and "used today" keeps meaning the free ones.
    if (user) {
      const spent = await spendCredit(user.sub);
      if (spent.ok) return { ok: true, quota: state(used, user, limitOverride, spent.balance), source: "credit" };
    }
    return { ok: false, quota: state(used, user, limitOverride, 0) };
  }
  const [next, credits] = await Promise.all([
    kvIncr(key, 1, DAY_SECONDS),
    user ? getCredits(user.sub) : Promise.resolve(0),
  ]);
  return { ok: true, quota: state(next, user, limitOverride, credits), source: "daily" };
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
  limitOverride?: number,
  // What paid for the generation being refunded. A credit goes back to the
  // balance; the daily counter is only touched for a daily generation.
  source: QuotaSource = "daily",
): Promise<QuotaState> {
  const key = keyFor(user, ip);
  if (source === "credit" && user) {
    const balance = await refundCredit(user.sub);
    return state(await kvGetNumber(key), user, limitOverride, balance);
  }
  let next = await kvIncr(key, -1, DAY_SECONDS);

  // A day rollover or duplicate recovery must never leave a negative counter.
  // Restore only the amount below zero so concurrent legitimate usage remains.
  if (next < 0) {
    await kvIncr(key, -next, DAY_SECONDS);
    next = 0;
  }

  const credits = user ? await getCredits(user.sub) : 0;
  return unlimited ? unlimitedState(next, Boolean(user)) : state(next, user, limitOverride, credits);
}

/**
 * The owner's key for the external clients, which have no session to be an
 * admin on.
 *
 * ADMIN_EMAILS cannot serve here: /api/v1 identifies a caller by an anonymous
 * device id in a header, and there is no signed-in account to check an email
 * against. The device id itself is the wrong thing to allowlist -- it is an
 * IDENTIFIER, sent in the clear on every request and already the quota key,
 * so treating it as a secret would mean anyone who saw one could spend the
 * generation budget.
 *
 * A separate key is a secret on purpose: never returned, never logged, and
 * held only in the server's environment and on the owner's own phone. Kept
 * out of the repository for the same reason ADMIN_EMAILS is: this one is
 * public.
 */
/** Shortest secret worth honouring. Low on purpose: see isOwnerKey. */
const OWNER_KEY_MIN = 8;

export function isOwnerKey(key: string | null | undefined): boolean {
  const secret = (process.env.OVERLAY_OWNER_KEY ?? "").trim();
  const given = (key ?? "").trim();
  // Both must be non-empty. This, not a length floor, is what stops an unset
  // variable from matching an absent header and uncapping everyone.
  //
  // The floor used to be sixteen characters, and that was a mistake: a real
  // key shorter than that was refused with no signal anywhere, which looks
  // exactly like a wrong key, a stale deployment or a missing variable. An
  // arbitrary minimum that silently rejects valid configuration costs more
  // than the weak keys it prevents. Eight is kept as a floor against a
  // one-character "secret", and the caller now reports a rejection.
  if (!secret || !given) return false;
  if (secret.length < OWNER_KEY_MIN) return false;
  if (given.length !== secret.length) return false;
  // Compare every character rather than stopping at the first mismatch, so a
  // wrong key cannot be narrowed down by how quickly it is rejected.
  let diff = 0;
  for (let i = 0; i < secret.length; i++) {
    diff |= secret.charCodeAt(i) ^ given.charCodeAt(i);
  }
  return diff === 0;
}

/** Why an owner key was refused, in terms safe to put in a response.
 *
 *  Names the reason without echoing either key: "no key on the server" and
 *  "the key you sent is wrong" are different problems with the same symptom,
 *  and guessing between them from the outside is what made this hard to set
 *  up in the first place. */
export function ownerKeyStatus(key: string | null | undefined):
  "accepted" | "no-server-key" | "server-key-too-short" | "mismatch" {
  const secret = (process.env.OVERLAY_OWNER_KEY ?? "").trim();
  if (!secret) return "no-server-key";
  if (secret.length < OWNER_KEY_MIN) return "server-key-too-short";
  return isOwnerKey(key) ? "accepted" : "mismatch";
}

