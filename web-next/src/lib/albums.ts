/**
 * Build Albums and Duo Blends.
 *
 * An **album** is a collection of builds a signed-in player has saved: their
 * one-tricks, their comfort picks, the build they want to try next patch. It is
 * the thing a saved build has been missing -- somewhere to live, and a link
 * worth sending to a friend.
 *
 * A **duo blend** takes two players' albums and mixes them, the way a shared
 * playlist does: how much taste they share, the champions they both saved, and
 * a combined pick list for when they queue together. One player starts a blend
 * and sends the code; the other opens it and joins.
 *
 * Everything is stored in the shared KV (src/lib/kv.ts). Albums are unlisted
 * rather than public: anyone with the id can read one, nothing is indexed, and
 * only the owner can change it.
 */
import crypto from "node:crypto";
import { kvDelete, kvGetJson, kvSetJson } from "@/lib/kv";
import type { SessionUser } from "@/lib/session";

export interface SavedBuild {
  id: string;
  champion: string;
  championSlug: string;
  /** Where the build came from, so the album can show how it was made. */
  source: "recommended" | "generated" | "custom";
  role?: string;
  /** Playstyle variant for recommended builds ("standard", "crit", ...). */
  variant?: string;
  items: string[];
  runes: string[];
  note?: string;
  addedAt: string;
}

/** A shared-album memory: a screenshot or image a duo wants to keep together.
 *
 *  The image itself is NOT stored here. KV holds small JSON values, not
 *  megabyte photos, so `imageUrl` points at a blob host (see uploadMemoryImage
 *  in src/lib/memory-upload.ts). This record is only the metadata around it. */
export interface Memory {
  id: string;
  imageUrl: string;
  category: MemoryCategory;
  caption?: string;
  /** Who added it, so a shared album can attribute each memory to a partner. */
  addedBySub: string;
  addedByName: string;
  addedAt: string;
}

/** The fixed set a memory can be filed under, so a duo can filter their wall.
 *  Kept small and concrete: an open-ended tag list becomes a mess of near
 *  duplicates ("funny", "funny moment", "lol") that filtering cannot use. */
export const MEMORY_CATEGORIES = [
  "victory",
  "rank-up",
  "funny-chat",
  "favorite",
] as const;
export type MemoryCategory = (typeof MEMORY_CATEGORIES)[number];

export const MEMORY_CATEGORY_LABELS: Record<MemoryCategory, string> = {
  victory: "Victory screenshots",
  "rank-up": "Rank-up moments",
  "funny-chat": "Funny chats",
  favorite: "Favorite memories",
};

export function isMemoryCategory(value: unknown): value is MemoryCategory {
  return typeof value === "string"
    && (MEMORY_CATEGORIES as readonly string[]).includes(value);
}

export interface Album {
  id: string;
  ownerSub: string;
  ownerName: string;
  ownerPicture?: string;
  title: string;
  description?: string;
  builds: SavedBuild[];
  createdAt: string;
  updatedAt: string;
}

export interface AlbumSummary {
  id: string;
  title: string;
  description?: string;
  ownerName: string;
  buildCount: number;
  champions: string[];
  updatedAt: string;
}

const MAX_ALBUMS_PER_USER = 20;
const MAX_BUILDS_PER_ALBUM = 60;
/** Blends expire if nobody joins or opens them for three months. */
const BLEND_TTL_SECONDS = 60 * 60 * 24 * 90;

const albumKey = (id: string) => `album:${id}`;
const userAlbumsKey = (sub: string) => `u:${sub}:albums`;
const userBlendsKey = (sub: string) => `u:${sub}:blends`;
const blendKey = (code: string) => `blend:${code}`;

function newId(bytes = 8): string {
  return crypto.randomBytes(bytes).toString("base64url");
}

/** Blend codes are read aloud and typed, so they avoid look-alike characters. */
function newBlendCode(): string {
  const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  return Array.from(crypto.randomBytes(6))
    .map((byte) => alphabet[byte % alphabet.length])
    .join("");
}

function summarize(album: Album): AlbumSummary {
  return {
    id: album.id,
    title: album.title,
    description: album.description,
    ownerName: album.ownerName,
    buildCount: album.builds.length,
    champions: [...new Set(album.builds.map((build) => build.champion))].slice(0, 8),
    updatedAt: album.updatedAt,
  };
}

/* ── albums ──────────────────────────────────────────────────────────────── */

export async function listAlbums(sub: string): Promise<AlbumSummary[]> {
  const ids = await kvGetJson<string[]>(userAlbumsKey(sub), []);
  const albums = await Promise.all(ids.map((id) => getAlbum(id)));
  return albums
    .filter((album): album is Album => Boolean(album))
    .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt))
    .map(summarize);
}

