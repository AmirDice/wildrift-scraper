import { NextResponse } from "next/server";
import { deleteBestBuild, listBestBuilds, saveBestBuild } from "@/lib/best-builds";

/**
 * Recording what the best player on a champion actually builds. ADMIN_TOKEN only.
 *
 *   GET    ?token=...                 -> every recorded build
 *   PUT    ?token=...  { ...build }   -> create or overwrite one champion's
 *   DELETE ?token=...&slug=...        -> remove one
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function authorised(request: Request): boolean {
  const expected = process.env.ADMIN_TOKEN ?? "";
  if (!expected) return false;
  const provided = new URL(request.url).searchParams.get("token")
    ?? request.headers.get("x-admin-token")
    ?? "";
  return provided === expected;
}

const denied = () => NextResponse.json({ error: "not found" }, { status: 404 });

export async function GET(request: Request) {
  if (!authorised(request)) return denied();
  return NextResponse.json(
    { builds: await listBestBuilds() },
    { headers: { "Cache-Control": "private, no-store, max-age=0" } },
  );
}

export async function PUT(request: Request) {
  if (!authorised(request)) return denied();

  let body: Record<string, unknown>;
  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }

  const text = (value: unknown, max: number) => (typeof value === "string" ? value.trim().slice(0, max) : "");
  // Items and runes are pasted as comma-separated lists in the admin console,
  // so accept either that or a real array.
  const list = (value: unknown, max: number) => {
    const raw = Array.isArray(value)
      ? value
      : typeof value === "string" ? value.split(",") : [];
    return raw
      .map((entry) => (typeof entry === "string" ? entry.trim() : ""))
      .filter(Boolean)
      .slice(0, max);
  };

  const championSlug = text(body.championSlug, 40).toLowerCase();
  const player = text(body.player, 40);
  if (!championSlug) return NextResponse.json({ error: "championSlug is required" }, { status: 400 });
  if (!player) return NextResponse.json({ error: "player is required" }, { status: 400 });

  const record = await saveBestBuild({
    championSlug,
    player,
    standing: text(body.standing, 60) || undefined,
    items: list(body.items, 6),
    boots: text(body.boots, 40) || undefined,
    runes: list(body.runes, 6),
    note: text(body.note, 400) || undefined,
  });
  return NextResponse.json({ build: record });
}

export async function DELETE(request: Request) {
  if (!authorised(request)) return denied();
  const slug = new URL(request.url).searchParams.get("slug") ?? "";
  if (!slug) return NextResponse.json({ error: "slug is required" }, { status: 400 });
  const ok = await deleteBestBuild(slug.toLowerCase());
  if (!ok) return NextResponse.json({ error: "nothing recorded for that champion" }, { status: 404 });
  return NextResponse.json({ ok: true });
}
