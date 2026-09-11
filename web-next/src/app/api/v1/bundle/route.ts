import { NextResponse } from "next/server";
import { getChampions, type Champion } from "@/lib/data";
import { roster } from "@/lib/threat";
import { CURRENT_PATCH } from "@/lib/patch";
import itemsData from "@/data/items.json";
import { cachedStudioBuild } from "@/lib/cached-build";
import { ladderConsensusBuild } from "@/lib/ladder-build";

/**
 * The per-patch snapshot for external clients: the /draft page and the
 * Android overlay download this ONCE, then answer every standard-build
 * lookup locally, offline, with zero LLM calls. Only counter/custom builds
 * need the live generator (/api/v1/build).
 *
 * Kept deliberately small: slugs and names, not prose. builds.json is
 * 3.5 MB of reasoning for Build Studio's UI; a phone overlay next to a
 * running game wants the five item slugs and nothing it can look up in the
 * catalogue it already has. Icons stay URLs into this site's own hosting.
 */

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "content-type",
};

/** A named thing the client has to DRAW -- a rune, a summoner spell.
 *  Enough to render it, not just enough to name it. */
type BundleNamed = { name: string; slug?: string; icon?: string };

type BundleBuild = {
  label: string;
  /** "generated" by the advisor, or "ladder" consensus. The app labels them
   *  differently: one is an answer, the other is what everybody builds. */
  source?: "generated" | "ladder";
  items: string[];
  boots?: string;
  bootsUpgrade?: string;
  runes?: {
    keystone?: BundleNamed;
    minors?: BundleNamed[];
    flex?: BundleNamed;
    tree?: string;
  };
  summoners?: BundleNamed[];
};

/** Keep the icon and slug, not only the name.
 *
 *  Accepts either shape: the source is an object per rune, but older curated
 *  entries are bare strings, and a client that gets a name-only rune should
 *  still show the name rather than nothing. */
function toNamed(v: unknown): BundleNamed | undefined {
  if (typeof v === "string") return v ? { name: v } : undefined;
  if (!v || typeof v !== "object") return undefined;
  const o = v as Record<string, unknown>;
  const name = String(o.name ?? "");
  if (!name) return undefined;
  return {
    name,
    slug: typeof o.slug === "string" ? o.slug : undefined,
    icon: typeof o.icon === "string" ? o.icon : undefined,
  };
}

/**
 * An advisor build, trimmed to what the app renders.
 *
 * The advisor answers with plain slug strings where the old precomputed
 * builds.json carried objects,
 * strings where builds.json carried objects, `runes.minors` where it carried
 * `treeMinors`, and `runes.flex` where it carried `flexMinor`. Reading the
 * wrong one of each pair is how the flex rune reached no client for months, so
 * both spellings are accepted on the way in.
 */
function trimAdvisorBuild(v: Record<string, unknown>): BundleBuild | null {
  const items = (Array.isArray(v.items) ? v.items : [])
    .map((s) => (typeof s === "string" ? s : ""))
    .filter(Boolean);
  if (!items.length) return null;
  const runes = v.runes as Record<string, unknown> | undefined;
  const minorSrc = runes && (Array.isArray(runes.minors) ? runes.minors
    : Array.isArray(runes.treeMinors) ? runes.treeMinors : null);
  const summs = Array.isArray(v.summoners) ? (v.summoners as unknown[]) : [];
  return {
    label: "Standard",
    items,
    boots: typeof v.boots === "string" ? v.boots : undefined,
    bootsUpgrade: typeof v.bootsUpgrade === "string" ? v.bootsUpgrade : undefined,
    runes: runes
      ? {
          keystone: toNamed(runes.keystone),
          minors: minorSrc
            ? (minorSrc as (string | Record<string, unknown>)[])
                .map(toNamed)
                .filter((r): r is BundleNamed => r !== undefined)
            : undefined,
          flex: toNamed(runes.flex ?? runes.flexMinor),
          tree: runes.primaryTree ? String(runes.primaryTree) : undefined,
        }
      : undefined,
    summoners: summs.map(toNamed).filter((x): x is BundleNamed => x !== undefined),
  };
}


