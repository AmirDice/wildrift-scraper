"use client";

import { useEffect, useState } from "react";
import type { Region } from "@/components/region-toggle";

/**
 * "Last updated" markers for the tier lists.
 *
 *  - CHINA is scraped every three days, while the public marker intentionally
 *    follows the visitor's current day. Reading the client clock keeps that
 *    marker current without requiring a daily deploy.
 *  - EU is reviewed a few times a season by hand, so it shows the date its data
 *    was last collected -- an honest single date, not a schedule.
 *
 * The earlier version drew a season timeline for EU/NA; it read as a promise of
 * a cadence the hand-reviewed list does not keep, so it was removed in favour of
 * a plain last-updated date.
 */

function formatToday(): string {
  return new Date().toLocaleDateString(undefined, {
    year: "numeric", month: "long", day: "numeric",
  });
}

function useToday(): string | null {
  const [today, setToday] = useState<string | null>(null);
  useEffect(() => {
    const frame = requestAnimationFrame(() => setToday(formatToday()));
    return () => cancelAnimationFrame(frame);
  }, []);
  return today;
}

function CalendarIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden className="text-emerald-300">
      <rect x="3" y="4" width="18" height="18" rx="2" />
      <path d="M16 2v4M8 2v4M3 10h18" />
    </svg>
  );
}

/** China: refreshed every day. The date is read after mount so render stays
 *  pure and the server/client markup match. */
export function ChinaUpdated() {
  const today = useToday();
  return (
    <span className="glass inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium text-muted">
      <CalendarIcon />
      Last updated{today && <> · <span className="text-text">{today}</span></>}
    </span>
  );
}

/** EU: the fixed date the current data was collected. */
export function LastUpdated({ date }: { date?: string | null }) {
  if (!date) return null;
  return (
    <span className="glass inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium text-muted">
      <CalendarIcon />
      Last updated · <span className="text-text">{date}</span>
    </span>
  );
}

function readableDate(date?: string | null): string | null {
  if (!date) return null;
  if (!/^\d{8}$/.test(date)) return date;
  const year = Number(date.slice(0, 4));
  const month = Number(date.slice(4, 6));
  const day = Number(date.slice(6, 8));
  return new Date(Date.UTC(year, month - 1, day)).toLocaleDateString(undefined, {
    year: "numeric", month: "long", day: "numeric", timeZone: "UTC",
  });
}

/** One honest, in-place date marker for region-toggled datasets. */
export function RegionUpdated({
  region,
  euDate,
  cnDate,
}: {
  region: Region;
  euDate?: string | null;
  cnDate?: string | null;
}) {
  const eu = readableDate(euDate);
  const today = useToday();
  const cn = today ?? readableDate(cnDate);
  if (region === "NA") return null;

  return (
    <span className="glass inline-flex flex-wrap items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium text-muted">
      <CalendarIcon />
      {region === "Global" ? (
        <>
          Data updated
          {eu && <><span className="text-faint">·</span><span className="text-text">EU {eu}</span></>}
          {cn && <><span className="text-faint">·</span><span className="text-text">CN {cn}</span></>}
        </>
      ) : (
        <>Last updated <span className="text-faint">·</span> <span className="text-text">{region === "CN" ? cn : eu}</span></>
      )}
    </span>
  );
}
