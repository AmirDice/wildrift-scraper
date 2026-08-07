/**
 * Tiny persistent key-value store.
 *
 * Everything that has to survive a request -- daily build quotas, the lifetime
 * "builds generated" counter, likes, and feature-usage events -- goes through
 * here. There is no database in this project, so the store talks to an Upstash
 * / Vercel KV Redis through the official SDK and
 * falls back to an in-process Map when no credentials are configured.
 *
 * Configure in the Vercel project (or .env.local) with EITHER pair:
 *   KV_REST_API_URL        / KV_REST_API_TOKEN          (Vercel KV)
 *   UPSTASH_REDIS_REST_URL / UPSTASH_REDIS_REST_TOKEN   (Upstash direct)
 *
 * Without them the app still works: counters live in memory, reset on redeploy,
 * and are not shared between serverless instances. That is fine for local dev
 * and acceptable for a soft launch; it is NOT accurate for production numbers.
 */

import { Redis } from "@upstash/redis";

const HAS_REDIS_ENV = Boolean(
  (process.env.UPSTASH_REDIS_REST_URL || process.env.KV_REST_API_URL)
  && (process.env.UPSTASH_REDIS_REST_TOKEN || process.env.KV_REST_API_TOKEN),
);
// Keep automatic deserialization off because this module intentionally exposes
// a string KV contract and performs JSON decoding only in kvGetJson.
const redis = HAS_REDIS_ENV ? Redis.fromEnv({ automaticDeserialization: false }) : null;

export const KV_CONFIGURED = Boolean(redis);

/* ── in-memory fallback ──────────────────────────────────────────────────── */

type MemoryEntry = { value: string; expiresAt: number | null };

// Pinned to globalThis, not module scope. In `next dev` each route handler can
// load its own copy of this module and the copies get hot-reloaded between
// requests, so a plain `const memory = new Map()` is a DIFFERENT map per route
// and per reload. That made an album created by POST /api/albums vanish before
// POST /api/albums/[id]/builds could read it, and the missing album surfaced to
// the user as "not your album". One store per process fixes it. Production sets
// KV and never touches this path, so the global is a dev-only convenience.
const _g = globalThis as typeof globalThis & {
  __wtmMemory?: Map<string, MemoryEntry>;
  __wtmMemoryLists?: Map<string, string[]>;
};
const memory = (_g.__wtmMemory ??= new Map<string, MemoryEntry>());
const memoryLists = (_g.__wtmMemoryLists ??= new Map<string, string[]>());

function memoryRead(key: string): string | null {
  const entry = memory.get(key);
  if (!entry) return null;
  if (entry.expiresAt != null && entry.expiresAt < Date.now()) {
    memory.delete(key);
    return null;
  }
  return entry.value;
}

/* ── public API ──────────────────────────────────────────────────────────── */

export async function kvGet(key: string): Promise<string | null> {
  if (!redis) return memoryRead(key);
  try {
    const value = await redis.get<string>(key);
    return value == null ? null : String(value);
  } catch {
    return memoryRead(key);
  }
}

