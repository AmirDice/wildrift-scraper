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

type BundleBuild = {
  label: string;
  items: string[];
  boots?: string;
  bootsUpgrade?: string;
  runes?: { keystone?: string; minors?: string[]; flex?: string; tree?: string };
  summoners?: string[];
};

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
    ? (minorSrc as (string | Record<string, unknown>)[]).map((m) =>
        typeof m === "string" ? m : String(m.name ?? "")).filter(Boolean)
    : undefined;
  return {
    label: String(v.label ?? "Standard"),
    items,
    boots: boots && typeof boots.slug === "string" ? boots.slug : undefined,
    bootsUpgrade: ench && typeof ench.slug === "string" ? ench.slug : undefined,
    runes: runes
      ? {
          keystone: typeof runes.keystone === "object" && runes.keystone
            ? String((runes.keystone as Record<string, unknown>).name ?? "")
            : String(runes.keystone ?? ""),
          minors,
          flex: typeof runes.flex === "object" && runes.flex
            ? String((runes.flex as Record<string, unknown>).name ?? "")
            : runes.flex ? String(runes.flex) : undefined,
          tree: runes.primaryTree ? String(runes.primaryTree) : undefined,
        }
      : undefined,
    summoners: summs.map((s2) => String(s2.name ?? "")).filter(Boolean),
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