export async function GET() {
  const R = roster();
  const champions = getChampions().map((c) => {
    const kit = R[c.name];
    return {
      slug: c.slug,
      name: c.name,
      role: c.role,
      // Every role the champion is really played in, primary first. Without
      // this the overlay ranked a support main's Nami above their own
      // junglers for a jungle game, because a flex pick has one role here.
      roles: (c as Champion & { roles?: string[] }).roles ?? [c.role],
      // the class powers the overlay's comp-fit pick suggestions
      class: c.class,
      tier: c.tier,
      wr: Number.isFinite(c.wr) ? c.wr : null,
      icon: c.icon,
      // Kit facts class cannot express, and the ones that decide a pick
      // against a specific composition. Three booleans and a short array per
      // champion, roughly 6 KB across the roster: the overlay cannot rank
      // Olaf against a lockdown comp without them, and it has no other way
      // to learn them offline.
      pctHpDamage: Boolean(kit?.pctHpDamage),
      trueDamage: Boolean(kit?.trueDamage),
      ccImmune: Boolean(kit?.ccImmune),
      mechanics: kit?.mechanics ?? [],
      // HOW MUCH lockdown, not just whether there is any. A boolean put Sona
      // -- one stun, on her ultimate -- level with Alistar, who has three and
      // lands them on demand, and the draft panel drew them as the same
      // threat. One number per champion, so the overlay can show an intensity.
      ccDepth: Number((kit as { ccDepth?: number } | undefined)?.ccDepth ?? 0),
      // A shield or heal that lands on somebody else, and the hand-authored
      // capability values. The overlay ranks the same champions from the same
      // data as the site, so it needs the same inputs or the two disagree in
      // front of the player.
      protectsAllies: Boolean((kit as { protectsAllies?: boolean } | undefined)?.protectsAllies),
      archetypes: (kit as { archetypes?: string[] } | undefined)?.archetypes ?? [],
      draftKit: (kit as { draftKit?: Record<string, number> } | undefined)?.draftKit ?? {},
    };
  });
  const items = (itemsData as Record<string, unknown>[]).map((it) => ({
    slug: it.slug,
    name: it.name,
    cost: it.cost,
    category: it.category,
    icon: it.icon,
  }));
  // BUILDS COME FROM THE ADVISOR CACHE, not from builds.json.
  //
  // builds.json was LLM-authored once on 2026-07-27, frozen three weeks before
  // the precomputed pipeline was deprecated, and is five patches behind. The
  // overlay was shipping those builds offline as "Standard build". Every live
  // generation since is cached in KV, so the bundle serves whichever of those
  // exist and simply omits the champions nobody has generated yet -- the app
  // already renders "No standard build in the bundle" for a missing champion
  // and offers the online path, which is an honest empty rather than a
  // confident stale answer.
  //
  // One KV read per champion, on a route cached for an hour.
  const builds: Record<string, BundleBuild[]> = {};
  const cached = await Promise.all(
    champions.map(async (c) => [c.name, await cachedStudioBuild(c.name, c.role ?? "")] as const),
  );
  for (const [name, build] of cached) {
    // A generated build when one exists, otherwise what the top fifty actually
    // build. Generating one for all 141 up front is what exhausted the model
    // prepayment at 80 champions, and the 61 it did not reach were exactly the
    // problem it was meant to solve. ladder_builds.json costs nothing, covers
    // 140 champions, and is a record of what real players hold rather than an
    // opinion about what they should. The index still fills by itself as
    // people generate, and a generated build wins the moment there is one.
    const trimmed = build ? trimAdvisorBuild(build) : null;
    if (trimmed) {
      builds[name] = [{ ...trimmed, source: "generated" }];
      continue;
    }
    const ladder = ladderConsensusBuild(name);
    if (ladder) {
      builds[name] = [{
        label: "Top 50 consensus",
        items: ladder.items,
        boots: ladder.boots,
        runes: {
          keystone: toNamed(ladder.runes.keystone),
          minors: ladder.runes.minors
            .map(toNamed).filter((r): r is BundleNamed => r !== undefined),
          flex: toNamed(ladder.runes.flex),
          tree: ladder.runes.primaryTree,
        },
        source: "ladder",
      }];
    }
  }
  return NextResponse.json(
    {
      v: 1,
      patch: CURRENT_PATCH ?? null,
      generatedAt: new Date().toISOString(),
      champions,
      items,
      builds,
    },
    {
      headers: {
        ...CORS,
        // a patch's bundle barely changes within a day; clients also cache by
        // the `patch` field and only refetch when it moves
        "Cache-Control": "public, s-maxage=3600, stale-while-revalidate=86400",
      },
    },
  );
}

export function OPTIONS() {
  return new Response(null, { status: 204, headers: CORS });
}
