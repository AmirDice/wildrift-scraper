import { readFile } from "node:fs/promises";
import path from "node:path";
import { ImageResponse } from "next/og";
import sharp from "sharp";
import { getChampions, regionBoard, TIER_ORDER, tierLabel, type Champion } from "@/lib/data";
import { getGlobalChampions, getCnChampionsByBracket, CN_META, type CnBracketKey } from "@/lib/cn";
import { CURRENT_PATCH } from "@/lib/patch";

/**
 * The tier list as a shareable 1200x630 card, sibling to the build card:
 * same footer voice, same full-bleed splash treatment, same "download OR
 * unfurl" size.
 *
 * GET /api/tier-card?region=Global|EU|NA|CN&role=Baron|Jungle|Mid|Dragon|Support
 *
 * Both params are validated against closed sets -- nothing caller-supplied is
 * ever fetched. Pool depth and the raw-number toggle are deliberately absent:
 * the card is the canonical full-pool board, not a screenshot of one person's
 * toggles. The background is the top-ranked champion's own splash, darkened
 * until the tier rows carry the image.
 */

export const runtime = "nodejs";

const PUBLIC_DIR = path.join(process.cwd(), "public");
const REGIONS = ["Global", "EU", "NA", "CN"] as const;
type RegionKey = (typeof REGIONS)[number];
const ROLES = ["Baron", "Jungle", "Mid", "Dragon", "Support"] as const;

/** Mirrors the tier chips in globals.css: the one place colour is loud. */
const TIER_STYLE: Record<string, { bg: string; fg: string }> = {
  GOD: { bg: "linear-gradient(135deg, #ffce4d, #ff7a1a 55%, #ee4a26)", fg: "#1a0c00" },
  S: { bg: "linear-gradient(135deg, #ff9a4d, #ff6f2c)", fg: "#1a0c00" },
  A: { bg: "linear-gradient(135deg, #ffd45a, #f3b400)", fg: "#2a1c00" },
  B: { bg: "linear-gradient(135deg, #5b9dff, #3a78e0)", fg: "#07121f" },
  C: { bg: "linear-gradient(135deg, #9aa2b6, #6a7286)", fg: "#0b0f18" },
  Ass: { bg: "linear-gradient(135deg, #424a60, #2b3142)", fg: "#aeb6ca" },
};

let LOGO_URI: string | null | undefined;
async function logoUri(): Promise<string | null> {
  if (LOGO_URI !== undefined) return LOGO_URI;
  try {
    const buf = await readFile(path.join(PUBLIC_DIR, "logo.png"));
    const png = await sharp(buf).resize({ height: 68 }).png().toBuffer();
    LOGO_URI = `data:image/png;base64,${png.toString("base64")}`;
  } catch {
    LOGO_URI = null;
  }
  return LOGO_URI;
}

/** Champion head icons, fetched once per process. ~90 icons feed a full
 *  board, so without this cache every render would re-download the roster. */
const ICON_CACHE = new Map<string, string | null>();
async function champIconUri(url: string | undefined): Promise<string | null> {
  if (!url || !url.startsWith("http")) return null;
  const hit = ICON_CACHE.get(url);
  if (hit !== undefined) return hit;
  let uri: string | null = null;
  try {
    const res = await fetch(url);
    if (res.ok) {
      const buf = Buffer.from(await res.arrayBuffer());
      const jpg = await sharp(buf).resize(72, 72).jpeg({ quality: 82 }).toBuffer();
      uri = `data:image/jpeg;base64,${jpg.toString("base64")}`;
    }
  } catch {
    uri = null;
  }
  ICON_CACHE.set(url, uri);
  return uri;
}

/** The #1 champion's stored splash, cover-cropped to the card. Local file, so
 *  the background needs no network at all. */
