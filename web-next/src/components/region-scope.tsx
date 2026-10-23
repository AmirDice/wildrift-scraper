"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

/**
 * Which server's numbers a champion page is showing: the EU + NA + CN blend,
 * or one board on its own. One choice for the whole page, so the hero, the
 * charts and the player cards never disagree about where a number came from.
 *
 * The server renders every view, and ForRegion shows the chosen one. That
 * keeps the pages static and the numbers in the HTML for crawlers, at the cost
 * of a few duplicated cards per page. The choice is remembered per browser and
 * can be linked with ?region=eu.
 */
import { REGIONS, REGION_LONG, REGION_LABEL, type Region } from "@/lib/region-labels";

export { REGIONS, REGION_LONG, REGION_LABEL, type Region };

const STORAGE_KEY = "wtm-champion-region";
/** Set once the visitor has used the switch; until then it pulses. */
const SEEN_KEY = "wtm-region-toggle-seen";

type Scope = { region: Region; setRegion: (region: Region) => void; fresh: boolean };
const RegionContext = createContext<Scope | null>(null);

const isRegion = (value: unknown): value is Region => REGIONS.includes(value as Region);

export function RegionProvider({ children }: { children: ReactNode }) {
  const [region, setRegionState] = useState<Region>("global");
  // False on the server and first paint, so the static HTML never pulses
  // for someone who has already found the switch.
  const [fresh, setFresh] = useState(false);

  // After hydration, so the static HTML is always the Global view.
  useEffect(() => {
    let seen = false;
    try { seen = Boolean(localStorage.getItem(SEEN_KEY)); } catch { /* storage blocked */ }
    const pulse = seen ? null : setTimeout(() => setFresh(true), 0);
    let initial: unknown = new URLSearchParams(window.location.search).get("region");
    if (!isRegion(initial)) {
      try { initial = localStorage.getItem(STORAGE_KEY); } catch { /* storage blocked */ }
    }
    if (isRegion(initial) && initial !== "global") {
      // A timer, not requestAnimationFrame: a background tab draws no
      // frames, so a link opened there would sit on Global.
      const timer = setTimeout(() => setRegionState(initial as Region), 0);
      return () => { clearTimeout(timer); if (pulse) clearTimeout(pulse); };
    }
    return () => { if (pulse) clearTimeout(pulse); };
  }, []);

  const setRegion = useCallback((next: Region) => {
    setRegionState(next);
    setFresh(false);
    try {
      localStorage.setItem(STORAGE_KEY, next);
      localStorage.setItem(SEEN_KEY, "1");
    } catch { /* storage blocked */ }
    const url = new URL(window.location.href);
    if (next === "global") url.searchParams.delete("region");
    else url.searchParams.set("region", next);
    window.history.replaceState(null, "", url);
  }, []);

  return <RegionContext.Provider value={{ region, setRegion, fresh }}>{children}</RegionContext.Provider>;
}

/** The page's region, or null outside a RegionProvider (Build Studio etc.). */
export function useRegionScope(): Scope | null {
  return useContext(RegionContext);
}

/** Renders its children only while `region` is the one selected. */
export function ForRegion({ region, children }: { region: Region; children: ReactNode }) {
  const scope = useContext(RegionContext);
  return (scope?.region ?? "global") === region ? <>{children}</> : null;
}

export function RegionToggle({ className = "", available }: { className?: string; available?: Partial<Record<Region, boolean>> }) {
  const scope = useContext(RegionContext);
  if (!scope) return null;
  return (
    <div role="radiogroup" aria-label="Which server's data to show" data-fresh={scope.fresh || undefined}
      className={`region-toggle inline-flex shrink-0 items-center gap-0.5 rounded-lg border border-accent/40 bg-black/25 p-0.5 ${className}`}>
      {REGIONS.map((region) => {
        const active = scope.region === region;
        const disabled = available ? available[region] === false : false;
        return (
          <button key={region} type="button" role="radio" aria-checked={active} disabled={disabled}
            title={disabled ? `No ${REGION_LONG[region]} board for this champion yet` : `Show ${REGION_LONG[region]} data`}
            onClick={() => scope.setRegion(region)}
            className={`rounded-md px-2.5 py-1.5 text-xs font-semibold transition disabled:cursor-not-allowed disabled:opacity-35 ${active ? "bg-accent/20 text-accent ring-1 ring-accent/25" : "text-muted hover:text-text"}`}>
            {REGION_LABEL[region]}
          </button>
        );
      })}
    </div>
  );
}
