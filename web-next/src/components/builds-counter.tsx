"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Live "builds generated" figure.
 *
 * Every generation increments a server-side counter; this reads the total back
 * from /api/stats, which is cached at the edge for an hour. So the number does
 * move on its own, but a busy home page never costs more than one store read
 * per hour.
 */

// The home page renders this figure twice (hero pill and stats grid), and the
// build page renders it again. One module-level promise means one request per
// refresh window, not one per caller.
//
// The memo is time-boxed rather than permanent: the figure now refreshes while
// someone is sitting on the build page, and a promise cached for the life of
// the tab would have made the interval below do nothing at all.
const REFRESH_MS = 60_000;
let pending: Promise<number | null> | null = null;
let pendingAt = 0;

function fetchTotal(): Promise<number | null> {
  const now = Date.now();
  if (pending && now - pendingAt < REFRESH_MS) return pending;
  pendingAt = now;
  pending = (async () => {
    try {
      const res = await fetch("/api/stats");
      if (!res.ok) return null;
      const data = (await res.json()) as { buildsGenerated?: number };
      return typeof data.buildsGenerated === "number" ? data.buildsGenerated : null;
    } catch {
      return null;
    }
  })();
  return pending;
}

function useBuildsGenerated(): number | null {
  const [total, setTotal] = useState<number | null>(null);
  useEffect(() => {
    let cancelled = false;
    const load = () => {
      void fetchTotal().then((value) => {
        if (!cancelled && value != null) setTotal(value);
      });
    };
    load();
    // Only while the tab is actually being looked at. A background tab polling
    // a counter nobody can see is pure waste, and browsers throttle it into
    // bursts on return anyway.
    const id = setInterval(() => {
      if (document.visibilityState === "visible") load();
    }, REFRESH_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible") load();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);
  return total;
}

/**
 * Counts from 0 up to `target` once, easing out so it decelerates into the
 * real figure instead of stopping dead.
 *
 * Anyone who has asked their system not to animate gets the final number
 * immediately -- a number sprinting upward is exactly the motion that setting
 * exists to suppress.
 */
function useCountUp(target: number | null, durationMs = 1400): number {
  const [value, setValue] = useState(0);
  const frame = useRef<number | null>(null);
  // What is on screen right now, so a refresh can animate from it rather than
  // from zero. Mirrored in its own effect rather than assigned during render:
  // writing a ref while rendering is exactly what react-hooks/refs forbids, and
  // the animation only reads this at the moment a new target arrives.
  const shown = useRef(0);
  useEffect(() => {
    shown.current = value;
  }, [value]);

  useEffect(() => {
    if (target == null) return;

    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduced || target <= 0) {
      // Deferred by a frame rather than set here: a synchronous setState inside
      // an effect costs a second render pass on every refresh tick.
      frame.current = requestAnimationFrame(() => setValue(target));
      return () => {
        if (frame.current != null) cancelAnimationFrame(frame.current);
      };
    }

    // Animate from what is displayed, not from zero. On first load that IS
    // zero, so the original count-up is unchanged; on the minute refresh it
    // ticks the last few digits up instead of resetting to nothing and
    // sprinting back, which would read as the site losing its numbers.
    const from = shown.current;
    if (from === target) return;

    const start = performance.now();
    const tick = (now: number) => {
      const progress = Math.min(1, (now - start) / durationMs);
      // easeOutCubic
      const eased = 1 - Math.pow(1 - progress, 3);
      setValue(Math.round(from + (target - from) * eased));
      if (progress < 1) frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);

    return () => {
      if (frame.current != null) cancelAnimationFrame(frame.current);
    };
  }, [target, durationMs]);

  return value;
}

/** Plain figure for the stats grid. Renders the fallback until the real one lands. */
export function BuildsGeneratedCount({ fallback = "-" }: { fallback?: string }) {
  const total = useBuildsGenerated();
  const shown = useCountUp(total);
  return <>{total == null ? fallback : shown.toLocaleString()}</>;
}

/** Same figure, animated, with a live dot, for the hero strip. */
export function BuildsGeneratedPill() {
  const total = useBuildsGenerated();
  const shown = useCountUp(total);

  if (total == null || total < 1) return null;

  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-accent/30 bg-accent/10 px-3.5 py-1.5 text-xs font-medium text-accent">
      <span className="h-1.5 w-1.5 rounded-full bg-accent motion-safe:animate-pulse" />
      {/* Tabular figures keep the pill from twitching wider and narrower as the
          digits roll: proportional numerals change width on every frame. */}
      <span className="font-bold tabular-nums" aria-hidden="true">
        {shown.toLocaleString()}
      </span>
      {/* Screen readers get the settled number once, not every frame of it. */}
      <span className="sr-only">{total.toLocaleString()}</span>
      builds generated by players
    </span>
  );
}
