import summary from "@/data/champion_change_summary.json";
import { CURRENT_PATCH } from "@/lib/patch";

/**
 * Is the win-rate data older than the patch the site claims to describe?
 *
 * The patch label and the win rates move on different clocks. CURRENT_PATCH
 * follows the pipeline, which is updated within hours of Riot publishing notes,
 * while EU and NA win rates only change when the boards are re-scraped, and
 * that is a manual overnight run. Between the two the tier list is titled with
 * a patch whose games it has never seen.
 *
 * That gap is not hypothetical. 7.2c went live on 2026-08-12 with EU collected
 * on the 6th and NA on the 9th, so for several days the page read "Wild Rift
 * Tier List Patch 7.2c" above rankings built entirely from 7.2b games, with
 * nothing saying so. A visitor checking whether a nerf landed would have been
 * reading the numbers from before it.
 *
 * The site cannot fix that by collecting faster, and pretending otherwise by
 * omission is worse than saying it. So the pages say it, computed rather than
 * remembered: nobody has to notice the mismatch and write a banner by hand,
 * and the banner disappears on its own once the data catches up.
 *
 * CN is deliberately out of scope. Those figures are Tencent's own, refreshed
 * daily, and China runs its own patch cycle, so "older than 7.2c" is not a
 * defect there and would be a confusing thing to warn about.
 */

interface SummaryEntry {
  lastChangedPatch?: string | null;
  lastChangedAt?: string | null;
}

const CHAMPIONS = (summary as { champions: Record<string, SummaryEntry> }).champions;

/** When the current patch went live (ISO), or null if nothing records it. */
export function currentPatchDate(): string | null {
  if (!CURRENT_PATCH) return null;
  for (const entry of Object.values(CHAMPIONS)) {
    if (entry.lastChangedPatch === CURRENT_PATCH && entry.lastChangedAt) {
      return entry.lastChangedAt;
    }
  }
  // A patch that changed no champion at all leaves no trace here. Returning
  // null means "cannot tell", and callers show nothing rather than guessing.
  return null;
}

export interface Freshness {
  patch: string;
  /** Human date the board was collected, exactly as the data stores it. */
  collectedOn: string;
  /** True when the board was collected BEFORE the patch went live. */
  stale: boolean;
  /** Whole days between collection and the patch. 0 when not stale. */
  daysBefore: number;
}

/**
 * Compares one region's collection date against the current patch.
 *
 * Returns null when the comparison cannot be made honestly: no patch recorded,
 * no collection date, or a date string that does not parse. Silence is the
 * right output there, because a warning that might be wrong is worse than no
 * warning at all.
 */
export function freshness(collectedOn: string | null | undefined): Freshness | null {
  const patchIso = currentPatchDate();
  if (!patchIso || !collectedOn || !CURRENT_PATCH) return null;

  const collected = new Date(collectedOn);
  const patched = new Date(patchIso);
  if (Number.isNaN(collected.getTime()) || Number.isNaN(patched.getTime())) return null;

  const ms = patched.getTime() - collected.getTime();
  const stale = ms > 0;
  return {
    patch: CURRENT_PATCH,
    collectedOn,
    stale,
    daysBefore: stale ? Math.floor(ms / 86_400_000) : 0,
  };
}