async function splashUri(splash: string | undefined): Promise<string | null> {
  if (!splash || !splash.startsWith("/")) return null;
  try {
    const buf = await readFile(path.join(PUBLIC_DIR, splash.replace(/^\//, "")));
    const jpg = await sharp(buf)
      .resize(1200, 630, { fit: "cover", position: "attention" })
      .jpeg({ quality: 72 })
      .toBuffer();
    return `data:image/jpeg;base64,${jpg.toString("base64")}`;
  } catch {
    return null;
  }
}

const MAX_PER_ROW = 17;

export async function GET(request: Request) {
  const url = new URL(request.url);
  const region = (REGIONS.find((r) => r === url.searchParams.get("region")) ?? "Global") as RegionKey;
  const roleParam = url.searchParams.get("role") ?? "";
  const role = ROLES.find((r) => r === roleParam) ?? null;

  const cnBracket = CN_META.defaultBracket as CnBracketKey;
  const champions: Champion[] =
    region === "Global" ? getGlobalChampions()
    : region === "EU" ? getChampions()
    : region === "NA" ? regionBoard("NA").champions
    : (getCnChampionsByBracket()[cnBracket] as unknown as Champion[]);

  // Same bucketing as the page: role boards re-tier within the role.
  const pool = role ? champions.filter((c) => c.role === role) : champions;
  const buckets: Record<string, Champion[]> = {};
  for (const t of TIER_ORDER) buckets[t] = [];
  for (const c of [...pool].sort((a, b) => b.wr - a.wr)) {
    (buckets[role ? c.tierRole : c.tier] ??= []).push(c);
  }
  const rows = TIER_ORDER
    .map((tier) => ({ tier, all: buckets[tier] ?? [] }))
    .filter((row) => row.all.length > 0)
    .map((row) => ({ ...row, shown: row.all.slice(0, MAX_PER_ROW), extra: row.all.length - Math.min(row.all.length, MAX_PER_ROW) }));

  const top = buckets.GOD?.[0] ?? pool[0];
  const shownChamps = rows.flatMap((r) => r.shown);
  const [logo, splash, ...icons] = await Promise.all([
    logoUri(),
    splashUri(top?.splash),
    ...shownChamps.map((c) => champIconUri(c.icon)),
  ]);
  const iconBySlug = new Map(shownChamps.map((c, i) => [c.slug, icons[i]]));

  const bracketLabel = CN_META.brackets.find((b) => b.key === cnBracket)?.label ?? "";
  const regionLabel = region === "Global" ? "Global · EU + NA"
    : region === "CN" ? `China · ${bracketLabel}`
    : region;
  const basis = region === "CN"
    ? "Official China server data, lolm.qq.com"
    : "Confidence-adjusted win rates of each champion's top 50 players";

  return new ImageResponse(
    (
      <div style={{
        width: "100%", height: "100%", display: "flex", flexDirection: "column",
        background: "#070a12", fontFamily: "sans-serif", position: "relative",
      }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        {splash && <img src={splash} width={1200} height={630}
                        style={{ position: "absolute", top: 0, left: 0 }} />}
        {/* The rows carry the card; the splash is atmosphere, not subject. */}
        <div style={{
          position: "absolute", top: 0, left: 0, width: 1200, height: 630, display: "flex",
          background: "rgba(6,9,17,0.85)",
        }} />
        <div style={{
          position: "absolute", top: 0, left: 0, width: 1200, height: 630, display: "flex",
          background: "linear-gradient(95deg, rgba(6,9,17,0.6) 0%, rgba(6,9,17,0.05) 60%)",
        }} />
        <div style={{
          position: "absolute", top: 0, left: 0, width: 1200, height: 6, display: "flex",
          background: "linear-gradient(90deg, #ffce4d, #4f8dff 45%, #22d3aa)",
        }} />

        <div style={{
          position: "relative", display: "flex", flexDirection: "column",
          width: "100%", height: "100%", padding: "26px 34px 22px",
        }}>
          {/* header */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
              {logo
                // eslint-disable-next-line @next/next/no-img-element
                ? <img src={logo} height={34} />
                : <div style={{ display: "flex", fontSize: 26, fontWeight: 800, color: "#eef2fb" }}>WRTRUEMETA</div>}
              <div style={{ display: "flex", fontSize: 25, fontWeight: 800, color: "#eef2fb", letterSpacing: "0.01em" }}>
                Tier List
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{
                display: "flex", fontSize: 16, fontWeight: 700, color: "#cfe0ff",
                background: "rgba(79,141,255,0.16)", border: "1px solid rgba(79,141,255,0.4)",
                borderRadius: 999, padding: "5px 14px",
              }}>
                {regionLabel}{role ? ` · ${role}` : ""}
              </div>
              {CURRENT_PATCH && (
                <div style={{
                  display: "flex", fontSize: 16, fontWeight: 700, color: "#9fb6e2",
                  border: "1px solid rgba(255,255,255,0.22)", borderRadius: 999, padding: "5px 14px",
                }}>
                  Patch {CURRENT_PATCH}
                </div>
              )}
            </div>
          </div>

          {/* tier rows */}
          <div style={{ display: "flex", flexDirection: "column", gap: 9, marginTop: 18, flexGrow: 1 }}>
            {rows.map((row) => {
              const style = TIER_STYLE[row.tier] ?? TIER_STYLE.C;
              return (
                <div key={row.tier} style={{
                  display: "flex", alignItems: "center", gap: 14,
                  background: "rgba(10,14,24,0.66)", border: "1px solid rgba(255,255,255,0.10)",
                  borderRadius: 16, padding: "7px 12px", flexGrow: 1,
                }}>
                  <div style={{
                    display: "flex", alignItems: "center", justifyContent: "center",
                    width: 62, height: 44, borderRadius: 11, background: style.bg,
                    fontSize: tierLabel(row.tier as (typeof TIER_ORDER)[number]).length > 1 ? 20 : 24,
                    fontWeight: 900, color: style.fg, letterSpacing: "0.02em", flexShrink: 0,
                  }}>
                    {tierLabel(row.tier as (typeof TIER_ORDER)[number])}
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 7, flexWrap: "nowrap" }}>
                    {row.shown.map((c) => {
                      const icon = iconBySlug.get(c.slug);
                      return icon ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img key={c.slug} src={icon} width={46} height={46}
                             style={{ borderRadius: 10, border: "1px solid rgba(255,255,255,0.28)" }} />
                      ) : (
                        <div key={c.slug} style={{
                          display: "flex", width: 46, height: 46, borderRadius: 10,
                          alignItems: "center", justifyContent: "center",
                          background: "rgba(255,255,255,0.09)", border: "1px solid rgba(255,255,255,0.22)",
                          fontSize: 15, fontWeight: 800, color: "#9fb6e2",
                        }}>
                          {c.name.slice(0, 2)}
                        </div>
                      );
                    })}
                    {row.extra > 0 && (
                      <div style={{
                        display: "flex", height: 46, alignItems: "center", justifyContent: "center",
                        borderRadius: 10, padding: "0 10px",
                        background: "rgba(255,255,255,0.07)", border: "1px solid rgba(255,255,255,0.16)",
                        fontSize: 16, fontWeight: 800, color: "#9fb6e2",
                      }}>
                        +{row.extra}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* footer */}
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 14,
          }}>
            <div style={{ display: "flex", fontSize: 15, color: "#7f8a9e", letterSpacing: "0.02em" }}>
              {basis}
            </div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
              <span style={{ fontSize: 18, color: "#9fb6e2" }}>Full tier list at</span>
              <span style={{ fontSize: 22, fontWeight: 800, color: "#4f8dff" }}>wrtruemeta.com</span>
            </div>
          </div>
        </div>
      </div>
    ),
    {
      width: 1200,
      height: 630,
      headers: {
        // The board changes when the data refreshes, i.e. every few days.
        "Cache-Control": "public, max-age=3600",
        "Content-Disposition": "inline",
      },
    },
  );
}
