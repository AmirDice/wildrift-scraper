import { readFile } from "node:fs/promises";
import path from "node:path";
import { ImageResponse } from "next/og";
import sharp from "sharp";
import { kvGetJson } from "@/lib/kv";
import { getChampion } from "@/lib/data";
import type { SharedBuild } from "@/app/api/share-build/route";
import engineData from "@/data/engine.json";
import skinsData from "@/data/champion_skins.json";

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
  runes?: Record<string, { icon?: string; type?: string | number; tree?: string }>;
};

/**
 * Keystone / minors / flex derived from the rune CATALOGUE, never from array
 * position. The page structure is fixed (1 keystone, 3 minors from one tree,
 * 1 flex from another) and the catalogue knows each rune's type and tree, so
 * the card labels correctly however the payload happens to be ordered. The
 * first version trusted position and a scrambled test payload promptly tagged
 * a Resolve minor as the flex.
 */
function classifyRunes(names: string[]) {
  const meta = names.map((name) => ({
    name,
    type: DATA.runes?.[name]?.type,
    tree: DATA.runes?.[name]?.tree ?? "",
  }));
  const keystone = meta.find((m) => m.type === "Keystone") ?? null;
  const rest = meta.filter((m) => m !== keystone);
  const counts = new Map<string, number>();
  for (const m of rest) counts.set(m.tree, (counts.get(m.tree) ?? 0) + 1);
  let majorityTree = "";
  let best = 0;
  for (const [tree, n] of counts) if (n > best) { best = n; majorityTree = tree; }
  const minors = rest.filter((m) => m.tree === majorityTree);
  const flex = rest.find((m) => m.tree !== majorityTree) ?? null;
  return {
    ordered: [
      ...(keystone ? [{ ...keystone, role: "keystone" as const }] : []),
      ...minors.map((m) => ({ ...m, role: "minor" as const })),
      ...(flex ? [{ ...flex, role: "flex" as const }] : []),
    ],
    minorTree: majorityTree,
  };
}
const itemName = (slug: string) => DATA.items?.[slug]?.name ?? slug;

/** Mirrors SUMMONERS in web/build_advisor.py: a CLOSED set, because the card
 *  fetches these icons server-side and must never fetch a caller-supplied URL. */
const DD_SPELL = "https://ddragon.leagueoflegends.com/cdn/16.11.1/img/spell";
const SUMMONER_DD: Record<string, string> = {
  Flash: "SummonerFlash", Ignite: "SummonerDot", Ghost: "SummonerHaste",
  Exhaust: "SummonerExhaust", Smite: "SummonerSmite", Cleanse: "SummonerBoost",
  Heal: "SummonerHeal", Barrier: "SummonerBarrier",
};

async function spellIconUri(name: string): Promise<string | null> {
  const dd = SUMMONER_DD[name];
  if (!dd) return null;
  try {
    const res = await fetch(`${DD_SPELL}/${dd}.png`);
    if (!res.ok) return null;
    const buf = Buffer.from(await res.arrayBuffer());
    const png = await sharp(buf).resize(80, 80).png().toBuffer();
    return `data:image/png;base64,${png.toString("base64")}`;
  } catch {
    return null;
  }
}

const BIAS_LABEL: Record<string, string> = {
  max_durability: "Maximum Durability",
  durability: "Durability Leaning",
  damage: "Damage Leaning",
  max_damage: "Maximum Damage",
};

const PUBLIC_DIR = path.join(process.cwd(), "public");

const SKINS = skinsData as Record<string, { key: string; skins: { num: number; name: string }[] }>;

/** The site's actual wordmark (public/logo.png, 1549x217), inlined once per
 *  process: it never changes between renders, so re-reading it per card would
 *  be waste. */
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

/** Local item webp -> png data URI. Null when the art is missing: the card
 *  then renders a lettered tile rather than a broken image. */
async function itemPng(slug: string): Promise<string | null> {
  for (const ext of ["webp", "png"]) {
    try {
      const buf = await readFile(path.join(PUBLIC_DIR, "items", `${slug}.${ext}`));
      const png = await sharp(buf).resize(96, 96).png().toBuffer();
      return `data:image/png;base64,${png.toString("base64")}`;
    } catch {
      /* try the next extension */
    }
  }
  return null;
}

/** Rune icon (external PNG) -> inlined data URI, resized. Null on any failure:
 *  the chip then renders text-only rather than a broken image. */
async function runeIconUri(name: string): Promise<string | null> {
  const src = DATA.runes?.[name]?.icon;
  if (!src || !src.startsWith("http")) return null;
  try {
    const res = await fetch(src);
    if (!res.ok) return null;
    const buf = Buffer.from(await res.arrayBuffer());
    const png = await sharp(buf).resize(44, 44).png().toBuffer();
    return `data:image/png;base64,${png.toString("base64")}`;
  } catch {
    return null;
  }
}