export async function getAlbum(id: string): Promise<Album | null> {
  return kvGetJson<Album | null>(albumKey(id), null);
}

export async function createAlbum(
  user: SessionUser,
  title: string,
  description?: string,
): Promise<Album | { error: string }> {
  const ids = await kvGetJson<string[]>(userAlbumsKey(user.sub), []);
  if (ids.length >= MAX_ALBUMS_PER_USER) {
    return { error: `You can keep ${MAX_ALBUMS_PER_USER} albums. Delete one to make room.` };
  }
  const now = new Date().toISOString();
  const album: Album = {
    id: newId(),
    ownerSub: user.sub,
    ownerName: user.name,
    ownerPicture: user.picture,
    title: title.trim().slice(0, 60) || "Untitled album",
    description: description?.trim().slice(0, 200),
    builds: [],
    createdAt: now,
    updatedAt: now,
  };
  await kvSetJson(albumKey(album.id), album);
  await kvSetJson(userAlbumsKey(user.sub), [album.id, ...ids]);
  return album;
}

export async function updateAlbum(
  id: string,
  sub: string,
  patch: { title?: string; description?: string },
): Promise<Album | null> {
  const album = await getAlbum(id);
  if (!album || album.ownerSub !== sub) return null;
  if (patch.title !== undefined) album.title = patch.title.trim().slice(0, 60) || album.title;
  if (patch.description !== undefined) album.description = patch.description.trim().slice(0, 200);
  album.updatedAt = new Date().toISOString();
  await kvSetJson(albumKey(id), album);
  return album;
}

export async function deleteAlbum(id: string, sub: string): Promise<boolean> {
  const album = await getAlbum(id);
  if (!album || album.ownerSub !== sub) return false;
  await kvDelete(albumKey(id));
  const ids = await kvGetJson<string[]>(userAlbumsKey(sub), []);
  await kvSetJson(userAlbumsKey(sub), ids.filter((entry) => entry !== id));
  return true;
}

export async function addBuild(
  id: string,
  sub: string,
  build: Omit<SavedBuild, "id" | "addedAt">,
): Promise<Album | { error: string } | null> {
  const album = await getAlbum(id);
  // Distinguish "gone" from "not yours": returning null for both made a missing
  // album (the dev memory-store bug above) read as "not your album", which sent
  // people hunting for a permissions problem that was really a lost record.
  if (!album) return { error: "That album no longer exists. Refresh and try again." };
  if (album.ownerSub !== sub) return null;
  if (album.builds.length >= MAX_BUILDS_PER_ALBUM) {
    return { error: `That album is full (${MAX_BUILDS_PER_ALBUM} builds).` };
  }
  // A duplicate is the same CONTENT, not the same label.
  //
  // This used to compare champion + variant + source, which rejected saves
  // that were genuinely different builds: Pyke Mid and Pyke Support collided
  // because role was never part of the key, and every counter build for a
  // champion collided with every other one because they all carry
  // variant="counter" -- even though a counter build exists precisely to
  // answer one specific enemy team. Players reported it as "you can only save
  // one build per champion", which was close enough to true.
  //
  // Comparing the items and runes instead means two saves collide only when
  // they really are the same loadout, which is the only case worth refusing.
  const sameLoadout = (a: readonly string[], b: readonly string[]) =>
    a.length === b.length && a.every((value, index) => value === b[index]);
  const duplicate = album.builds.find(
    (entry) => entry.championSlug === build.championSlug
      && sameLoadout(entry.items, build.items)
      && sameLoadout(entry.runes, build.runes),
  );
  if (duplicate) {
    return { error: `That exact ${build.champion} build is already in this album.` };
  }

  album.builds.unshift({ ...build, id: newId(6), addedAt: new Date().toISOString() });
  album.updatedAt = new Date().toISOString();
  await kvSetJson(albumKey(id), album);
  return album;
}

export async function removeBuild(id: string, sub: string, buildId: string): Promise<Album | null> {
  const album = await getAlbum(id);
  if (!album || album.ownerSub !== sub) return null;
  album.builds = album.builds.filter((entry) => entry.id !== buildId);
  album.updatedAt = new Date().toISOString();
  await kvSetJson(albumKey(id), album);
  return album;
}

/* ── blends ──────────────────────────────────────────────────────────────── */

export interface BlendRecord {
  code: string;
  a: { sub: string; name: string; picture?: string };
  b?: { sub: string; name: string; picture?: string };
  /** The duo's shared album: victories, rank-ups, funny chats, keepsakes.
   *  Lives on the blend, not on either person's own album, because it belongs
   *  to the pair -- either member adds to it and either can set the banner. */
  memories?: Memory[];
  /** The image chosen as the duo-profile banner, by id. One at a time. */
  bannerMemoryId?: string;
  createdAt: string;
}

