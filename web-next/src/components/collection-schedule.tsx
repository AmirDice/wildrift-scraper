import { site, regionBoard } from "@/lib/data";
import { CN_META } from "@/lib/cn";
import { CURRENT_PATCH } from "@/lib/patch";
import { currentPatchDate } from "@/lib/patch-freshness";

/**
 * When each server's leaderboards are collected, as a fixed rhythm people can
 * plan around rather than a date they have to discover.
 *
 * The rule, set by the owner on 2026-10-25: a patch lands on a Tuesday, and
 * the week after it NA is collected on the Monday, EU on the Tuesday and the
 * China ladder on the Wednesday. NA and EU are collected every patch; China
 * every other patch for now. The 7.3b cycle already ran this way (patch on
 * 14 Oct, NA on the 19th, EU on the 20th, China skipped after collecting
 * 7.3a), so the dates below are computed from the patch, not typed in.
 *
 * Nothing here depends on today's date. The pages are static, so a "late" or
 * "today" label would be frozen at whatever moment the deploy happened. Each
 * region is either collected for this patch (its board is dated after the
 * patch went live) or shows the day it is planned for.
 *
 * China's daily win rates are a different feed (Tencent's own numbers,
 * refreshed every day) and are not on this schedule; the footnote says so,
 * because "China every other patch" next to a daily-updated China tier list
 * would otherwise read as a contradiction.
 */

const DAY = 86_400_000;

/** The Monday of the week after the patch: the first Monday at least four
 *  days after it, so a Tuesday patch gives the next Monday (+6) and a patch
 *  that slips to Wednesday still lands on the same Monday (+5). */
function collectionMonday(patch: Date): Date {
  const earliest = new Date(patch.getTime() + 4 * DAY);
  const toMonday = (8 - earliest.getUTCDay()) % 7;
  const monday = new Date(earliest.getTime() + toMonday * DAY);
  monday.setUTCHours(0, 0, 0, 0);
  return monday;
}

const fmt = (d: Date) =>
  d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });

const parse = (s: string | null | undefined) => {
  if (!s) return null;
  const d = new Date(`${s} UTC`);
  return Number.isNaN(d.getTime()) ? null : d;
};

type Status =
  | { kind: "collected"; on: Date }
  | { kind: "planned"; on: Date }
  | { kind: "skipped" };

interface Row {
  region: string;
  when: string;
  cadence: string;
  status: Status | null;
}

function schedule(): { patch: string; patchOn: Date | null; rows: Row[] } {
  const patchIso = currentPatchDate();
  const patchOn = patchIso ? new Date(patchIso) : null;
  const monday = patchOn ? collectionMonday(patchOn) : null;

  const statusFor = (collected: string | null | undefined, offset: number): Status | null => {
    if (!patchOn || !monday) return null;
    const on = parse(collected);
    if (on && on.getTime() >= patchOn.getTime() - DAY) return { kind: "collected", on };
    return { kind: "planned", on: new Date(monday.getTime() + offset * DAY) };
  };

  // China alternates. A ladder collected within three weeks before this
  // patch went live covered the previous one, so this patch is the skip.
  // Patches run about two weeks apart; three weeks absorbs a late capture
  // without mistaking a missed cycle for a planned skip.
  let cn = statusFor(CN_META.ladderDate, 2);
  const cnOn = parse(CN_META.ladderDate);
  if (cn?.kind === "planned" && patchOn && cnOn && patchOn.getTime() - cnOn.getTime() < 21 * DAY) {
    cn = { kind: "skipped" };
  }

  return {
    patch: CURRENT_PATCH,
    patchOn,
    rows: [
      { region: "NA", when: "Monday", cadence: "Every patch", status: statusFor(regionBoard("NA").collectedOn, 0) },
      { region: "EU", when: "Tuesday", cadence: "Every patch", status: statusFor(site.collectedOn, 1) },
      { region: "China", when: "Wednesday", cadence: "Every other patch", status: cn },
    ],
  };
}

function StatusPill({ status, patch }: { status: Status | null; patch: string }) {
  if (!status) return null;
  if (status.kind === "collected") {
    // The patch, not the day: a board's date is its LAST session, so a few
    // recaptures on a Friday would read as the Monday collection slipping.
    return <span title={`Last session ${fmt(status.on)}`} className="rounded-full bg-emerald-400/12 px-2 py-0.5 text-[0.65rem] font-semibold text-emerald-300">Collected for {patch}</span>;
  }
  if (status.kind === "planned") {
    return <span className="rounded-full bg-gold/12 px-2 py-0.5 text-[0.65rem] font-semibold text-gold">Next: {fmt(status.on)}</span>;
  }
  return <span className="rounded-full bg-white/[0.07] px-2 py-0.5 text-[0.65rem] font-semibold text-muted">Skips {patch}, back next patch</span>;
}

export function CollectionSchedule({ className = "" }: { className?: string }) {
  const { patch, patchOn, rows } = schedule();
  return (
    <section id="schedule" aria-labelledby="schedule-title" className={`glass rounded-2xl border border-white/[0.09] p-4 sm:p-5 ${className}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 id="schedule-title" className="text-sm font-semibold text-text">Data update schedule</h2>
        <p className="text-[0.7rem] text-faint">
          Patches land on Tuesday. Leaderboards are collected the week after.
          {patch && patchOn ? <> Patch {patch} went live {fmt(patchOn)}.</> : null}
        </p>
      </div>
      <ol className="mt-3 grid gap-2 sm:grid-cols-3">
        {rows.map((row) => (
          <li key={row.region} className="flex items-center justify-between gap-3 rounded-xl bg-white/[0.035] px-3 py-2.5 sm:flex-col sm:items-stretch sm:gap-1.5">
            <div className="min-w-0">
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-sm font-semibold text-text">{row.region}</span>
                <span className="hidden text-[0.65rem] uppercase tracking-[0.12em] text-faint sm:inline">{row.cadence}</span>
              </div>
              <p className="text-xs text-muted">
                {row.when} after the patch<span className="sm:hidden"> · {row.cadence.toLowerCase()}</span>
              </p>
            </div>
            <div className="shrink-0"><StatusPill status={row.status} patch={patch} /></div>
          </li>
        ))}
      </ol>
      <p className="mt-3 text-[0.65rem] leading-relaxed text-faint">
        China&rsquo;s official win rates update every day and are not on this schedule. It covers the China ladder: top players, their builds and win rates.
      </p>
    </section>
  );
}
