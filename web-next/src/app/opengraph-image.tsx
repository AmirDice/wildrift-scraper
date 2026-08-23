import { readFile } from "node:fs/promises";
import path from "node:path";
import { ImageResponse } from "next/og";
import { CURRENT_PATCH } from "@/lib/patch";
import releases from "@/data/champion_releases.json";
import roster from "@/data/roster.json";

/**
 * The card Discord, Slack and X render when someone pastes a wrtruemeta link.
 *
 * Generated rather than a checked-in PNG so it cannot go stale: the champion
 * count, the patch number and the champion shown all come from the data, so
 * nobody has to remember to re-export anything.
 *
 * The art is the NEWEST RELEASED CHAMPION, read from champion_releases.json,
 * so the card refreshes itself every time Riot ships one. That champion is
 * usually too new to have a leaderboard entry, so the portrait cannot come from
 * site.json and is built from Riot's own CDN by name instead.
 *
 * Satori supports flexbox and a subset of CSS only: no grid, and every element
 * with more than one child needs an explicit `display: flex`.
 */
export const alt = "WrTrueMeta: real Wild Rift win rates and build tools";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const ACCENT = "#78beff";

/** Riot's asset key for a champion. Their CDN drops punctuation and spaces,
 *  and a few names differ outright, so the irregulars are listed. */
function assetKey(name: string): string {
  const irregular: Record<string, string> = {
    Wukong: "MonkeyKing",
    "Nunu & Willump": "Nunu",
    "Renata Glasc": "Renata",
    Fiddlesticks: "Fiddlesticks",
  };
  if (irregular[name]) return irregular[name];
  return name.replace(/[^A-Za-z]/g, "");
}

/** Both images are inlined as data URIs rather than handed to Satori as URLs.
 *  Satori fetches remote images itself and fails SILENTLY when it cannot, which
 *  is how this card rendered with no art at all and no error: a 200 response
 *  and a missing background. Fetching here means a failure is visible and the
 *  logo works the same way in production as in dev, with no origin to guess. */
async function dataUri(fetchIt: () => Promise<ArrayBuffer | Buffer>, mime: string) {
  try {
    const bytes = await fetchIt();
    const b64 = Buffer.from(bytes as ArrayBuffer).toString("base64");
    return `data:${mime};base64,${b64}`;
  } catch (err) {
    console.error("[og] asset inline failed:", err instanceof Error ? err.message : err);
    return null;
  }
}

/** The most recently released champion, by release date. */
function newestChampion(): { name: string; patch: string } | null {
  const entries = Object.entries(
    (releases as { releases?: Record<string, { patch?: string; releasedAt?: string }> }).releases ?? {},
  );
  let best: { name: string; patch: string; at: string } | null = null;
  for (const [name, value] of entries) {
    const at = value?.releasedAt ?? "";
    if (!at) continue;
    if (!best || at > best.at) best = { name, patch: value?.patch ?? "", at };
  }
  return best ? { name: best.name, patch: best.patch } : null;
}

