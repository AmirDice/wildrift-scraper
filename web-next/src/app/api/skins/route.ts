import { NextResponse } from "next/server";
import skinsData from "@/data/champion_skins.json";

/**
 * Skin list for one champion, for the build card's skin picker.
 *
 * A dedicated endpoint because the full catalogue is half a megabyte (7,700
 * skins across the roster) and the popover needs exactly one champion's
 * dozen: importing the JSON into the client bundle would ship 500KB so a
 * dropdown can render.
 */

const SKINS = skinsData as Record<string, { key: string; skins: { num: number; name: string }[] }>;

export async function GET(request: Request) {
  const slug = (new URL(request.url).searchParams.get("champion") ?? "")
    .replace(/[^a-z0-9-]/g, "").slice(0, 60);
  const entry = SKINS[slug];
  if (!entry) return NextResponse.json({ skins: [] });
  return NextResponse.json(entry, {
    // The catalogue changes when Riot ships skins, i.e. rarely.
    headers: { "Cache-Control": "public, max-age=86400" },
  });
}
