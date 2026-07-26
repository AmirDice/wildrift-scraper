import { NextResponse } from "next/server";
import {
  creatorCategoryKeys,
  creatorPlatformKeys,
  deleteCreator,
  listManagedCreators,
  saveCreator,
} from "@/lib/creator-store";
import type { Creator, CreatorCategory, Platform } from "@/lib/creators";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function authorised(request: Request): boolean {
  const expected = process.env.ADMIN_TOKEN ?? "";
  const provided = new URL(request.url).searchParams.get("token")
    ?? request.headers.get("x-admin-token")
    ?? "";
  return Boolean(expected) && provided === expected;
}

const denied = () => NextResponse.json({ error: "not found" }, { status: 404 });
const text = (value: unknown, max: number) => typeof value === "string" ? value.trim().slice(0, max) : "";
const stringList = (value: unknown, max: number) => {
  const raw = Array.isArray(value) ? value : typeof value === "string" ? value.split(",") : [];
  return raw.map((entry) => text(entry, 40)).filter(Boolean).slice(0, max);
};
const safeUrl = (value: unknown) => {
  const raw = text(value, 500);
  if (!raw) return "";
  try {
    const url = new URL(raw);
    return url.protocol === "https:" || url.protocol === "http:" ? url.toString() : "";
  } catch {
    return "";
  }
};

export async function GET(request: Request) {
  if (!authorised(request)) return denied();
  return NextResponse.json(
    { creators: await listManagedCreators() },
    { headers: { "Cache-Control": "private, no-store, max-age=0" } },
  );
}

export async function PUT(request: Request) {
  if (!authorised(request)) return denied();
  let body: Record<string, unknown>;
  try {
    body = await request.json() as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }

  const name = text(body.name, 80);
  const tagline = text(body.tagline, 180);
  if (!name) return NextResponse.json({ error: "name is required" }, { status: 400 });
  if (!tagline) return NextResponse.json({ error: "tagline is required" }, { status: 400 });

  const categories = stringList(body.categories, 8)
    .filter((key): key is CreatorCategory => creatorCategoryKeys.has(key as CreatorCategory));
  if (!categories.length) return NextResponse.json({ error: "choose at least one category" }, { status: 400 });

  const linksInput = body.links && typeof body.links === "object" ? body.links as Record<string, unknown> : {};
  const links: Creator["links"] = {};
  for (const [key, value] of Object.entries(linksInput)) {
    if (!creatorPlatformKeys.has(key as Platform)) continue;
    const url = safeUrl(value);
    if (url) links[key as Platform] = url;
  }
  if (!Object.keys(links).length) return NextResponse.json({ error: "add at least one valid platform URL" }, { status: 400 });

  const requestedDate = text(body.lastChecked, 10);
  const lastChecked = /^\d{4}-\d{2}-\d{2}$/.test(requestedDate)
    ? requestedDate
    : new Date().toISOString().slice(0, 10);
  const record = await saveCreator({
    id: text(body.id, 80) || undefined,
    name,
    tagline,
    categories,
    languages: stringList(body.languages, 8),
    links,
    avatar: safeUrl(body.avatar) || undefined,
    lastChecked,
  });
  return NextResponse.json({ creator: record });
}

export async function DELETE(request: Request) {
  if (!authorised(request)) return denied();
  const id = new URL(request.url).searchParams.get("id")?.trim() ?? "";
  if (!id) return NextResponse.json({ error: "id is required" }, { status: 400 });
  if (!await deleteCreator(id)) return NextResponse.json({ error: "creator not found" }, { status: 404 });
  return NextResponse.json({ ok: true });
}
