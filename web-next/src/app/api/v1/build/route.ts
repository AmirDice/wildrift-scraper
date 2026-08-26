import { after } from "next/server";
import { NextResponse } from "next/server";
import { buildCacheKey, readCachedBuild, writeCachedBuild } from "@/lib/build-cache";
import { clientIp, consumeQuota, refundQuota } from "@/lib/quota";
import { recordGenerationEngagement, trackEvent } from "@/lib/stats";

/**
 * The ported generator: one versioned endpoint for clients that are not this
 * site -- the /draft page and the Android overlay first. Same brain as
 * /api/build (same advisor, same cache keys, so the two routes share every
 * cached build), different contract:
 *
 *   - identity is an anonymous device id (x-device-id header), not a session
 *     cookie; the daily allowance rides on it
 *   - the response is TRIMMED to what a phone next to a running game needs:
 *     slugs, names, short reasons -- no scores tables, no play guide
 *   - CORS is open: the callers are not on this origin
 *
 * The advisor is reached over HTTP only (ADVISOR_URL); this route never
 * shells out, because its callers are production surfaces. Normalization
 * mirrors /api/build's rules -- kept in sync by the shared cache keys, which
 * would fragment if the shapes drifted.
 */

const ADVISOR_URL = process.env.ADVISOR_URL || "";
const ADVISOR_SECRET = process.env.ADVISOR_SECRET || "";

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "content-type, x-device-id",
};

const BIAS_VALUES = new Set([
  "max_damage", "damage", "balanced", "durability", "max_durability",
]);

function json(data: unknown, status = 200) {
  return NextResponse.json(data, { status, headers: CORS });
}

type Advice = Record<string, unknown>;

/** The overlay's view of a build: enough to play from, small enough to read
 *  during a loading screen. */
function trim(advice: Advice) {
  const itemReasons = new Map<string, string>();
  for (const row of (advice.itemScores as Record<string, unknown>[] | undefined) ?? []) {
    if (row && typeof row.item === "string" && typeof row.reason === "string") {
      itemReasons.set(row.item, row.reason.slice(0, 140));
    }
  }
  const items = ((advice.items as string[] | undefined) ?? []).map((slug) => ({
    slug,
    why: itemReasons.get(slug),
  }));
  return {
    items,
    boots: advice.boots ?? null,
    bootsUpgrade: advice.bootsUpgrade ?? null,
    bootsUpgradeAfter: advice.bootsUpgradeAfter ?? null,
    bootsReason: typeof advice.bootsReason === "string" ? advice.bootsReason.slice(0, 200) : null,
    runes: advice.runes ?? null,
    runeReasons: advice.runeReasons ?? null,
    summoners: advice.summoners ?? null,
    situational: advice.situational ?? null,
    situationalBoots: advice.situationalBoots ?? null,
    buildScore: advice.buildScore ?? null,
  };
}

export async function POST(request: Request) {
  let body: Record<string, unknown>;
  try {
    body = await request.json();
  } catch {
    return json({ error: "invalid JSON body" }, 400);
  }
  const clean = (s: unknown) =>
    typeof s === "string" ? s.replace(/[^A-Za-z0-9 .'&-]/g, "").slice(0, 40) : "";
  const cleanList = (a: unknown) =>
    Array.isArray(a) ? a.map(clean).filter(Boolean).slice(0, 5) : [];
  const champion = clean(body.champion);
  if (!champion) return json({ error: "champion is required" }, 400);

  const mode = clean(body.mode) === "counter" ? "counter" : "studio";
  const unique = (values: string[]) => [...new Set(values)];
  const enemies = unique(cleanList(body.enemies)).filter((n) => n !== champion);
  const allies = unique(cleanList(body.allies))
    .filter((n) => n !== champion && !enemies.includes(n)).slice(0, 4);
  if (mode === "counter" && enemies.length === 0) {
    return json({ error: "at least one enemy is required for a counter build" }, 400);
  }
  const advisorRequest = {
    champion,
    role: clean(body.role),
    enemies,
    allies,
    playstyle: clean(body.playstyle) || "standard",
    objective: clean(body.objective) || "balanced",
    gamePhase: clean(body.gamePhase) || "balanced",
    damagePath: clean(body.damagePath) || "standard",
    championForm: clean(body.championForm),
    aheadEnemy: clean(body.aheadEnemy),
    mode,
    riskTolerance: clean(body.riskTolerance) || "medium",
    skillLevel: clean(body.skillLevel) || "average",
    buildBias: typeof body.buildBias === "string" && BIAS_VALUES.has(body.buildBias)
      ? body.buildBias : "balanced",
    lockedItems: cleanList(body.lockedItems),
    lockedRunes: cleanList(body.lockedRunes),
  };

  // The device id is the quota identity. It rides through consumeQuota's ip
  // slot with a prefix, so a device can never collide with a real address,
  // and a missing header falls back to the caller's IP.
  const rawDevice = request.headers.get("x-device-id") || "";
  const device = rawDevice.replace(/[^A-Za-z0-9-]/g, "").slice(0, 64);
  const identity = device ? `device:${device}` : clientIp(request);

  // Cache first: someone may have paid for this exact build already.
  const cacheKey = buildCacheKey(advisorRequest);
  const cached = await readCachedBuild(cacheKey);
  const { ok, quota } = await consumeQuota(null, identity, false);
  if (!ok) {
    after(() => trackEvent("limit_reached_anon"));
    return json({
      error: `That is your ${quota.limit} free builds for today.`,
      quota: { used: quota.used, limit: quota.limit },
    }, 429);
  }
  after(() => trackEvent(mode === "counter" ? "counter_generated" : "build_generated"));
  after(() => recordGenerationEngagement(identity, quota.used));
  if (cached) {
    return json({
      v: 1, cached: true, mode, champion,
      build: trim(cached as Advice),
      quota: { used: quota.used, limit: quota.limit },
    });
  }

  if (!ADVISOR_URL) {
    await refundQuota(null, identity);
    return json({ error: "the generator is not available right now; try again shortly" }, 503);
  }
  try {
    const res = await fetch(ADVISOR_URL, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        ...(ADVISOR_SECRET ? { "x-advisor-secret": ADVISOR_SECRET } : {}),
      },
      body: JSON.stringify(advisorRequest),
    });
    const data = (await res.json()) as Advice;
    if (!res.ok || data.error) {
      await refundQuota(null, identity);
      return json({ error: String(data.error || `generator error (${res.status})`) }, 502);
    }
    after(() => writeCachedBuild(cacheKey, data));
    return json({
      v: 1, cached: false, mode, champion,
      build: trim(data),
      quota: { used: quota.used, limit: quota.limit },
    });
  } catch {
    await refundQuota(null, identity);
    return json({ error: "the generator did not answer; try again" }, 502);
  }
}

export function OPTIONS() {
  return new Response(null, { status: 204, headers: CORS });
}