export async function kvGetNumber(key: string, fallback = 0): Promise<number> {
  const raw = await kvGet(key);
  const parsed = raw == null ? Number.NaN : Number(raw);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export async function kvSet(key: string, value: string, ttlSeconds?: number): Promise<void> {
  if (!redis) {
    memory.set(key, { value, expiresAt: ttlSeconds ? Date.now() + ttlSeconds * 1000 : null });
    return;
  }
  try {
    await redis.set(key, value, ttlSeconds ? { ex: ttlSeconds } : undefined);
  } catch {
    memory.set(key, { value, expiresAt: ttlSeconds ? Date.now() + ttlSeconds * 1000 : null });
  }
}

/**
 * Increments a counter and returns the new value. When `ttlSeconds` is given
 * the expiry is (re)applied only on creation, so a daily window really is a
 * day and not a sliding window that never expires under steady traffic.
 */
export async function kvIncr(key: string, by = 1, ttlSeconds?: number): Promise<number> {
  if (!redis) {
    const current = Number(memoryRead(key) ?? 0);
    const next = current + by;
    const existing = memory.get(key);
    memory.set(key, {
      value: String(next),
      expiresAt: existing?.expiresAt ?? (ttlSeconds ? Date.now() + ttlSeconds * 1000 : null),
    });
    return next;
  }
  try {
    const pipeline = redis.pipeline().incrby(key, by);
    const [value] = ttlSeconds
      ? await pipeline.expire(key, ttlSeconds, "NX").exec()
      : await pipeline.exec();
    return Number(value) || 0;
  } catch {
    const current = Number(memoryRead(key) ?? 0);
    const next = current + by;
    memory.set(key, { value: String(next), expiresAt: ttlSeconds ? Date.now() + ttlSeconds * 1000 : null });
    return next;
  }
}

/** Reads many counters at once; missing keys come back as 0. */
export async function kvGetNumbers(keys: string[]): Promise<number[]> {
  if (keys.length === 0) return [];
  if (!redis) return keys.map((key) => Number(memoryRead(key) ?? 0));
  try {
    const pipeline = redis.pipeline();
    for (const key of keys) pipeline.get(key);
    const values = await pipeline.exec();
    return values.map((value) => Number(value) || 0);
  } catch {
    return keys.map((key) => Number(memoryRead(key) ?? 0));
  }
}

/** Appends to a capped list (newest first). Used for free-text build feedback. */
export async function kvPushCapped(key: string, value: string, cap = 500): Promise<void> {
  if (!redis) {
    const list = memoryLists.get(key) ?? [];
    list.unshift(value);
    memoryLists.set(key, list.slice(0, cap));
    return;
  }
  try {
    await redis.pipeline().lpush(key, value).ltrim(key, 0, cap - 1).exec();
  } catch {
    const list = memoryLists.get(key) ?? [];
    list.unshift(value);
    memoryLists.set(key, list.slice(0, cap));
  }
}

/** Appends to the RIGHT of a list -- with {@link kvList} this makes a FIFO
 *  queue (oldest entry first), which is what the ops job queue needs. */
export async function kvRightPush(key: string, value: string): Promise<void> {
  if (!redis) {
    const list = memoryLists.get(key) ?? [];
    list.push(value);
    memoryLists.set(key, list);
    return;
  }
  try {
    await redis.rpush(key, value);
  } catch {
    const list = memoryLists.get(key) ?? [];
    list.push(value);
    memoryLists.set(key, list);
  }
}

/** Reads back a capped list written by {@link kvPushCapped}. */
export async function kvList(key: string, limit = 100): Promise<string[]> {
  if (!redis) return (memoryLists.get(key) ?? []).slice(0, limit);
  try {
    const values = await redis.lrange<string>(key, 0, limit - 1);
    return values.map(String);
  } catch {
    return (memoryLists.get(key) ?? []).slice(0, limit);
  }
}

export async function kvDelete(key: string): Promise<void> {
  if (!redis) {
    memory.delete(key);
    memoryLists.delete(key);
    return;
  }
  try {
    await redis.del(key);
  } catch {
    memory.delete(key);
  }
}

/** Reads a JSON document, returning `fallback` when absent or corrupt. */
export async function kvGetJson<T>(key: string, fallback: T): Promise<T> {
  const raw = await kvGet(key);
  if (raw == null) return fallback;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export async function kvSetJson(key: string, value: unknown, ttlSeconds?: number): Promise<void> {
  await kvSet(key, JSON.stringify(value), ttlSeconds);
}

/** UTC day stamp (YYYY-MM-DD), the bucket key for every daily counter. */
export function dayKey(date = new Date()): string {
  return date.toISOString().slice(0, 10);
}
