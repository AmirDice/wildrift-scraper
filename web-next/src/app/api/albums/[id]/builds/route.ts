import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { SESSION_COOKIE, readSession } from "@/lib/session";
import { addBuild, removeBuild } from "@/lib/albums";
import { recordActor, trackEvent } from "@/lib/stats";

/**
 * POST   { champion, championSlug, source, ... } -> adds a build to the album.
 * DELETE ?buildId=...                            -> removes one.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const SOURCES = new Set(["recommended", "generated", "custom"]);

export async function POST(request: Request, context: RouteContext<"/api/albums/[id]/builds">) {
  const { id } = await context.params;
  const store = await cookies();
  const user = readSession(store.get(SESSION_COOKIE)?.value);
  if (!user) return NextResponse.json({ error: "sign in first" }, { status: 401 });

  let body: Record<string, unknown>;
  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }

  const text = (value: unknown, max = 60) =>
    typeof value === "string" ? value.slice(0, max) : "";
  const list = (value: unknown, max = 8) =>
    Array.isArray(value)
      ? value.filter((entry): entry is string => typeof entry === "string").slice(0, max)
      : [];

  const champion = text(body.champion, 40);
  const championSlug = text(body.championSlug, 40);
  if (!champion || !championSlug) {
    return NextResponse.json({ error: "champion is required" }, { status: 400 });
  }
  const source = SOURCES.has(text(body.source)) ? (text(body.source) as "recommended" | "generated" | "custom") : "custom";

  const result = await addBuild(id, user.sub, {
    champion,
    championSlug,
    source,
    role: text(body.role, 20) || undefined,
    variant: text(body.variant, 30) || undefined,
    items: list(body.items),
    runes: list(body.runes, 6),
    note: text(body.note, 200) || undefined,
  });
  if (result === null) return NextResponse.json({ error: "not your album" }, { status: 403 });
  if ("error" in result) return NextResponse.json(result, { status: 409 });

  void trackEvent("build_saved");
  // Saving into an album requires an account, so the actor is always the sub.
  void recordActor("saved", `u:${user.sub}`);
  return NextResponse.json({ album: result });
}

export async function DELETE(request: Request, context: RouteContext<"/api/albums/[id]/builds">) {
  const { id } = await context.params;
  const store = await cookies();
  const user = readSession(store.get(SESSION_COOKIE)?.value);
  if (!user) return NextResponse.json({ error: "sign in first" }, { status: 401 });

  const buildId = new URL(request.url).searchParams.get("buildId") ?? "";
  if (!buildId) return NextResponse.json({ error: "buildId is required" }, { status: 400 });

  const album = await removeBuild(id, user.sub, buildId);
  if (!album) return NextResponse.json({ error: "not your album" }, { status: 403 });
  return NextResponse.json({ album });
}
