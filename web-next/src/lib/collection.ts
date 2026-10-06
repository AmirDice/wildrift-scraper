import site from "@/data/site.json";
import siteNa from "@/data/site_na.json";
import cn from "@/data/cn.json";
import { kvGetJson } from "@/lib/kv";

/**
 * Where the data comes from, and how far along it is right now.
 *
 * The three regions are collected by three different processes on three
 * different clocks, and a visitor reading a win rate has no way to know which
 * of them produced it or how old it is. EU and NA are overnight ADB runs on
 * the phone here, one champion at a time through 141 champions; CN is a daily
 * pull from Tencent's published figures. A run can also be part way through,
 * which is the case this exists for: the tier list is live and changing while
 * the numbers behind it are still being replaced.
 *
 * Two sources, in priority order:
 *
 *   LIVE  `collection:progress` in KV, written by the scraper as it works
 *         (see src/collection_progress.py). Present only while a run is in
 *         flight, or until the next run clears it.
 *
 *   REST  the collection dates baked into the data files themselves. Always
 *         available, and what the bar falls back to between runs, which is
 *         most of the time. This is why the component is useful on day one
 *         rather than only during a scrape.
 *
 * The live record never invents a region: a region missing from KV falls back
 * to its baked date independently of the others, so a partial write cannot
 * blank out the two regions it does not mention.
 */

export type RegionKey = "EU" | "NA" | "CN";
export type CollectionStatus = "running" | "complete" | "idle";

export interface RegionProgress {
  region: RegionKey;
  status: CollectionStatus;
  /** Champions finished so far. Only meaningful while running. */
  done: number;
  /** Champions this run intends to cover. */
  total: number;
  /** 0-100, rounded. 100 whenever status is "complete". */
  percent: number;
  /** ISO date the CURRENT data was collected, or null if nothing has run. */
  collectedOn: string | null;
  /** ISO timestamp the in-flight run began, or null. */
  startedAt: string | null;
}

export interface CollectionState {
  regions: RegionProgress[];
  /** True while any region is mid-run; the client polls only when it is. */
  active: boolean;
}

const KV_KEY = "collection:progress";
// Fallback only: used when a region's data file carries no nChampions.
// The roster is 142 (Hwei joined after this was first written), and a
// stale value here would show a region as collecting more or fewer
// champions than exist.
const ROSTER_TOTAL = 142;

/** "September 3, 2026" and "20260921" are both dates. Neither is ISO. */
function toIso(value: unknown): string | null {
  if (typeof value !== "string" || !value.trim()) return null;
  const compact = value.trim();
  const ymd = /^(\d{4})(\d{2})(\d{2})$/.exec(compact);
  if (ymd) return `${ymd[1]}-${ymd[2]}-${ymd[3]}`;
  const parsed = Date.parse(compact);
  if (Number.isNaN(parsed)) return null;
  // Local parts, NOT toISOString(). "September 3, 2026" parses as local
  // midnight, and converting that to UTC rolls the date back a day for any
  // timezone ahead of UTC: the API served 2026-09-02 for a file that says
  // September 3. The date here is a calendar day, not an instant, so it must
  // never be shifted by an offset.
  const d = new Date(parsed);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

interface LiveRegion {
  status?: string;
  done?: number;
  total?: number;
  startedAt?: string | null;
  completedAt?: string | null;
}

/** What the data files say, with no live run involved. */
function baseline(): Record<RegionKey, RegionProgress> {
  const rest = (
    region: RegionKey, collectedOn: string | null, total: number,
  ): RegionProgress => ({
    region,
    // A baked date means that region finished, whenever that was. Without one
    // it has never run, which is "idle" rather than a 0% run in progress.
    status: collectedOn ? "complete" : "idle",
    done: collectedOn ? total : 0,
    total,
    percent: collectedOn ? 100 : 0,
    collectedOn,
    startedAt: null,
  });
  return {
    EU: rest("EU", toIso(site.collectedOn), site.nChampions || ROSTER_TOTAL),
    NA: rest("NA", toIso(siteNa.collectedOn), siteNa.nChampions || ROSTER_TOTAL),
    CN: rest("CN", toIso((cn as { date?: string }).date),
             (cn as { nChampions?: number }).nChampions || ROSTER_TOTAL),
  };
}

export async function getCollectionState(): Promise<CollectionState> {
  const merged = baseline();
  let live: Record<string, LiveRegion> = {};
  try {
    const doc = await kvGetJson<{ regions?: Record<string, LiveRegion> }>(
      KV_KEY, {});
    live = doc.regions || {};
  } catch {
    // KV being unreachable must never take the navbar down with it. The
    // baked dates are a complete, correct answer on their own.
    live = {};
  }

  for (const key of ["EU", "NA", "CN"] as RegionKey[]) {
    const row = live[key];
    if (!row || typeof row !== "object") continue;
    const total = Number(row.total) > 0 ? Number(row.total) : merged[key].total;
    const done = Math.max(0, Math.min(Number(row.done) || 0, total));
    const running = row.status === "running";
    if (running) {
      merged[key] = {
        region: key,
        status: "running",
        done,
        total,
        percent: total > 0 ? Math.round((done / total) * 100) : 0,
        // While a run is in flight the date on screen is still the date of
        // the data being REPLACED, not the run's own. Showing the new date
        // early would claim freshness the site does not have yet.
        collectedOn: merged[key].collectedOn,
        startedAt: typeof row.startedAt === "string" ? row.startedAt : null,
      };
    } else if (row.completedAt) {
      const iso = toIso(row.completedAt);
      merged[key] = {
        region: key, status: "complete", done: total, total, percent: 100,
        collectedOn: iso ?? merged[key].collectedOn, startedAt: null,
      };
    }
  }

  const regions = [merged.EU, merged.NA, merged.CN];
  return { regions, active: regions.some((r) => r.status === "running") };
}
