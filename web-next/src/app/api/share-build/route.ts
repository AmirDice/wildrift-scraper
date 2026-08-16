import crypto from "node:crypto";
import { NextResponse } from "next/server";
import { kvGetJson, kvIncr, kvSetJson } from "@/lib/kv";
import { clientIp } from "@/lib/quota";

/**
 * Permanent URLs for generated builds.
 *
 * POST a build snapshot -> { id }, served at /b/{id}. The snapshot is the
 * BUILD, not the request: cache entries expire with the patch cycle and are
 * keyed by request hash, so "the thing I generated last Tuesday" needs its own
 * record or the link dies the moment the cache rolls. 180-day TTL: long enough
 * that a link in a Discord pin still works next season, short enough that the
 * store does not grow forever.
 *
 * Free (a share is an acquisition channel, charging for it would be absurd)
 * but capped at 30 creations per IP per day so it cannot be scripted into a
 * free JSON store.
 */

const TTL_SECONDS = 60 * 60 * 24 * 180;
const DAILY_CAP = 30;

export interface SharedBuild {
  champion: string;
  championSlug: string;
  role?: string;
  playstyle?: string;
  bias?: string;
  patch?: string;
  items: string[];
  boots?: string;
  bootsUpgrade?: string;
  /** Tier-3 enchant lands after this many completed items; 0 = stays tier-2. */
  bootsUpgradeAfter?: number;
  runes: string[];
  summoners?: string[];
  /** ddragon skin number for the card's splash; 0 is the base skin. */
  skin?: number;
  /** Optional display name the player chose to put on their card. */
  player?: string;
  createdAt: string;
}

const slug = (s: unknown, max = 60) =>
  typeof s === "string" ? s.replace(/[^a-z0-9-]/g, "").slice(0, max) : "";
const text = (s: unknown, max = 40) =>
  typeof s === "string" ? s.replace(/[^A-Za-z0-9 .:'&_-]/g, "").slice(0, max) : "";
const list = (a: unknown, limit: number, cleaner: (x: unknown) => string) =>
  Array.isArray(a) ? a.map(cleaner).filter(Boolean).slice(0, limit) : [];

export async function POST(request: Request) {
  let body: Record<string, unknown>;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }

  const snapshot: SharedBuild = {
    champion: text(body.champion),
    championSlug: slug(body.championSlug),
    role: text(body.role) || undefined,
    playstyle: text(body.playstyle) || undefined,
    bias: text(body.bias, 20) || undefined,
    patch: text(body.patch, 12) || undefined,
    items: list(body.items, 6, slug),
    boots: slug(body.boots) || undefined,
    bootsUpgrade: slug(body.bootsUpgrade) || undefined,
    bootsUpgradeAfter: Number.isInteger(body.bootsUpgradeAfter)
      && (body.bootsUpgradeAfter as number) >= 0 && (body.bootsUpgradeAfter as number) <= 5
      ? (body.bootsUpgradeAfter as number) : undefined,
    runes: list(body.runes, 6, (x) => text(x)),
    summoners: list(body.summoners, 2, (x) => text(x, 12)),
    skin: Number.isInteger(body.skin) && (body.skin as number) >= 0 && (body.skin as number) <= 99
      ? (body.skin as number) : undefined,
    player: text(body.player, 24) || undefined,
    createdAt: new Date().toISOString(),
  };
  if (!snapshot.champion || !snapshot.championSlug || snapshot.items.length === 0) {
    return NextResponse.json({ error: "champion and items are required" }, { status: 400 });
  }

  const ipHash = crypto.createHash("sha256").update(clientIp(request)).digest("hex").slice(0, 16);
  const day = new Date().toISOString().slice(0, 10);
  const used = await kvIncr(`share:cap:${ipHash}:${day}`, 1, 60 * 60 * 24);
  if (used > DAILY_CAP) {
    return NextResponse.json({ error: "share limit reached for today" }, { status: 429 });
  }

  // 8 random bytes -> 11 URL-safe chars. Unguessable enough that links are
  // only reachable by being shared, which is the entire privacy model.
  const id = crypto.randomBytes(8).toString("base64url");
  await kvSetJson(`share:build:${id}`, snapshot, TTL_SECONDS);
  return NextResponse.json({ id });
}

export async function GET(request: Request) {
  const id = new URL(request.url).searchParams.get("id") ?? "";
  if (!/^[A-Za-z0-9_-]{8,16}$/.test(id)) {
    return NextResponse.json({ error: "bad id" }, { status: 400 });
  }
  const snapshot = await kvGetJson<SharedBuild | null>(`share:build:${id}`, null);
  if (!snapshot) return NextResponse.json({ error: "not found" }, { status: 404 });
  return NextResponse.json(snapshot);
}
