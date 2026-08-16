import { readFile } from "node:fs/promises";
import path from "node:path";
import { ImageResponse } from "next/og";
import sharp from "sharp";
import { kvGetJson } from "@/lib/kv";
import { getChampion } from "@/lib/data";
import type { SharedBuild } from "@/app/api/share-build/route";
import engineData from "@/data/engine.json";

/**
 * The shareable build card, as an actual image.
 *
 * GET /api/build-card?d=<base64url JSON>   self-contained: the build rides in
 *                                          the URL, so this works with no KV
 *                                          and no prior snapshot
 * GET /api/build-card?id=<share id>        the /b/{id} snapshot, used as that
 *                                          page's OG image
 *
 * 1200x630, the OG standard, which is the whole point: the same image is what
 * a player downloads to post AND what Discord unfurls when the /b/ link is
 * pasted. One renderer, both jobs.
 *
 * Satori cannot decode webp and cannot fetch relative URLs, and our item art
 * is local webp exactly. Everything local is therefore inlined as a data URI,
 * items converted webp -> png through sharp on the way. The card depends on
 * no origin and no CDN being awake.
 */

export const runtime = "nodejs";

const DATA = engineData as {
  items?: Record<string, { name?: string; icon?: string }>;
};
const itemName = (slug: string) => DATA.items?.[slug]?.name ?? slug;

const BIAS_LABEL: Record<string, string> = {
  max_durability: "Maximum Durability",
  durability: "Durability Leaning",
  damage: "Damage Leaning",
  max_damage: "Maximum Damage",
};

const PUBLIC_DIR = path.join(process.cwd(), "public");

/** Local item webp -> png data URI. Null when the art is missing: the card
 *  then renders a lettered tile rather than a broken image. */
async function itemPng(slug: string): Promise<string | null> {
  try {
    const buf = await readFile(path.join(PUBLIC_DIR, "items", `${slug}.webp`));
    const png = await sharp(buf).resize(96, 96).png().toBuffer();
    return `data:image/png;base64,${png.toString("base64")}`;
  } catch {
    return null;
  }
}

/** Champion splash as a data URI, whether it lives in public/ or on ddragon. */
async function splashUri(splash: string | undefined): Promise<string | null> {
  if (!splash) return null;
  try {
    if (splash.startsWith("/")) {
      const buf = await readFile(path.join(PUBLIC_DIR, splash.slice(1)));
      const jpg = await sharp(buf).resize(1200, 630, { fit: "cover" }).jpeg({ quality: 74 }).toBuffer();
      return `data:image/jpeg;base64,${jpg.toString("base64")}`;
    }
    const res = await fetch(splash);
    if (!res.ok) return null;
    const buf = Buffer.from(await res.arrayBuffer());
    const jpg = await sharp(buf).resize(1200, 630, { fit: "cover" }).jpeg({ quality: 74 }).toBuffer();
    return `data:image/jpeg;base64,${jpg.toString("base64")}`;
  } catch {
    return null;
  }
}