/**
 * Full-bleed background: the ddragon SPLASH (1215x717 cinematic horizontal),
 * for the champion's chosen skin. Cover-cropping 1215x717 into 1200x630 trims
 * only ~11% of the height, and "attention" spends that trim away from the
 * subject, so the composition survives intact for the whole roster. Skin
 * numbers are validated against the catalogue; anything unknown is the base
 * skin. Champions absent from ddragon (Wild Rift exclusives) fall back to
 * whatever art the site stores for them.
 */
async function splashUri(slug: string, skin: number, fallback: string | undefined): Promise<string | null> {
  const entry = SKINS[slug];
  const num = entry?.skins.some((k) => k.num === skin) ? skin : 0;
  const url = entry
    ? `https://ddragon.leagueoflegends.com/cdn/img/champion/splash/${entry.key}_${num}.jpg`
    : fallback;
  if (!url) return null;
  try {
    const buf = url.startsWith("/")
      ? await readFile(path.join(PUBLIC_DIR, url.slice(1)))
      : await (async () => {
          const res = await fetch(url);
          if (!res.ok) throw new Error(String(res.status));
          return Buffer.from(await res.arrayBuffer());
        })();
    const jpg = await sharp(buf)
      .resize(1200, 630, { fit: "cover", position: "attention" })
      .jpeg({ quality: 76 })
      .toBuffer();
    return `data:image/jpeg;base64,${jpg.toString("base64")}`;
  } catch {
    return null;
  }
}

