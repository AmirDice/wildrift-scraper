import { readFile } from "node:fs/promises";
import path from "node:path";
import { ImageResponse } from "next/og";
import sharp from "sharp";
import { getChampions, regionBoard, TIER_ORDER, tierLabel, type Champion } from "@/lib/data";
import { getGlobalChampions, getCnChampionsByBracket, CN_META, type CnBracketKey } from "@/lib/cn";
import { CURRENT_PATCH } from "@/lib/patch";

/**
 * The tier list as a shareable 1200x630 card, sibling to the build card:
 * same footer voice, same "download OR unfurl" size.
 *
 * GET /api/tier-card?region=Global|EU|NA|CN&role=Baron|Jungle|Mid|Dragon|Support
 *
 * Both params are validated against closed sets -- nothing caller-supplied is
 * ever fetched. Pool depth and the raw-number toggle are deliberately absent:
 * the card is the canonical full-pool board, not a screenshot of one person's
 * toggles.
 *
 * THE GLASS IS REAL, within Satori's limits. Satori has no backdrop-filter,
 * so translucent panels over a photo normally read as flat tints. But this
 * layout is deterministic: every row's card-space position is computed here
 * before render, which means each panel can contain the PRE-BLURRED
 * background image, absolutely offset by exactly minus its own position and
 * clipped by the panel's rounded corners. What shows through each panel is
 * the true frosted view of what sits behind it -- the same optical trick
 * backdrop-filter performs, done by hand. A specular top edge, a diagonal
 * sheen and a drop shadow finish the material.
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
  GOD: "#ffb37a", S: "#ffb37a", A: "#ffd45a", B: "#8fb7ff", C: "#aeb6ca", Ass: "#8a92a6",
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

/** The site's background art (public/ionia2.jpg), prepared once per process
 *  in the two states the glass needs: the scene itself, and the scene as it
 *  looks THROUGH the glass -- heavily blurred, dimmer but more saturated,
 *  which is the vibrancy trick frosted materials live on. */
let SCENE: { base: string; frost: string } | null | undefined;
async function sceneUris(): Promise<{ base: string; frost: string } | null> {
  if (SCENE !== undefined) return SCENE;
  try {
    const buf = await readFile(path.join(PUBLIC_DIR, "ionia2.jpg"));
    const fitted = sharp(buf).resize(1200, 630, { fit: "cover", position: "centre" });
    const [base, frost] = await Promise.all([
      fitted.clone().modulate({ brightness: 0.85, saturation: 1.12 }).jpeg({ quality: 74 }).toBuffer(),
      fitted.clone()
        .blur(16)
        .modulate({ brightness: 0.9, saturation: 1.12 })
        .jpeg({ quality: 60 })
        .toBuffer(),
    ]);
    SCENE = {
      base: `data:image/jpeg;base64,${base.toString("base64")}`,
      frost: `data:image/jpeg;base64,${frost.toString("base64")}`,
    };
  } catch {
    SCENE = null;
  }
  return SCENE;
}

const MAX_PER_ROW = 17;

// Fixed geometry, so every panel knows its own position and can align its
// slice of the frosted scene. All in card pixels.
const PAD_X = 34;
const ROWS_TOP = 92;
const ROWS_BOTTOM = 586;
const ROW_GAP = 10;
const PANEL_W = 1200 - PAD_X * 2;

/** One frosted panel: the blurred scene aligned to card space, a translucent
 *  ink tint, a diagonal sheen, and a specular top edge. Children render above. */