const slugRe = /[^a-z0-9-]/g;
const textRe = /[^A-Za-z0-9 .'&_-]/g;

function parsePayload(raw: string): SharedBuild | null {
  if (raw.length > 2400) return null;
  try {
    const decoded = JSON.parse(Buffer.from(raw, "base64url").toString("utf-8")) as Record<string, unknown>;
    const t = (v: unknown, max = 40) => (typeof v === "string" ? v.replace(textRe, "").slice(0, max) : "");
    const sl = (v: unknown) => (typeof v === "string" ? v.replace(slugRe, "").slice(0, 60) : "");
    const list = (a: unknown, limit: number, c: (x: unknown) => string) =>
      Array.isArray(a) ? a.map(c).filter(Boolean).slice(0, limit) : [];
    const build: SharedBuild = {
      champion: t(decoded.champion),
      championSlug: sl(decoded.championSlug),
      role: t(decoded.role) || undefined,
      playstyle: t(decoded.playstyle) || undefined,
      bias: t(decoded.bias, 20) || undefined,
      patch: t(decoded.patch, 12) || undefined,
      items: list(decoded.items, 6, sl),
      boots: sl(decoded.boots) || undefined,
      bootsUpgrade: sl(decoded.bootsUpgrade) || undefined,
      runes: list(decoded.runes, 6, (x) => t(x)),
      createdAt: "",
    };
    if (!build.champion || build.items.length === 0) return null;
    return build;
  } catch {
    return null;
  }
}

export async function GET(request: Request) {
  const url = new URL(request.url);
  let build: SharedBuild | null = null;

  const d = url.searchParams.get("d");
  if (d) build = parsePayload(d);
  if (!build) {
    const id = url.searchParams.get("id") ?? "";
    if (/^[A-Za-z0-9_-]{8,16}$/.test(id)) {
      build = await kvGetJson<SharedBuild | null>(`share:build:${id}`, null);
    }
  }
  if (!build) return new Response("not found", { status: 404 });

  const champ = getChampion(build.championSlug);
  const [splash, champIcon, ...itemArt] = await Promise.all([
    splashUri(champ?.splash),
    champ?.icon && champ.icon.startsWith("http") ? champ.icon : null,
    ...build.items.map(itemPng),
  ]);
  const bootsFinal = build.bootsUpgrade || build.boots || "";
  const bootsArt = bootsFinal ? await itemPng(bootsFinal) : null;
  const biasLabel = build.bias ? BIAS_LABEL[build.bias] : null;

  return new ImageResponse(
    (
      <div style={{
        width: "100%", height: "100%", display: "flex", flexDirection: "column",
        background: "#070a12", fontFamily: "sans-serif", position: "relative",
      }}>
        {/* the signature: a hairline accent-to-gold gradient across the top */}
        <div style={{
          position: "absolute", top: 0, left: 0, width: 1200, height: 5, display: "flex",
          background: "linear-gradient(90deg, #4f8dff 0%, #7fd6ff 45%, #ffd76e 100%)",
        }} />
        {/* the art, then the site's dark wash so text holds */}
        {splash && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={splash} width={1200} height={630}
               style={{ position: "absolute", top: 0, left: 0, objectFit: "cover" }} />
        )}
        <div style={{
          position: "absolute", top: 5, left: 0, width: 1200, height: 625, display: "flex",
          background: "linear-gradient(100deg, rgba(5,8,15,0.94) 0%, rgba(5,8,15,0.82) 44%, rgba(7,10,18,0.38) 100%)",
        }} />
        <div style={{
          position: "absolute", top: 0, left: 0, width: 1200, height: 630, display: "flex",
          background: "linear-gradient(0deg, rgba(3,5,11,0.85) 0%, rgba(3,5,11,0.0) 38%)",
        }} />

        <div style={{
          position: "relative", display: "flex", flexDirection: "column",
          height: "100%", padding: "44px 56px 36px",
        }}>
          {/* brand */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", fontSize: 26, fontWeight: 800, letterSpacing: "0.14em" }}>
              <span style={{ color: "#4f8dff" }}>WRTRUE</span>
              <span style={{ color: "#eef2fb" }}>META</span>
            </div>
            {build.patch && (
              <div style={{
                display: "flex", fontSize: 20, fontWeight: 700, color: "#9fb6e2",
                border: "2px solid rgba(159,182,226,0.35)", borderRadius: 999, padding: "6px 18px",
              }}>
                Patch {build.patch}
              </div>
            )}
          </div>

          {/* champion */}
          <div style={{ display: "flex", alignItems: "center", marginTop: 26 }}>
            {champIcon && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={champIcon} width={92} height={92}
                   style={{ borderRadius: 22, border: "3px solid rgba(79,141,255,0.65)" }} />
            )}
            <div style={{ display: "flex", flexDirection: "column", marginLeft: 24 }}>
              <div style={{ display: "flex", fontSize: 64, fontWeight: 800, color: "#f4f7ff", letterSpacing: "-0.01em" }}>
                {build.champion}
              </div>
              <div style={{ display: "flex", gap: 10, marginTop: 6 }}>
                {build.role && (
                  <div style={{ display: "flex", fontSize: 19, fontWeight: 700, color: "#b6c1d4",
                                background: "rgba(255,255,255,0.08)", borderRadius: 8, padding: "4px 14px" }}>
                    {build.role}
                  </div>
                )}
                {build.playstyle && (
                  <div style={{ display: "flex", fontSize: 19, fontWeight: 700, color: "#8fd0ff",
                                background: "rgba(79,141,255,0.16)", borderRadius: 8, padding: "4px 14px",
                                textTransform: "capitalize" }}>
                    {build.playstyle}
                  </div>
                )}
                {biasLabel && (
                  <div style={{ display: "flex", fontSize: 19, fontWeight: 700, color: "#ffd76e",
                                background: "rgba(255,215,110,0.14)", borderRadius: 8, padding: "4px 14px" }}>
                    {biasLabel}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* items */}
          <div style={{
            display: "flex", alignItems: "center", gap: 18, marginTop: 40,
            background: "rgba(10,14,24,0.62)", border: "2px solid rgba(255,255,255,0.14)",
            borderRadius: 24, padding: "26px 30px", alignSelf: "flex-start",
          }}>
            {itemArt.map((art, i) => (
              <div key={i} style={{ display: "flex", flexDirection: "column", alignItems: "center", position: "relative" }}>
                {art ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={art} width={88} height={88}
                       style={{ borderRadius: 16, border: "2px solid rgba(255,255,255,0.22)" }} />
                ) : (
                  <div style={{
                    display: "flex", width: 88, height: 88, borderRadius: 16, alignItems: "center",
                    justifyContent: "center", background: "rgba(255,255,255,0.08)",
                    border: "2px solid rgba(255,255,255,0.22)", fontSize: 30, fontWeight: 800, color: "#9fb6e2",
                  }}>
                    {itemName(build.items[i]).slice(0, 2)}
                  </div>
                )}
                <div style={{
                  display: "flex", position: "absolute", top: -10, left: -10, width: 30, height: 30,
                  borderRadius: 999, background: "#0e1322", border: "2px solid rgba(79,141,255,0.7)",
                  color: "#4f8dff", fontSize: 17, fontWeight: 800, alignItems: "center", justifyContent: "center",
                }}>
                  {i + 1}
                </div>
              </div>
            ))}
            {bootsArt && (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", marginLeft: 6 }}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={bootsArt} width={72} height={72}
                     style={{ borderRadius: 14, border: "2px solid rgba(255,215,110,0.55)" }} />
                <div style={{ display: "flex", fontSize: 13, fontWeight: 800, color: "#ffd76e", marginTop: 4, letterSpacing: "0.08em" }}>
                  BOOTS
                </div>
              </div>
            )}
          </div>

          {/* runes */}
          {build.runes.length > 0 && (
            <div style={{ display: "flex", gap: 10, marginTop: 22, flexWrap: "wrap", maxWidth: 820 }}>
              {build.runes.map((rune) => (
                <div key={rune} style={{
                  display: "flex", fontSize: 19, fontWeight: 700, color: "#d9e2f5",
                  background: "rgba(255,255,255,0.07)", border: "2px solid rgba(255,255,255,0.14)",
                  borderRadius: 999, padding: "6px 18px",
                }}>
                  {rune}
                </div>
              ))}
            </div>
          )}

          {/* footer */}
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            marginTop: "auto",
          }}>
            <div style={{ display: "flex", fontSize: 20, color: "#8b93a7" }}>
              Generated by the Build Studio
            </div>
            <div style={{ display: "flex", fontSize: 24, fontWeight: 800, color: "#4f8dff" }}>
              wrtruemeta.com
            </div>
          </div>
        </div>
      </div>
    ),
    {
      width: 1200,
      height: 630,
      headers: {
        // Immutable by content: the payload IS the URL, so a day of caching
        // costs nothing and repeated shares of one build render once.
        "Cache-Control": "public, max-age=86400",
      },
    },
  );
}
