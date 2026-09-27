"use client";

import { Fragment, useEffect, useState } from "react";
import type { CollectionState, RegionProgress } from "@/lib/collection";

/**
 * The data-collection strip under the navbar.
 *
 * Three segments, one per region, each with its own track. They are separate
 * bars rather than points on one shared line because the three numbers are
 * not points on one scale: EU, NA and CN are three independent runs that can
 * each be idle, part way through, or finished, and a single continuous
 * timeline would imply an ordering between them that does not exist.
 *
 * It polls only while something is actually running. Between runs the state
 * is three fixed dates, and re-fetching those every few seconds would spend
 * the visitor's battery to tell them nothing.
 */

const REGION_COLOR: Record<string, string> = {
  EU: "#4f8dff",
  NA: "#5ad6a8",
  CN: "#ff6a6a",
};

/** How often to re-read while a run is in flight. */
const POLL_MS = 15_000;

function formatDate(iso: string | null): string {
  if (!iso) return "";
  // Split the parts rather than Date.parse: a bare "2026-09-03" is parsed as
  // UTC midnight, so rendering it in a timezone BEHIND UTC shows the 2nd.
  // The same calendar day has to read the same everywhere.
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!m) return "";
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

/** `short` drops the words a 375px segment has no room for.
 *
 *  At full width three segments share 375px minus gaps, which left NA reading
 *  "Completed Au..." with the date, the part that carries the information,
 *  cut off. Truncating a label is worse than shortening it deliberately. */
function label(r: RegionProgress, short = false): string {
  if (r.status === "running") return `${r.percent}%`;
  if (r.status === "complete") {
    const d = formatDate(r.collectedOn);
    if (!d) return short ? "Done" : "Completed";
    return short ? d : `Completed ${d}`;
  }
  return short ? "Idle" : "Not started";
}

function Segment({ r }: { r: RegionProgress }) {
  const color = REGION_COLOR[r.region] ?? "#8b93a7";
  const running = r.status === "running";
  const done = r.status === "complete";
  // Idle regions take the muted colour rather than their own: a full-strength
  // hue on an empty track reads as "this is happening" at a glance.
  const tint = running || done ? color : "var(--color-muted)";
  return (
    <div className="flex min-w-0 flex-1 flex-col gap-1">
      <div className="flex min-w-0 items-baseline gap-1.5">
        <span
          className="shrink-0 text-[0.68rem] font-bold uppercase tracking-wider"
          style={{ color: tint }}
        >
          {r.region}
        </span>
        <span
          className={`truncate text-[0.68rem] tabular-nums ${
            running ? "font-semibold text-text" : "text-faint"}`}
        >
          <span className="sm:hidden">{label(r, true)}</span>
          <span className="hidden sm:inline">{label(r)}</span>
        </span>
        {running && (
          // The raw count is the first thing to go when space is tight: the
          // percentage already says the same thing.
          <span className="ml-auto hidden shrink-0 text-[0.62rem] tabular-nums text-faint sm:inline">
            {r.done}/{r.total}
          </span>
        )}
      </div>
      <div
        className="h-[3px] w-full overflow-hidden rounded-full bg-white/[0.07]"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={r.percent}
        aria-label={`${r.region} data collection: ${label(r)}`
          + (running ? `, ${r.done} of ${r.total} champions` : "")}
      >
        <div
          className="h-full rounded-full motion-safe:transition-[width] motion-safe:duration-700"
          style={{
            width: `${r.percent}%`,
            background: tint,
            // A finished region should not shout as loudly as a live one.
            opacity: done ? 0.55 : 1,
            boxShadow: running ? `0 0 8px ${color}66` : undefined,
          }}
        />
      </div>
    </div>
  );
}

export function CollectionTimeline() {
  const [state, setState] = useState<CollectionState | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const load = async () => {
      try {
        const res = await fetch("/api/collection", { cache: "no-store" });
        if (!res.ok) return;
        const next = (await res.json()) as CollectionState;
        if (cancelled) return;
        setState(next);
        // Reschedule from the RESPONSE, not a fixed interval: the moment a
        // run finishes the polling stops on its own, and the moment one
        // starts the next tick picks it up.
        if (next.active) timer = setTimeout(load, POLL_MS);
      } catch {
        // Offline or a failed deploy: keep whatever is already on screen
        // rather than collapsing the strip.
      }
    };

    void load();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, []);

  if (!state || state.regions.length === 0) return null;

  return (
    <div className="border-b border-line bg-black/20">
      <div className="mx-auto flex max-w-6xl items-center gap-4 px-5 py-1.5 sm:gap-6">
        <span className="hidden shrink-0 text-[0.6rem] font-bold uppercase tracking-[0.18em] text-faint lg:block">
          Data collection
        </span>
        {state.regions.map((r, i) => (
          // Fragment rather than a wrapper per segment: wrapping each one
          // with its own divider made the first segment narrower than the
          // other two, because only two of the three carried a divider's
          // width inside their flex basis.
          <Fragment key={r.region}>
            {i > 0 && <span className="hidden h-6 w-px shrink-0 bg-line sm:block" />}
            <Segment r={r} />
          </Fragment>
        ))}
      </div>
    </div>
  );
}
