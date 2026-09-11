/**
 * Reading builds that have already been generated, without generating one.
 *
 * The draft page and the overlay bundle both used to serve
 * web-next/src/data/builds.json: LLM-authored builds written once on 2026-07-27
 * and frozen, three weeks before the precomputed pipeline was deprecated and
 * five patches before 7.2e. Jinx's stored build opened Phantom Dancer into
 * Guardian Angel, which 15 and 2 of 49 top-50 Jinx players build respectively,
 * and omitted Magnetic Blaster, which 39 of them build.
 *
 * The Build Studio has generated live through the advisor since that
 * deprecation, and every one of those generations is cached in KV against a
 * hash of its inputs. So the fix for both surfaces is not to regenerate a
 * frozen file: it is to read the cache the live path already fills.
 *
 * A cache hit costs nothing. It spends no model call and, deliberately, no
 * generation from the player's daily allowance -- we did not pay for it, so
 * neither should they.
 */
import { buildCacheKey, readCachedBuild, type BuildRequestKey } from "@/lib/build-cache";
import { kvGetJson, kvSetJson } from "@/lib/kv";

/** Long enough to outlive a patch cycle; a newer generation overwrites it. */
const LATEST_TTL_SECONDS = 60 * 60 * 24 * 45;

/**
 * The request a plain "build me this champion" produces.
 *
 * Must stay identical to what /api/v1/build assembles from a body carrying
 * only `champion` and `role`, or the key will not match anything the live path
 * ever wrote and every lookup silently misses.
 */
export function studioRequest(champion: string, role = ""): BuildRequestKey {
  return {
    champion,
    role,
    enemies: [],
    allies: [],
    playstyle: "standard",
    objective: "balanced",
    gamePhase: "balanced",
    damagePath: "standard",
    championForm: "",
    aheadEnemy: "",
    mode: "studio",
    riskTolerance: "medium",
    skillLevel: "average",
    buildBias: "balanced",
    lockedItems: [],
    lockedRunes: [],
  };
}

/**
 * Where the newest plain build for a champion is filed.
 *
 * The per-request cache key is a hash of EVERY input -- playstyle, objective,
 * game phase, damage path, risk, bias, locks -- which is right for answering
 * the same question twice and useless for asking "is there any build for this
 * champion". Measured before this existed: 17 of 141 champions were reachable,
 * because the Build Studio sends a playstyle and objective from its UI and the
 * bare default is a request almost nobody makes. The overlay would have shown
 * "No standard build in the bundle" for the other 124.
 *
 * So a successful studio generation also files itself here, one slot per
 * champion, latest wins. It fills by itself as the site is used.
 */
export function latestBuildKey(champion: string): string {
  return `latest:build:${champion.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
}

/** Record a generated build as this champion's newest plain answer. */
export async function rememberLatestBuild(champion: string, build: unknown): Promise<void> {
  try {
    await kvSetJson(latestBuildKey(champion), build, LATEST_TTL_SECONDS);
  } catch {
    /* the index is a convenience; a failure here must not fail a generation */
  }
}

/**
 * A build for this champion to show without generating one, or null.
 *
 * Prefers the champion index, because that is the one that actually gets
 * written. Falls back to the exact-default key for anything filed before the
 * index existed.
 */
export async function cachedStudioBuild(
  champion: string,
  role = "",
): Promise<Record<string, unknown> | null> {
  const latest = await kvGetJson<Record<string, unknown> | null>(
    latestBuildKey(champion), null);
  if (latest) return latest;
  const tries = role ? ["", role] : [""];
  for (const r of tries) {
    const hit = await readCachedBuild(buildCacheKey(studioRequest(champion, r)));
    if (hit) return hit;
  }
  return null;
}
