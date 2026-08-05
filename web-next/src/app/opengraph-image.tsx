import { ImageResponse } from "next/og";
import { getChampions } from "@/lib/data";

/**
 * The card Discord, Slack and X render when someone pastes a wrtruemeta link.
 *
 * There was no image at all before this, which is why a shared link showed a
 * bare line of text: the twitter card was already declared `summary_large_image`
 * and there was no large image to put in it.
 *
 * Generated rather than a checked-in PNG so the champion count stays true
 * without anyone remembering to re-export it, and so the wording only has to be
 * right in one place.
 */
export const alt = "WrTrueMeta: real Wild Rift win rates and build tools";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default async function Image() {
  let champions = 0;
  try {
    champions = getChampions().length;
  } catch {
    // The card must render even if the data layer is unavailable; a missing
    // number is a worse card, a thrown error is no card at all.
  }

  return new ImageResponse(
    (
      <div
        style={{
          height: "100%",
          width: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          background: "linear-gradient(135deg, #0a0e1a 0%, #131a2e 55%, #0d1424 100%)",
          padding: "72px 80px",
          fontFamily: "sans-serif",
        }}
      >
        <div style={{ display: "flex", flexDirection: "column" }}>
          <div
            style={{
              display: "flex",
              fontSize: 78,
              fontWeight: 800,
              color: "#f2f5ff",
              letterSpacing: "-0.02em",
            }}
          >
            WrTrueMeta
          </div>
          <div
            style={{
              display: "flex",
              marginTop: 18,
              fontSize: 38,
              lineHeight: 1.3,
              color: "#9fb0d0",
              maxWidth: 900,
            }}
          >
            Real Wild Rift win rates from the top 50 players on every champion,
            plus build and counter tools.
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
          {[
            champions ? `${champions} champions` : "Every champion",
            "Live win rates",
            "Build Studio",
            "Build vs Enemy Team",
          ].map((label) => (
            <div
              key={label}
              style={{
                display: "flex",
                border: "2px solid rgba(120, 190, 255, 0.35)",
                background: "rgba(120, 190, 255, 0.10)",
                color: "#8fd0ff",
                borderRadius: 999,
                padding: "12px 26px",
                fontSize: 26,
                fontWeight: 700,
              }}
            >
              {label}
            </div>
          ))}
        </div>
      </div>
    ),
    size,
  );
}
