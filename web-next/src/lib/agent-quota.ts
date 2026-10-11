import crypto from "node:crypto";
import { dayKey, kvGetNumber, kvIncr } from "@/lib/kv";
import type { SessionUser } from "@/lib/session";
import {
  ANON_DAILY_AGENT_QUESTIONS,
  SIGNED_IN_DAILY_AGENT_QUESTIONS,
} from "@/lib/agent-quota-limits";

export { ANON_DAILY_AGENT_QUESTIONS, SIGNED_IN_DAILY_AGENT_QUESTIONS };

const DAY_SECONDS = 60 * 60 * 24;

export interface AgentQuotaState {
  used: number;
  limit: number;
  remaining: number;
  signedIn: boolean;
  canUnlockBySigningIn: boolean;
  resetAt: number;
  unlimited?: boolean;
}

function nextUtcMidnight(): number {
  const now = new Date();
  return Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1);
}

function ipKey(ip: string): string {
  return crypto.createHash("sha256").update(ip).digest("hex").slice(0, 20);
}

function keyFor(user: SessionUser | null, ip: string): string {
  return user
    ? `quota:agent:u:${user.sub}:${dayKey()}`
    : `quota:agent:ip:${ipKey(ip)}:${dayKey()}`;
}

function state(used: number, user: SessionUser | null): AgentQuotaState {
  const limit = user ? SIGNED_IN_DAILY_AGENT_QUESTIONS : ANON_DAILY_AGENT_QUESTIONS;
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

function unlimitedState(used: number, signedIn: boolean): AgentQuotaState {
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

export async function peekAgentQuota(
  user: SessionUser | null,
  ip: string,
  unlimited = false,
): Promise<AgentQuotaState> {
  const used = await kvGetNumber(keyFor(user, ip));
  return unlimited ? unlimitedState(used, Boolean(user)) : state(used, user);
}

export async function consumeAgentQuota(
  user: SessionUser | null,
  ip: string,
  unlimited = false,
): Promise<{ ok: boolean; quota: AgentQuotaState }> {
  const key = keyFor(user, ip);
  const used = await kvGetNumber(key);
  if (unlimited) {
    return { ok: true, quota: unlimitedState(await kvIncr(key, 1, DAY_SECONDS), Boolean(user)) };
  }
  const limit = user ? SIGNED_IN_DAILY_AGENT_QUESTIONS : ANON_DAILY_AGENT_QUESTIONS;
  if (used >= limit) return { ok: false, quota: state(used, user) };
  return { ok: true, quota: state(await kvIncr(key, 1, DAY_SECONDS), user) };
}

export async function refundAgentQuota(
  user: SessionUser | null,
  ip: string,
  unlimited = false,
): Promise<AgentQuotaState> {
  const key = keyFor(user, ip);
  let next = await kvIncr(key, -1, DAY_SECONDS);
  if (next < 0) {
    await kvIncr(key, -next, DAY_SECONDS);
    next = 0;
  }
  return unlimited ? unlimitedState(next, Boolean(user)) : state(next, user);
}