export interface BlendResult {
  code: string;
  a: BlendRecord["a"];
  b?: BlendRecord["b"];
  /** 0-100 taste match. Champions weigh most, then items, then roles. */
  match: number;
  sharedChampions: { champion: string; championSlug: string }[];
  onlyA: string[];
  onlyB: string[];
  sharedItems: string[];
  /** The combined pick list: what to play when these two queue together. */
  duoPicks: { champion: string; championSlug: string; from: "both" | "a" | "b"; role?: string }[];
  /** Empty until the second player joins. */
  pending: boolean;
  /** The shared album carried through from the record, so the view has it. */
  memories: Memory[];
  bannerMemoryId?: string;
}

/* ── shared-album memories (on the blend) ────────────────────────────────── */

const MAX_MEMORIES_PER_BLEND = 100;

/** A memory contributor must be one of the two players in the blend. */
function isBlendMember(record: BlendRecord, sub: string): boolean {
  return record.a.sub === sub || record.b?.sub === sub;
}

/** Add a memory to a duo's shared album. Either member may. */
export async function addBlendMemory(
  code: string,
  contributor: { sub: string; name: string },
  memory: { imageUrl: string; category: MemoryCategory; caption?: string },
): Promise<BlendRecord | { error: string } | null> {
  const record = await getBlendRecord(code);
  if (!record) return null;
  if (!isBlendMember(record, contributor.sub)) return null;
  const memories = record.memories ?? [];
  if (memories.length >= MAX_MEMORIES_PER_BLEND) {
    return { error: `This shared album is full (${MAX_MEMORIES_PER_BLEND} memories).` };
  }
  memories.unshift({
    id: newId(6),
    imageUrl: memory.imageUrl,
    category: memory.category,
    caption: memory.caption?.slice(0, 200),
    addedBySub: contributor.sub,
    addedByName: contributor.name,
    addedAt: new Date().toISOString(),
  });
  record.memories = memories;
  await kvSetJson(blendKey(record.code), record, BLEND_TTL_SECONDS);
  return record;
}

/** Remove a memory. Either member may remove their own; anyone in the duo may
 *  remove any -- it is a shared space between two people who trust each other. */
export async function removeBlendMemory(
  code: string, sub: string, memoryId: string,
): Promise<BlendRecord | null> {
  const record = await getBlendRecord(code);
  if (!record || !isBlendMember(record, sub)) return null;
  record.memories = (record.memories ?? []).filter((m) => m.id !== memoryId);
  if (record.bannerMemoryId === memoryId) delete record.bannerMemoryId;
  await kvSetJson(blendKey(record.code), record, BLEND_TTL_SECONDS);
  return record;
}

/** Choose the duo-profile banner, or clear it with null. Either member may:
 *  it is the pair's banner, not one person's. One image at a time. */
export async function setBlendBanner(
  code: string, sub: string, memoryId: string | null,
): Promise<BlendRecord | null> {
  const record = await getBlendRecord(code);
  if (!record || !isBlendMember(record, sub)) return null;
  if (memoryId === null) {
    delete record.bannerMemoryId;
  } else {
    if (!(record.memories ?? []).some((m) => m.id === memoryId)) return null;
    record.bannerMemoryId = memoryId;
  }
  await kvSetJson(blendKey(record.code), record, BLEND_TTL_SECONDS);
  return record;
}

export async function createBlend(user: SessionUser): Promise<BlendRecord> {
  const record: BlendRecord = {
    code: newBlendCode(),
    a: { sub: user.sub, name: user.name, picture: user.picture },
    createdAt: new Date().toISOString(),
  };
  await kvSetJson(blendKey(record.code), record, BLEND_TTL_SECONDS);
  const codes = await kvGetJson<string[]>(userBlendsKey(user.sub), []);
  await kvSetJson(userBlendsKey(user.sub), [record.code, ...codes].slice(0, 20));
  return record;
}

export async function getBlendRecord(code: string): Promise<BlendRecord | null> {
  return kvGetJson<BlendRecord | null>(blendKey(code.toUpperCase()), null);
}

