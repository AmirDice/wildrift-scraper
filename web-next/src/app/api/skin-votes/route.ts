import crypto from "node:crypto";
import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { kvGet, kvGetNumbers, kvIncr, kvSet } from "@/lib/kv";
import { clientIp } from "@/lib/quota";
import { SESSION_COOKIE, readSession } from "@/lib/session";
import { getChampionSkins } from "@/lib/skins";

/**
 * Skin votes: each player picks ONE favourite skin per champion.
 *
 *   GET  /api/skin-votes?champion=riven  -> { counts: { [skinKey]: n }, mine }
 *   POST { champion, skin }              -> same; voting for your current
 *                                           pick again takes the vote back
 *
 * One vote per voter per champion, changeable, so a share of the vote means
 * something and repeat clicking cannot stuff it. A voter is their Google
 * sign-in, or a hashed IP when signed out (the same identity the build
 * allowance uses). Counts live in KV as skinvote:<champion>:c:<skinKey>, the
 * voter's pick as skinvote:<champion>:v:<voter>.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const CHANGES_PER_HOUR = 30;

async function voterId(request: Request): Promise<string> {
  const store = await cookies();
  const user = readSession(store.get(SESSION_COOKIE)?.value);
  const raw = user ? `user:${user.sub}` : `ip:${clientIp(request)}`;
  return crypto.createHash("sha256").update(raw).digest("hex").slice(0, 24);
}

async function state(champion: string, voter: string) {
  const skins = getChampionSkins(champion);
  const values = await kvGetNumbers(skins.map((skin) => `skinvote:${champion}:c:${skin.key}`));
  const counts = Object.fromEntries(skins.map((skin, index) => [skin.key, Math.max(0, values[index] ?? 0)]));
  const mine = await kvGet(`skinvote:${champion}:v:${voter}`);
  return { counts, mine: mine && mine in counts ? mine : null };
}

const NO_STORE = { headers: { "Cache-Control": "private, no-store" } };

export async function GET(request: Request) {
  const champion = new URL(request.url).searchParams.get("champion") ?? "";
  if (!getChampionSkins(champion).length) return NextResponse.json({ error: "unknown champion" }, { status: 400 });
  return NextResponse.json(await state(champion, await voterId(request)), NO_STORE);
}

export async function POST(request: Request) {
  let body: { champion?: unknown; skin?: unknown };
  try { body = (await request.json()) as typeof body; } catch { return NextResponse.json({ error: "invalid JSON" }, { status: 400 }); }
  const champion = typeof body.champion === "string" ? body.champion : "";
  const skin = typeof body.skin === "string" ? body.skin : "";
  const skins = getChampionSkins(champion);
  if (!skins.some((entry) => entry.key === skin)) return NextResponse.json({ error: "unknown skin" }, { status: 400 });

  const voter = await voterId(request);
  if (await kvIncr(`skinvote:rate:${voter}`, 1, 3600) > CHANGES_PER_HOUR) {
    return NextResponse.json({ error: "Too many votes from you this hour. Try again later." }, { status: 429 });
  }
  const pickKey = `skinvote:${champion}:v:${voter}`;
  const previous = await kvGet(pickKey);
  if (previous) await kvIncr(`skinvote:${champion}:c:${previous}`, -1);
  if (previous === skin) {
    await kvSet(pickKey, "");          // same skin again: take the vote back
  } else {
    await kvIncr(`skinvote:${champion}:c:${skin}`, 1);
    await kvSet(pickKey, skin);
  }
  return NextResponse.json(await state(champion, voter), NO_STORE);
}
