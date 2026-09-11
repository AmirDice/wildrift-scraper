import { after } from "next/server";
import { NextResponse } from "next/server";
import { buildCacheKey, readCachedBuild, writeCachedBuild } from "@/lib/build-cache";
import { cachedStudioBuild, rememberLatestBuild } from "@/lib/cached-build";
import { clientIp, consumeQuota, isOwnerKey, ownerKeyStatus, refundQuota } from "@/lib/quota";
import { ALPHA_DAILY_BUILDS, deviceAllowed, isAlphaDevice } from "@/lib/alpha";
import { kvGet, kvSet, kvDelete } from "@/lib/kv";
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
  "Access-Control-Allow-Headers": "content-type, x-device-id, x-owner-key",
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
    // Why this build beats these five. The draft page and the overlay show a
    // build with no room for prose around it, so the one thing worth carrying
    // is the reasoning that names which piece answers which enemy.
    counterSummary: advice.counterSummary ?? null,
  };
}

/** How long an items call may follow its runes call without paying again.
 *  Long enough for a draft, short enough that it cannot be hoarded. */
const PAIR_WINDOW_SECONDS = 15 * 60;

/** Remember that this exact build already paid, via its runes half. */
async function openPair(key: string): Promise<void> {
  try {
    await kvSet(key, "1", PAIR_WINDOW_SECONDS);
  } catch {
    // A missing KV must not break generation: the worst case is that the
    // items half is charged too, which is the behaviour before this existed.
  }
}

/** Spend the pairing, if there is one. Single-use: the follow-up is free
 *  once, not for every request that reuses the signature afterwards. */