export default async function Image() {
  // The ROSTER, not the leaderboard export. A champion released this patch has
  // no win-rate rows yet, so site.json lagged the real count by one and the card
  // undersold the coverage.
  const champions = roster && typeof roster === "object"
    ? Object.keys(roster as Record<string, unknown>).length
    : 0;
  const newest = newestChampion();
  // The LANDSCAPE splash (1215x717), not the portrait loading art: it nearly
  // matches the 1200x630 card, so it can sit full-bleed behind the text
  // instead of being boxed into a side panel.
  const splash = newest
    ? await dataUri(
        async () =>
          fetch(
            `https://ddragon.leagueoflegends.com/cdn/img/champion/splash/${assetKey(newest.name)}_0.jpg`,
            // Riot's CDN answers 403 to a bare server-side fetch. A normal
            // browser User-Agent is all it wants.
            { headers: { "User-Agent": "Mozilla/5.0 (compatible; WrTrueMeta/1.0)" } },
          ).then((r) => {
            if (!r.ok) throw new Error(String(r.status));
            return r.arrayBuffer();
          }),
        "image/jpeg",
      )
    : null;
  const logo = await dataUri(
    () => readFile(path.join(process.cwd(), "public", "logo.png")),
    "image/png",
  );

  return new ImageResponse(
    (
      <div
        style={{
          height: "100%",
          width: "100%",
          display: "flex",
          position: "relative",
          // The art goes in as a BACKGROUND, not an <img>. Satori will not
          // position an image element, so an absolutely placed <img> renders as
          // nothing and the card silently loses its background.
          backgroundImage: splash
            ? `url(${splash})`
            : "linear-gradient(135deg, #0a0e1a 0%, #131a2e 55%, #0d1424 100%)",
          backgroundSize: "1200px 630px",
          backgroundPosition: "center",
          fontFamily: "sans-serif",
        }}
      >
        {/* The splash fills the whole card, then a scrim from the left keeps
            the copy readable over it. Art first in the tree so everything
            after it paints on top. */}
        {splash ? (
          <div
            style={{
              display: "flex",
              position: "absolute",
              top: 0,
              left: 0,
              width: 1200,
              height: 630,
              background:
                "linear-gradient(90deg, #08101f 0%, rgba(8,16,31,0.94) 42%, rgba(8,16,31,0.55) 68%, rgba(8,16,31,0.25) 100%)",
            }}
          />
        ) : null}

        {/* The words, over the art. */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
            padding: "68px 0 68px 76px",
            width: 760,
          }}
        >
          <div style={{ display: "flex", flexDirection: "column" }}>
            {/* The real logo, with the wordmark as a fallback so a missing
                asset costs the branding rather than the whole card. */}
            {logo ? (
              <div style={{ display: "flex" }}>
                <img src={logo} height={92} style={{ objectFit: "contain" }} alt="" />
              </div>
            ) : (
              <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                <div style={{ display: "flex", width: 10, height: 54, background: ACCENT, borderRadius: 999 }} />
                <div
                  style={{
                    display: "flex",
                    fontSize: 74,
                    fontWeight: 800,
                    color: "#f2f5ff",
                    letterSpacing: "-0.02em",
                  }}
                >
                  WrTrueMeta
                </div>
              </div>
            )}
            <div
              style={{
                display: "flex",
                marginTop: 20,
                fontSize: 34,
                lineHeight: 1.35,
                color: "#9fb0d0",
                maxWidth: 660,
              }}
            >
              Real Wild Rift win rates from the top 50 players on every champion,
              plus build and counter tools.
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              {[
                champions ? `${champions} champions` : "Every champion",
                "Live win rates",
                "Build Studio",
              ].map((label) => (
                <div
                  key={label}
                  style={{
                    display: "flex",
                    border: `2px solid rgba(120, 190, 255, 0.35)`,
                    background: "rgba(120, 190, 255, 0.10)",
                    color: "#8fd0ff",
                    borderRadius: 999,
                    padding: "10px 24px",
                    fontSize: 25,
                    fontWeight: 700,
                  }}
                >
                  {label}
                </div>
              ))}
            </div>
            {CURRENT_PATCH ? (
              <div style={{ display: "flex", fontSize: 24, color: "#6f80a0", fontWeight: 600 }}>
                Patch {CURRENT_PATCH}
              </div>
            ) : null}
          </div>
        </div>

        {/* Who the art is, bottom right, so the card always says it. */}
        {newest ? (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "flex-end",
              position: "absolute",
              right: 60,
              bottom: 56,
            }}
          >
            <div
              style={{
                display: "flex",
                background: ACCENT,
                color: "#08101f",
                borderRadius: 8,
                padding: "6px 14px",
                fontSize: 21,
                fontWeight: 800,
                letterSpacing: "0.08em",
              }}
            >
              NEWEST CHAMPION
            </div>
            <div
              style={{
                display: "flex",
                marginTop: 10,
                fontSize: 44,
                fontWeight: 800,
                color: "#ffffff",
              }}
            >
              {newest.name}
            </div>
          </div>
        ) : null}
      </div>
    ),
    size,
  );
}