function GlassPanel({ x, y, w, h, r, frost, children }: {
  x: number; y: number; w: number; h: number; r: number;
  frost: string | null;
  children: React.ReactNode;
}) {
  return (
    <div style={{
      position: "absolute", top: y, left: x, width: w, height: h, display: "flex",
      borderRadius: r, overflow: "hidden",
      border: "1.5px solid rgba(255,255,255,0.45)",
      boxShadow: "0 18px 50px rgba(2,4,10,0.35)",
    }}>
      {frost && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={frost} width={1200} height={630}
             style={{ position: "absolute", top: -y, left: -x }} />
      )}
      <div style={{
        position: "absolute", top: 0, left: 0, width: w, height: h, display: "flex",
        background: "rgba(10,14,24,0.22)",
      }} />
      <div style={{
        position: "absolute", top: 0, left: 0, width: w, height: h, display: "flex",
        background: "rgba(236,242,252,0.12)",
      }} />
      <div style={{
        position: "absolute", top: 0, left: 0, width: w, height: h, display: "flex",
        background: "linear-gradient(118deg, rgba(255,255,255,0.16) 0%, rgba(255,255,255,0.05) 34%, rgba(255,255,255,0) 55%, rgba(255,255,255,0.08) 100%)",
      }} />
      <div style={{
        position: "absolute", top: 0, left: 0, width: w, height: 2, display: "flex",
        background: "linear-gradient(90deg, rgba(255,255,255,0.1), rgba(255,255,255,0.55) 30%, rgba(255,255,255,0.55) 70%, rgba(255,255,255,0.1))",
      }} />
      <div style={{
        position: "absolute", top: 2, left: 2, width: w - 4, height: h - 4, display: "flex",
        borderRadius: r - 3, border: "1px solid rgba(255,255,255,0.14)",
      }} />
      {children}
    </div>
  );
}

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
  const tiers = TIER_ORDER
    .map((tier) => ({ tier, all: buckets[tier] ?? [] }))
    .filter((row) => row.all.length > 0)
    .map((row) => ({ ...row, shown: row.all.slice(0, MAX_PER_ROW), extra: row.all.length - Math.min(row.all.length, MAX_PER_ROW) }));

  // Panel geometry: rows share the band between header and footer equally.
  const n = Math.max(tiers.length, 1);
  const rowH = Math.floor((ROWS_BOTTOM - ROWS_TOP - (n - 1) * ROW_GAP) / n);
  const rows = tiers.map((row, i) => ({ ...row, y: ROWS_TOP + i * (rowH + ROW_GAP) }));

  const shownChamps = rows.flatMap((r) => r.shown);
  const [logo, scene, ...icons] = await Promise.all([
    logoUri(),
    sceneUris(),
    ...shownChamps.map((c) => champIconUri(c.icon)),
  ]);
  const iconBySlug = new Map(shownChamps.map((c, i) => [c.slug, icons[i]]));
  const frost = scene?.frost ?? null;

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
        width: "100%", height: "100%", display: "flex",
        background: "#070a12", fontFamily: "sans-serif", position: "relative",
      }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        {scene && <img src={scene.base} width={1200} height={630}
                       style={{ position: "absolute", top: 0, left: 0 }} />}
        {/* the scene stays bright; just enough floor for the footer text */}
        <div style={{
          position: "absolute", top: 0, left: 0, width: 1200, height: 630, display: "flex",
          background: "linear-gradient(180deg, rgba(7,10,18,0.2) 0%, rgba(7,10,18,0.06) 40%, rgba(7,10,18,0.38) 100%)",
        }} />

        {/* header: floats on the scene, no panel -- glass needs contrast with
            something that is NOT glass to read as a material */}
        <div style={{
          position: "absolute", top: 24, left: PAD_X, width: PANEL_W, height: 44,
          display: "flex", alignItems: "center", justifyContent: "space-between",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
            {logo
              // eslint-disable-next-line @next/next/no-img-element
              ? <img src={logo} height={34} />
              : <div style={{ display: "flex", fontSize: 26, fontWeight: 800, color: "#eef2fb" }}>WRTRUEMETA</div>}
            <div style={{
              display: "flex", fontSize: 25, fontWeight: 800, color: "#eef2fb",
              letterSpacing: "0.01em", textShadow: "0 2px 12px rgba(0,0,0,0.7)",
            }}>
              Tier List
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{
              display: "flex", fontSize: 16, fontWeight: 700, color: "#f5f9ff",
              background: "rgba(10,14,24,0.5)", border: "1px solid rgba(255,255,255,0.45)",
              borderRadius: 999, padding: "5px 14px", boxShadow: "0 6px 18px rgba(2,4,10,0.35)",
            }}>
              {regionLabel}{role ? ` · ${role}` : ""}
            </div>
            {CURRENT_PATCH && (
              <div style={{
                display: "flex", fontSize: 16, fontWeight: 700, color: "#f5f9ff",
                background: "rgba(10,14,24,0.42)", border: "1px solid rgba(255,255,255,0.4)",
                borderRadius: 999, padding: "5px 14px", boxShadow: "0 6px 18px rgba(2,4,10,0.35)",
              }}>
                Patch {CURRENT_PATCH}
              </div>
            )}
          </div>
        </div>

        {/* the frosted tier rows */}
        {rows.map((row) => {
          const style = TIER_STYLE[row.tier] ?? TIER_STYLE.C;
          const wrColor = TIER_TEXT[row.tier] ?? "#aeb6ca";
          return (
            <GlassPanel key={row.tier} x={PAD_X} y={row.y} w={PANEL_W} h={rowH} r={24} frost={frost}>
              <div style={{
                position: "absolute", top: 0, left: 0, width: PANEL_W, height: rowH,
                display: "flex", alignItems: "center", gap: 14, padding: "0 14px",
              }}>
                <div style={{
                  display: "flex", alignItems: "center", justifyContent: "center",
                  width: 58, height: 42, borderRadius: 13, background: style.bg,
                  fontSize: tierLabel(row.tier as (typeof TIER_ORDER)[number]).length > 1 ? 19 : 23,
                  fontWeight: 900, color: style.fg, letterSpacing: "0.02em", flexShrink: 0,
                  border: "1px solid rgba(255,255,255,0.35)",
                  boxShadow: "0 3px 12px rgba(0,0,0,0.45)",
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
                               style={{
                                 borderRadius: 11, border: "1px solid rgba(255,255,255,0.32)",
                                 boxShadow: "0 3px 8px rgba(0,0,0,0.4)",
                               }} />
                        ) : (
                          <div style={{
                            display: "flex", width: 42, height: 42, borderRadius: 11,
                            alignItems: "center", justifyContent: "center",
                            background: "rgba(255,255,255,0.10)", border: "1px solid rgba(255,255,255,0.25)",
                            fontSize: 14, fontWeight: 800, color: "#c9d4ea",
                          }}>
                            {c.name.slice(0, 2)}
                          </div>
                        )}
                        <div style={{
                          display: "flex", fontSize: 11, fontWeight: 700, color: wrColor,
                          textShadow: "0 1px 5px rgba(0,0,0,0.85)",
                        }}>
                          {c.wr.toFixed(1)}%
                        </div>
                      </div>
                    );
                  })}
                  {row.extra > 0 && (
                    <div style={{
                      display: "flex", height: 42, alignItems: "center", justifyContent: "center",
                      borderRadius: 11, padding: "0 10px", marginBottom: 15,
                      background: "rgba(255,255,255,0.10)", border: "1px solid rgba(255,255,255,0.22)",
                      fontSize: 15, fontWeight: 800, color: "#c9d4ea",
                    }}>
                      +{row.extra}
                    </div>
                  )}
                </div>
              </div>
            </GlassPanel>
          );
        })}

        {/* footer */}
        <div style={{
          position: "absolute", top: 596, left: PAD_X, width: PANEL_W,
          display: "flex", alignItems: "center", justifyContent: "space-between",
        }}>
          <div style={{
            display: "flex", fontSize: 15, color: "#aeb9cf", letterSpacing: "0.02em",
            textShadow: "0 1px 6px rgba(0,0,0,0.7)",
          }}>
            {basis}
          </div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8, textShadow: "0 1px 6px rgba(0,0,0,0.7)" }}>
            <span style={{ fontSize: 18, color: "#c3d4f2" }}>Full tier list at</span>
            <span style={{ fontSize: 22, fontWeight: 800, color: "#7fb2ff" }}>wrtruemeta.com</span>
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