async function claimPair(key: string): Promise<boolean> {
  try {
    const seen = await kvGet(key);
    if (!seen) return false;
    await kvDelete(key);
    return true;
  } catch {
    return false;
  }
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
  // Runes and summoners alone, when the caller wants the half of the build
  // that has a deadline before the half that does not. A rune page cannot be
  // changed after champion select; items can be bought for the next twenty
  // minutes.
  const only = clean(body.only) === "runes" ? "runes" : "";
  // CACHE-ONLY. Answer from a build somebody has already paid for, or say
  // there is none -- never generate, never spend a generation, never queue.
  //
  // The draft page and the overlay used to fill this gap with builds.json,
  // frozen on 2026-07-27 and five patches stale. A cache read gives them a
  // real current-patch build for free wherever one exists, and an honest
  // "nothing yet" where one does not.
  const cacheOnly = body.cacheOnly === true;
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
    ...(only ? { only } : {}),
  };

  // The device id is the quota identity. It rides through consumeQuota's ip
  // slot with a prefix, so a device can never collide with a real address,
  // and a missing header falls back to the caller's IP.
  const rawDevice = request.headers.get("x-device-id") || "";
  const device = rawDevice.replace(/[^A-Za-z0-9-]/g, "").slice(0, 64);
  const identity = device ? `device:${device}` : clientIp(request);

  // The alpha gate. Enforced HERE rather than in the app, because the app is a
  // file people pass on and every install that reaches this line spends real
  // generation credit. The owner's own key still walks through, so a phone
  // testing the build cannot be locked out by its own gate.
  const alphaTester = await isAlphaDevice(device);
  if (!isOwnerKey(request.headers.get("x-owner-key")) && !(await deviceAllowed(device))) {
    return json({ error: "This build is in closed testing. Enter your invite code in the app.",
                  needsActivation: true }, 403);
  }

  // Cache first: someone may have paid for this exact build already.
  //
  // buildCacheKey deliberately does not know about `only`, so a runes-only
  // answer must NOT be stored under the full build's key -- it would be
  // served to the next caller asking for a whole build, which would arrive
  // with no items at all. It gets its own suffixed slot instead, and existing
  // entries keep their keys.
  const fullKey = buildCacheKey(advisorRequest);
  const cacheKey = only ? `${fullKey}:${only}` : fullKey;
  // A cached FULL build already contains the rune page, so it answers a
  // runes-only request too, faster and for free. Prefer it.
  const cached = (only ? await readCachedBuild(fullKey) : null)
    ?? await readCachedBuild(cacheKey);
  // The owner's own phone is not rate-limited against them. Usage is still
  // COUNTED either way, so what the beta costs stays visible: the cap is
  // lifted, the meter is not switched off.
  const ownerHeader = request.headers.get("x-owner-key");
  const unlimited = isOwnerKey(ownerHeader);
  // Runes-first splits ONE build across two requests, and charging both would
  // silently halve everyone's allowance the day the overlay started using it.
  // The runes call pays; the items call that follows it is free, recognised
  // by the same request signature within a short window.
  const pairKey = `pair:${identity}:${fullKey}`;
  const paired = only === "runes" ? false : await claimPair(pairKey);
  // Say why a key was refused. A silent rejection is indistinguishable from a
  // stale deployment or an unset variable, and there is nothing secret in the
  // reason -- neither key appears in it.
  const ownerKey = ownerHeader ? ownerKeyStatus(ownerHeader) : undefined;
  if (cacheOnly) {
    // Ahead of consumeQuota on purpose: a lookup that cannot generate must not
    // be able to spend the day's allowance either. Trimmed the same way the
    // cached path below trims, so a caller cannot tell the two apart by shape.
    //
    // Falls through to the CHAMPION INDEX when this exact request has never
    // been asked. That is the common case and the whole point: the caller
    // wants "a build for Jinx", not "the build for Jinx at these eleven
    // settings", and the exact key only answers the second question. Without
    // this the draft page asked for a cached build, got a 200 with null, and
    // showed nothing for a champion whose build was sitting in the index.
    const any = cached ?? await cachedStudioBuild(champion, advisorRequest.role);
    return json({ v: 1, cached: Boolean(any), mode, champion,
                  build: any ? trim(any as Advice) : null });
  }
  const { ok, quota } = await consumeQuota(null, identity, unlimited || paired,
                                          alphaTester ? ALPHA_DAILY_BUILDS : undefined);
  if (!ok) {
    after(() => trackEvent("limit_reached_anon"));
    return json({
      error: `That is your ${quota.limit} free builds for today.`,
      quota: { used: quota.used, limit: Number.isFinite(quota.limit) ? quota.limit : null,
               unlimited: Boolean(quota.unlimited) },
      ownerKey,
    }, 429);
  }
  if (only === "runes") after(() => openPair(pairKey));
  after(() => trackEvent(mode === "counter" ? "counter_generated" : "build_generated"));
  after(() => recordGenerationEngagement(identity, quota.used));
  if (cached) {
    return json({
      v: 1, cached: true, mode, champion,
      build: trim(cached as Advice),
      quota: { used: quota.used, limit: Number.isFinite(quota.limit) ? quota.limit : null,
               unlimited: Boolean(quota.unlimited) },
      ownerKey,
    });
  }

  if (!ADVISOR_URL) {
    await refundQuota(null, identity, unlimited);
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
      await refundQuota(null, identity, unlimited);
      return json({ error: String(data.error || `generator error (${res.status})`) }, 502);
    }
    after(() => writeCachedBuild(cacheKey, data));
    // File it as this champion's newest plain answer, so the draft page and
    // the overlay bundle have something current to show without generating.
    // Only a full studio build with no enemies: a counter build is an answer
    // to one comp and a runes-only reply has no items in it at all.
    if (!only && mode === "studio" && enemies.length === 0) {
      after(() => rememberLatestBuild(champion, data));
    }
    return json({
      v: 1, cached: false, mode, champion,
      build: trim(data),
      quota: { used: quota.used, limit: Number.isFinite(quota.limit) ? quota.limit : null,
               unlimited: Boolean(quota.unlimited) },
      ownerKey,
    });
  } catch {
    await refundQuota(null, identity, unlimited);
    return json({ error: "the generator did not answer; try again" }, 502);
  }
}

export function OPTIONS() {
  return new Response(null, { status: 204, headers: CORS });
}
