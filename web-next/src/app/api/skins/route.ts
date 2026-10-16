import { NextResponse } from "next/server";
import { getChampionSkins } from "@/lib/skins";

/**
 * Skin list for one champion, for the share card's skin picker.
 *
 * The official Wild Rift list (scripts/fetch_wr_skins.py), not League PC's
 * from ddragon: that catalogue offered skins Wild Rift never had, and the
 * card had stopped drawing them, so the picker's choice did nothing.
 * One champion's dozen instead of the whole catalogue.
 */
export async function GET(request: Request) {
  const slug = (new URL(request.url).searchParams.get("champion") ?? "")
    .replace(/[^a-z0-9-]/g, "").slice(0, 60);
  const skins = getChampionSkins(slug).map(({ key, name }) => ({ key, name }));
  return NextResponse.json({ skins }, {
    // The list changes when Riot ships skins, i.e. rarely.
    headers: { "Cache-Control": "public, max-age=86400" },
  });
}
