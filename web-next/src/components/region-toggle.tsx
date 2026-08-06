"use client";

export const REGIONS = ["EU", "NA", "CN"] as const;
/** "Global" is not a server; it's the combined EU+CN view (tier list only). */
export type Region = (typeof REGIONS)[number] | "Global";

/** Regions/views we currently have data for. Add "NA" here when collected. */
export const REGIONS_WITH_DATA: Region[] = ["EU", "CN", "Global"];

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
