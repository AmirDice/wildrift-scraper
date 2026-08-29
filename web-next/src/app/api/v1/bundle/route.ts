import { NextResponse } from "next/server";
import { getChampions } from "@/lib/data";
import { CURRENT_PATCH } from "@/lib/patch";
import buildsData from "@/data/builds.json";
import itemsData from "@/data/items.json";

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

function trimBuild(v: Record<string, unknown>): BundleBuild | null {
  const core = Array.isArray(v.coreBuild) ? (v.coreBuild as Record<string, unknown>[]) : [];
  const items = core
    .map((it) => (typeof it.slug === "string" ? it.slug : ""))
    .filter(Boolean);
  if (!items.length) return null;
  const boots = v.boots as Record<string, unknown> | undefined;
  const ench = v.enchantment as Record<string, unknown> | undefined;
  const runes = v.runes as Record<string, unknown> | undefined;
  const summs = Array.isArray(v.summoners) ? (v.summoners as Record<string, unknown>[]) : [];
  // builds.json calls them treeMinors (objects with name/slug/icon/reason)
  const minorSrc = runes && (Array.isArray(runes.treeMinors) ? runes.treeMinors
    : Array.isArray(runes.minors) ? runes.minors : null);
  const minors = minorSrc
    ? (minorSrc as (string | Record<string, unknown>)[])
        .map(toNamed)
        .filter((r): r is BundleNamed => r !== undefined)
    : undefined;
  return {
    label: String(v.label ?? "Standard"),
    items,
    boots: boots && typeof boots.slug === "string" ? boots.slug : undefined,
    bootsUpgrade: ench && typeof ench.slug === "string" ? ench.slug : undefined,
    runes: runes
      ? {
          keystone: toNamed(runes.keystone),
          minors,
          // flexMinor is what the data calls it. Reading `flex` found nothing
          // every single time, so the fifth rune never reached any client.
          flex: toNamed(runes.flexMinor ?? runes.flex),
          tree: runes.primaryTree ? String(runes.primaryTree) : undefined,
        }
      : undefined,
    // Summoners lost their icons the same way the runes did: mapped down to
    // bare names, so anything wanting to show the spell had nothing to show.
    summoners: summs.map(toNamed).filter((x): x is BundleNamed => x !== undefined),
  };
}

export async function GET() {
  const champions = getChampions().map((c) => ({
    slug: c.slug,
    name: c.name,
    role: c.role,
    // the class powers the overlay's comp-fit pick suggestions
    class: c.class,
    tier: c.tier,
    wr: Number.isFinite(c.wr) ? c.wr : null,
    icon: c.icon,
  }));
  const items = (itemsData as Record<string, unknown>[]).map((it) => ({
    slug: it.slug,
    name: it.name,
    cost: it.cost,
    category: it.category,
    icon: it.icon,
  }));
  const builds: Record<string, BundleBuild[]> = {};
  for (const [name, entry] of Object.entries(buildsData as Record<string, Record<string, unknown>>)) {
    const variants = entry.builds && typeof entry.builds === "object"
      ? Object.values(entry.builds as Record<string, Record<string, unknown>>)
      : [];
    const trimmed = variants.map(trimBuild).filter((b): b is BundleBuild => Boolean(b));
    if (trimmed.length) builds[name] = trimmed;
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