export async function joinBlend(
  code: string,
  user: SessionUser,
): Promise<BlendRecord | { error: string }> {
  const record = await getBlendRecord(code);
  if (!record) return { error: "That blend link has expired or never existed." };
  if (record.a.sub === user.sub) return record; // opening your own blend is fine
  if (record.b && record.b.sub !== user.sub) {
    return { error: "This blend already has two players." };
  }
  record.b = { sub: user.sub, name: user.name, picture: user.picture };
  await kvSetJson(blendKey(record.code), record, BLEND_TTL_SECONDS);
  const codes = await kvGetJson<string[]>(userBlendsKey(user.sub), []);
  if (!codes.includes(record.code)) {
    await kvSetJson(userBlendsKey(user.sub), [record.code, ...codes].slice(0, 20));
  }
  return record;
}

export async function listBlends(sub: string): Promise<BlendRecord[]> {
  const codes = await kvGetJson<string[]>(userBlendsKey(sub), []);
  const records = await Promise.all(codes.map((code) => getBlendRecord(code)));
  return records.filter((record): record is BlendRecord => Boolean(record));
}

/** Every build a player has across all their albums. */
async function allBuilds(sub: string): Promise<SavedBuild[]> {
  const ids = await kvGetJson<string[]>(userAlbumsKey(sub), []);
  const albums = await Promise.all(ids.map((id) => getAlbum(id)));
  return albums.filter((album): album is Album => Boolean(album)).flatMap((album) => album.builds);
}

function jaccard(left: Set<string>, right: Set<string>): number {
  if (left.size === 0 && right.size === 0) return 0;
  const shared = [...left].filter((entry) => right.has(entry)).length;
  const union = new Set([...left, ...right]).size;
  return union === 0 ? 0 : shared / union;
}

/**
 * Mixes two players' albums.
 *
 * The match number is a weighted overlap: champions carry the most (what you
 * play is most of your taste), then items (how you play them), then roles.
 * Nobody scores 100 unless their albums are identical, which is the point.
 */
export async function computeBlend(code: string): Promise<BlendResult | null> {
  const record = await getBlendRecord(code);
  if (!record) return null;
  if (!record.b) {
    return {
      code: record.code, a: record.a, match: 0, sharedChampions: [],
      onlyA: [], onlyB: [], sharedItems: [], duoPicks: [], pending: true,
      // A solo player can still start the wall before a partner joins.
      memories: record.memories ?? [], bannerMemoryId: record.bannerMemoryId,
    };
  }

  const [buildsA, buildsB] = await Promise.all([allBuilds(record.a.sub), allBuilds(record.b.sub)]);
  const slugToName = new Map<string, string>();
  const collect = (builds: SavedBuild[]) => {
    for (const build of builds) slugToName.set(build.championSlug, build.champion);
    return {
      champions: new Set(builds.map((build) => build.championSlug)),
      items: new Set(builds.flatMap((build) => build.items)),
      roles: new Set(builds.map((build) => build.role).filter((role): role is string => Boolean(role))),
    };
  };
  const left = collect(buildsA);
  const right = collect(buildsB);

  const match = Math.round(
    (jaccard(left.champions, right.champions) * 0.55
      + jaccard(left.items, right.items) * 0.3
      + jaccard(left.roles, right.roles) * 0.15) * 100,
  );

  const sharedSlugs = [...left.champions].filter((slug) => right.champions.has(slug));
  const roleOf = (slug: string) =>
    [...buildsA, ...buildsB].find((build) => build.championSlug === slug)?.role;

  const duoPicks: BlendResult["duoPicks"] = [
    ...sharedSlugs.map((slug) => ({
      champion: slugToName.get(slug) ?? slug, championSlug: slug, from: "both" as const, role: roleOf(slug),
    })),
    ...[...left.champions].filter((slug) => !right.champions.has(slug)).slice(0, 3).map((slug) => ({
      champion: slugToName.get(slug) ?? slug, championSlug: slug, from: "a" as const, role: roleOf(slug),
    })),
    ...[...right.champions].filter((slug) => !left.champions.has(slug)).slice(0, 3).map((slug) => ({
      champion: slugToName.get(slug) ?? slug, championSlug: slug, from: "b" as const, role: roleOf(slug),
    })),
  ].slice(0, 10);

  return {
    code: record.code,
    a: record.a,
    b: record.b,
    match,
    sharedChampions: sharedSlugs.map((slug) => ({
      champion: slugToName.get(slug) ?? slug, championSlug: slug,
    })),
    onlyA: [...left.champions].filter((slug) => !right.champions.has(slug))
      .map((slug) => slugToName.get(slug) ?? slug),
    onlyB: [...right.champions].filter((slug) => !left.champions.has(slug))
      .map((slug) => slugToName.get(slug) ?? slug),
    sharedItems: [...left.items].filter((item) => right.items.has(item)).slice(0, 12),
    duoPicks,
    pending: false,
    memories: record.memories ?? [],
    bannerMemoryId: record.bannerMemoryId,
  };
}