const slugRe = /[^a-z0-9-]/g;
const textRe = /[^A-Za-z0-9 .:'&_-]/g;

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
      bootsUpgradeAfter: Number.isInteger(decoded.bootsUpgradeAfter)
        && (decoded.bootsUpgradeAfter as number) >= 0 && (decoded.bootsUpgradeAfter as number) <= 5
        ? (decoded.bootsUpgradeAfter as number) : undefined,
      runes: list(decoded.runes, 6, (x) => t(x)),
      summoners: list(decoded.summoners, 2, (x) => t(x, 12)).filter((n) => n in SUMMONER_DD),
      skin: Number.isInteger(decoded.skin) && (decoded.skin as number) >= 0 && (decoded.skin as number) <= 99
        ? (decoded.skin as number) : 0,
      player: t(decoded.player, 24) || undefined,
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
  const [logo, splash, champIcon, ...itemArt] = await Promise.all([
    logoUri(),
    splashUri(build.championSlug, build.skin ?? 0, champ?.splash),
    champ?.icon && champ.icon.startsWith("http") ? champ.icon : null,
    ...build.items.map(itemPng),
  ]);
  const bootsFinal = build.bootsUpgrade || build.boots || "";
  const spells = build.summoners ?? [];
  const runes = classifyRunes(build.runes);
  const [bootsArt, spellArtA, spellArtB, ...runeArt] = await Promise.all([
    bootsFinal ? itemPng(bootsFinal) : Promise.resolve(null),
    spells[0] ? spellIconUri(spells[0]) : Promise.resolve(null),
    spells[1] ? spellIconUri(spells[1]) : Promise.resolve(null),
    ...runes.ordered.map((r) => runeIconUri(r.name)),
  ]);
  const spellArt = [spellArtA, spellArtB];
  const biasLabel = build.bias ? BIAS_LABEL[build.bias] : null;
  // A Lab card is the player's own work: CORE tags describe an optimised
  // purchase order it does not have, and "generated" would claim authorship
  // the site does not deserve.
  const isCustom = build.playstyle === "custom";
  // The boots label carries the model's upgrade timing when the build has one:
  // "T3 AFTER 2ND" mirrors the strip on the site, "T2 ALL GAME" is the
  // deliberate skip, and a Lab card keeps the plain label.
  const ORDS = ["", "1ST", "2ND", "3RD", "4TH", "5TH"];
  const upAfter = build.bootsUpgradeAfter;
  const bootsTag = build.bootsUpgrade && upAfter && upAfter >= 1
    ? `T3 AFTER ${ORDS[upAfter]}`
    : !build.bootsUpgrade && upAfter === 0
      ? "T2 ALL GAME"
      : "BOOTS";

  return new ImageResponse(
    (
      <div style={{
        width: "100%", height: "100%", display: "flex", flexDirection: "column",
        background: "#070a12", fontFamily: "sans-serif", position: "relative",
      }}>
        {/* Full-bleed cinematic splash, washed just enough: a left gradient
            under the text column, a slim top band under the brand row, a
            bottom band under runes and footer. The art keeps the right side. */}
        {splash && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={splash} width={1200} height={630}
               style={{ position: "absolute", top: 0, left: 0 }} />
        )}
        <div style={{
          position: "absolute", top: 0, left: 0, width: 1200, height: 630, display: "flex",
          background: "linear-gradient(95deg, rgba(5,8,15,0.93) 0%, rgba(5,8,15,0.78) 36%, rgba(7,10,18,0.28) 66%, rgba(7,10,18,0.12) 100%)",
        }} />
        <div style={{
          position: "absolute", top: 0, left: 0, width: 1200, height: 150, display: "flex",
          background: "linear-gradient(180deg, rgba(5,8,15,0.72) 0%, rgba(5,8,15,0) 100%)",
        }} />
        <div style={{
          position: "absolute", top: 400, left: 0, width: 1200, height: 230, display: "flex",
          background: "linear-gradient(0deg, rgba(3,5,11,0.9) 0%, rgba(3,5,11,0.45) 55%, rgba(3,5,11,0) 100%)",
        }} />

        {/* the signature: a hairline accent-to-gold gradient across the top.
            Painted AFTER the splash and its seals so it spans the full width;
            as an earlier sibling the top seal covered its right half. */}
        <div style={{
          position: "absolute", top: 0, left: 0, width: 1200, height: 5, display: "flex",
          background: "linear-gradient(90deg, #4f8dff 0%, #7fd6ff 45%, #ffd76e 100%)",
        }} />
        <div style={{
          position: "relative", display: "flex", flexDirection: "column",
          height: "100%", padding: "44px 56px 36px",
        }}>
          {/* brand */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            {logo ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={logo} height={34} width={Math.round(34 * (1549 / 217))} />
            ) : (
              <div style={{ display: "flex", fontSize: 26, fontWeight: 800, letterSpacing: "0.14em" }}>
                <span style={{ color: "#4f8dff" }}>WRTRUE</span>
                <span style={{ color: "#eef2fb" }}>META</span>
              </div>
            )}
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
            display: "flex", alignItems: "flex-start", gap: 18, marginTop: 40,
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
                {i < 3 && !isCustom && (
                  <div style={{ display: "flex", fontSize: 12, fontWeight: 800, color: "#7fb2ff", marginTop: 5, letterSpacing: "0.1em" }}>
                    CORE
                  </div>
                )}
              </div>
            ))}
            {bootsArt && (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", marginLeft: 6 }}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={bootsArt} width={72} height={72}
                     style={{ borderRadius: 14, border: "2px solid rgba(255,215,110,0.55)" }} />
                <div style={{ display: "flex", fontSize: 12, fontWeight: 800, color: "#ffd76e", marginTop: 4, letterSpacing: "0.08em", whiteSpace: "nowrap" }}>
                  {bootsTag}
                </div>
              </div>
            )}
            {spellArt.some(Boolean) && (
              <div style={{
                display: "flex", flexDirection: "column", alignItems: "center", marginLeft: 10,
                paddingLeft: 18, borderLeft: "2px solid rgba(255,255,255,0.12)",
              }}>
                <div style={{ display: "flex", gap: 8 }}>
                  {spellArt.map((art, i) => art && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img key={i} src={art} width={56} height={56}
                         style={{ borderRadius: 12, border: "2px solid rgba(127,214,255,0.5)" }} />
                  ))}
                </div>
                <div style={{ display: "flex", fontSize: 13, fontWeight: 800, color: "#7fd6ff", marginTop: 5, letterSpacing: "0.08em" }}>
                  SPELLS
                </div>
              </div>
            )}
          </div>

          {/* runes */}
          {runes.ordered.length > 0 && (
            <div style={{ display: "flex", gap: 10, marginTop: 22, flexWrap: "wrap", maxWidth: 1000, alignItems: "center" }}>
              {runes.ordered.map((rune, i) => {
                const isKeystone = rune.role === "keystone";
                const isFlex = rune.role === "flex";
                return (
                  <div key={rune.name} style={{
                    display: "flex", alignItems: "center", gap: 8,
                    fontSize: isKeystone ? 21 : 19, fontWeight: 700,
                    color: isKeystone ? "#f4f7ff" : "#d9e2f5",
                    background: isKeystone ? "rgba(79,141,255,0.16)" : "rgba(255,255,255,0.07)",
                    border: isKeystone ? "2px solid rgba(79,141,255,0.6)"
                      : isFlex ? "2px solid rgba(255,215,110,0.4)"
                      : "2px solid rgba(255,255,255,0.14)",
                    borderRadius: 999, padding: runeArt[i] ? "4px 18px 4px 6px" : "6px 18px",
                  }}>
                    {runeArt[i] && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={runeArt[i]!} width={isKeystone ? 40 : 34} height={isKeystone ? 40 : 34}
                           style={{ borderRadius: 999, background: "rgba(0,0,0,0.35)" }} />
                    )}
                    {rune.name}
                    {isFlex && (
                      <span style={{ fontSize: 13, fontWeight: 800, color: "#ffd76e", letterSpacing: "0.06em" }}>
                        FLEX
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* footer */}
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            marginTop: "auto",
          }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
              {build.player && (
                <div style={{ display: "flex", fontSize: 20, color: "#8b93a7" }}>
                  Built by <span style={{ color: "#eef2fb", fontWeight: 800, marginLeft: 7 }}>{build.player}</span>
                </div>
              )}
              <div style={{ display: "flex", fontSize: 15, color: "#7f8a9e", letterSpacing: "0.02em" }}>
                {isCustom
                  ? "Built by hand in the WRTrueMeta Custom Lab"
                  : "Generated & optimized by WRTrueMeta Build Studio"}
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
              <span style={{ fontSize: 20, color: "#9fb6e2" }}>Generate yours at</span>
              <span style={{ fontSize: 24, fontWeight: 800, color: "#4f8dff" }}>wrtruemeta.com</span>
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
