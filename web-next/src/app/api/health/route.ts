import { NextResponse } from "next/server";
import { KV_CONFIGURED, kvGet, kvSet } from "@/lib/kv";
import cn from "@/data/cn.json";

/**
 * GET /api/health -- what the uptime monitor polls.
 *
 * Two kinds of check, answered differently:
 *
 * - KV (Upstash). Quotas, credits, saved builds and sign-ins all live there,
 *   so if it is unreachable the build tools are broken even though every page
 *   still renders. That is an outage: HTTP 503, and the monitor alerts.
 *
 * - China data age. The daily GitHub Action commits fresh China rates and
 *   triggers a redeploy; if either half stops, nothing errors -- the site just
 *   quietly serves old numbers. That is "degraded": still HTTP 200 (the site is
 *   up), but the body says so, and a keyword monitor on "status":"ok" catches
 *   it. The EU/NA boards are deliberately not checked: they are collected by
 *   hand twice a month, so their age is a schedule, not a fault.
 *
 * No secrets, no per-visitor data, and nothing billable: one tiny KV write
 * and read with a short TTL.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** The China job runs daily; three missed runs in a row is a fault. */
const CN_MAX_AGE_DAYS = 3;
const KV_TIMEOUT_MS = 3000;

function cnAgeDays(): number | null {
  const raw = (cn as { date?: string }).date;
  if (!raw || !/^\d{8}$/.test(raw)) return null;
  const scraped = Date.UTC(Number(raw.slice(0, 4)), Number(raw.slice(4, 6)) - 1, Number(raw.slice(6, 8)));
  return Math.floor((Date.now() - scraped) / 86_400_000);
}

async function checkKv(): Promise<{ ok: boolean; ms: number; error?: string }> {
  const started = Date.now();
  if (!KV_CONFIGURED) return { ok: false, ms: 0, error: "not configured" };
  try {
    const token = String(started);
    const roundTrip = (async () => {
      await kvSet("health:ping", token, 60);
      return kvGet("health:ping");
    })();
    const timeout = new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error(`timed out after ${KV_TIMEOUT_MS}ms`)), KV_TIMEOUT_MS));
    const read = await Promise.race([roundTrip, timeout]);
    // Two monitors polling at once can overwrite each other's token, so only
    // "something came back" is required, not our exact value.
    return read ? { ok: true, ms: Date.now() - started } : { ok: false, ms: Date.now() - started, error: "read back nothing" };
  } catch (error) {
    return { ok: false, ms: Date.now() - started, error: error instanceof Error ? error.message : "unknown error" };
  }
}

export async function GET() {
  const kv = await checkKv();
  const age = cnAgeDays();
  const cnFresh = age != null && age <= CN_MAX_AGE_DAYS;
  const status = !kv.ok ? "down" : cnFresh ? "ok" : "degraded";

  return NextResponse.json(
    {
      status,
      checks: {
        kv,
        chinaData: { ok: cnFresh, scraped: (cn as { date?: string }).date ?? null, ageDays: age, maxAgeDays: CN_MAX_AGE_DAYS },
      },
      release: process.env.VERCEL_GIT_COMMIT_SHA?.slice(0, 7) ?? null,
      time: new Date().toISOString(),
    },
    { status: kv.ok ? 200 : 503, headers: { "Cache-Control": "no-store" } },
  );
}
