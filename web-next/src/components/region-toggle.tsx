"use client";

export const REGIONS = ["EU", "NA", "CN"] as const;
/** "Global" is not a server; it's the combined EU+CN view (tier list only). */
export type Region = (typeof REGIONS)[number] | "Global";

/** Regions/views we currently have data for. NA joined 2026-08-08; its
 *  collection is still running, so it covers fewer champions than EU and the
 *  pages that show it say which ones are missing rather than implying a
 *  champion has no players. */
export const REGIONS_WITH_DATA: Region[] = ["EU", "NA", "CN", "Global"];

/**
 * Resolve a `?region=` query value to a Region, or null.
 *
 * The region tabs are client state seeded by a build-time `initialRegion`, so
 * the server-rendered HTML is deterministic and a crawler always gets one
 * known ranking. That is deliberate, and it is also why `?region=NA` did
 * nothing: nothing ever read the URL. Reading it in an effect after mount
 * keeps the prerendered shell exactly as it was while making shared links
 * land where they say they do.
 *
 * Deliberately NOT useSearchParams: on a statically rendered page that hook
 * forces a Suspense boundary or the production build fails, and both pages
 * that need this are static on purpose.
 *
 * Case-insensitive, because a link typed by hand says `?region=na`.
 */
export function regionFromQuery(
  search: string, allowed: readonly Region[],
): Region | null {
  const raw = new URLSearchParams(search).get("region");
  if (!raw) return null;
  const want = raw.trim().toLowerCase();
  return allowed.find((r) => r.toLowerCase() === want) ?? null;
}

export function RegionToggle({
  region,
  onChange,
  regions = REGIONS,
}: {
  region: Region;
  onChange: (r: Region) => void;
  regions?: readonly Region[];
}) {
  return (
    <div className="inline-flex items-center gap-3">
      <span className="text-xs font-semibold uppercase tracking-wide text-faint">Region</span>
      {/* liquid-glass, not the flat strip it was: this control decides what
          the whole page shows, and a quiet border on a dark ground was the
          most-missed element on the tier list. */}
      <div className="liquid-glass inline-flex rounded-full p-1">
        {regions.map((r) => {
          const hasData = REGIONS_WITH_DATA.includes(r);
          return (
            <button
              key={r}
              onClick={() => onChange(r)}
              className={`relative rounded-full px-4 py-1.5 text-sm font-semibold transition ${
                region === r ? "bg-accent text-[#07121f]" : "text-muted hover:text-text"
              }`}
            >
              {r}
              {!hasData && (
                <span className="ml-1 text-[0.55rem] font-medium uppercase opacity-70">soon</span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function RegionComingSoon({ region }: { region: Region }) {
  return (
    <div className="glass rounded-2xl p-12 text-center">
      <p className="text-lg font-semibold">{region} data is coming soon</p>
      <p className="mx-auto mt-2 max-w-md text-sm text-muted">
        We&rsquo;re currently tracking <span className="text-text">EU</span>. {region} win rates and
        leaderboards are on the way, check back after an upcoming update.
      </p>
    </div>
  );
}
