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
 * toggles. The background is the SITE's background (ionia2.jpg with the same
 * overlay recipe the layout uses), so the card reads as a piece of the site
 * rather than as one champion's poster.
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

const TIER_TEXT: Record<string, string> = {
  GOD: "#ff9a52", S: "#ff9a52", A: "#ffd45a", B: "#5b9dff", C: "#9aa2b6", Ass: "#6a7286",
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

/** The site's background art (public/ionia2.jpg, 1295x729 -- almost the
 *  card's own aspect), inlined once per process like the logo. */
let BG_URI: string | null | undefined;
async function backgroundUri(): Promise<string | null> {
  if (BG_URI !== undefined) return BG_URI;
  try {
    const buf = await readFile(path.join(PUBLIC_DIR, "ionia2.jpg"));
    const jpg = await sharp(buf)
      .resize(1200, 630, { fit: "cover", position: "centre" })
      .jpeg({ quality: 74 })
      .toBuffer();
    BG_URI = `data:image/jpeg;base64,${jpg.toString("base64")}`;
  } catch {
    BG_URI = null;
  }
  return BG_URI;
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

  const shownChamps = rows.flatMap((r) => r.shown);
  const [logo, background, ...icons] = await Promise.all([
    logoUri(),
    backgroundUri(),
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
        {background && <img src={background} width={1200} height={630}
                            style={{ position: "absolute", top: 0, left: 0 }} />}
        {/* The site layout's own overlay recipe (dark wash + corner vignette),
            weighted a little heavier because the card is dense with content. */}
        <div style={{
          position: "absolute", top: 0, left: 0, width: 1200, height: 630, display: "flex",
          background: "linear-gradient(180deg, rgba(7,10,18,0.62) 0%, rgba(7,10,18,0.68) 45%, rgba(7,10,18,0.74) 100%)",
        }} />
        <div style={{
          position: "absolute", top: 0, left: 0, width: 1200, height: 630, display: "flex",
          background: "radial-gradient(125% 105% at 50% 45%, rgba(3,5,11,0) 55%, rgba(3,5,11,0.42) 88%, rgba(3,5,11,0.62) 100%)",
        }} />
        <div style={{
          position: "absolute", top: 0, left: 0, width: 1200, height: 5, display: "flex",
          background: "linear-gradient(90deg, #4f8dff 0%, #7fd6ff 45%, #ffd76e 100%)",
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
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 16, flexGrow: 1 }}>
            {rows.map((row) => {
              const style = TIER_STYLE[row.tier] ?? TIER_STYLE.C;
              const wrColor = TIER_TEXT[row.tier] ?? "#9aa2b6";
              return (
                <div key={row.tier} style={{
                  display: "flex", alignItems: "center", gap: 14,
                  background: "rgba(10,14,24,0.72)", border: "1px solid rgba(255,255,255,0.09)",
                  borderRadius: 18, padding: "6px 14px", flexGrow: 1,
                }}>
                  <div style={{
                    display: "flex", alignItems: "center", justifyContent: "center",
                    width: 58, height: 42, borderRadius: 12, background: style.bg,
                    fontSize: tierLabel(row.tier as (typeof TIER_ORDER)[number]).length > 1 ? 19 : 23,
                    fontWeight: 900, color: style.fg, letterSpacing: "0.02em", flexShrink: 0,
                    boxShadow: "0 2px 10px rgba(0,0,0,0.45)",
                  }}>
                    {tierLabel(row.tier as (typeof TIER_ORDER)[number])}
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "nowrap" }}>
                    {row.shown.map((c) => {
                      const icon = iconBySlug.get(c.slug);
                      return (
                        <div key={c.slug} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
                          {icon ? (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img src={icon} width={42} height={42}
                                 style={{ borderRadius: 10, border: "1px solid rgba(255,255,255,0.28)" }} />
                          ) : (
                            <div style={{
                              display: "flex", width: 42, height: 42, borderRadius: 10,
                              alignItems: "center", justifyContent: "center",
                              background: "rgba(255,255,255,0.09)", border: "1px solid rgba(255,255,255,0.22)",
                              fontSize: 14, fontWeight: 800, color: "#9fb6e2",
                            }}>
                              {c.name.slice(0, 2)}
                            </div>
                          )}
                          <div style={{ display: "flex", fontSize: 11, fontWeight: 700, color: wrColor }}>
                            {c.wr.toFixed(1)}%
                          </div>
                        </div>
                      );
                    })}
                    {row.extra > 0 && (
                      <div style={{
                        display: "flex", height: 42, alignItems: "center", justifyContent: "center",
                        borderRadius: 10, padding: "0 10px", marginBottom: 15,
                        background: "rgba(255,255,255,0.07)", border: "1px solid rgba(255,255,255,0.16)",
                        fontSize: 15, fontWeight: 800, color: "#9fb6e2",
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
