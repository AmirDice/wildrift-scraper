"use client";

import { useEffect, useState } from "react";
import { DiscordButton } from "./discord";

// What's shipping and when. Dates are Sundays; the countdown always targets the
// next milestone still in the future, so the section stays correct as each one
// ships without any code change.
type Milestone = { date: string; title: string; desc: string };

const MILESTONES: Milestone[] = [
  { date: "2026-07-26", title: "Build Optimizer & Counter Builder", desc: "Generate a full build, runes and item order for any champion, or one tuned to beat your exact enemy team." },
  { date: "2026-08-02", title: "NA win rates", desc: "Real North America win rates from the top players on every champion." },
  { date: "2026-08-05", title: "EU win rates refresh", desc: "A fresh Europe pull: top-50 win rates plus player builds, ranked tiers and per-queue stats for every champion." },
  { date: "2026-08-16", title: "Draft counter-pick", desc: "Live draft assistant: pick the champion that best counters the enemy draft, pick by pick." },
];

// midnight UTC on the milestone day
const at = (d: string) => new Date(`${d}T00:00:00Z`).getTime();

function fmt(d: string): string {
  return new Date(`${d}T00:00:00Z`).toLocaleDateString("en-US", {
    month: "short", day: "numeric", timeZone: "UTC",
  });
}

function useCountdown(target: number | null) {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  if (target == null || now == null) return null;
  const ms = Math.max(0, target - now);
  return {
    days: Math.floor(ms / 86_400_000),
    hours: Math.floor((ms / 3_600_000) % 24),
    minutes: Math.floor((ms / 60_000) % 60),
    seconds: Math.floor((ms / 1000) % 60),
  };
}

export function Roadmap() {
  // Resolve "now" on the client so status is accurate without a rebuild.
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => setNow(Date.now()), []);

  const nextIdx = now == null ? 0 : MILESTONES.findIndex((m) => at(m.date) > now);
  const next = nextIdx >= 0 ? MILESTONES[nextIdx] : null;
  const cd = useCountdown(next ? at(next.date) : null);

  return (
    <section className="glass overflow-hidden rounded-2xl border border-line">
      <div className="grid gap-6 p-6 sm:p-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] lg:gap-10">
        {/* countdown side */}
        <div className="flex flex-col justify-center">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">What&rsquo;s coming</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">The road ahead</h2>
          {next ? (
            <>
              <p className="mt-3 text-sm text-muted">
                Next up: <span className="font-semibold text-text">{next.title}</span> · {fmt(next.date)}
              </p>
              <div className="mt-4 flex gap-2.5">
                {cd
                  ? ([["Days", cd.days], ["Hrs", cd.hours], ["Min", cd.minutes], ["Sec", cd.seconds]] as const).map(
                      ([label, val]) => (
                        <div key={label} className="flex min-w-[3.7rem] flex-col items-center rounded-xl border border-line bg-white/[0.03] px-2 py-2.5">
                          <span className="text-2xl font-bold tabular-nums text-text">{String(val).padStart(2, "0")}</span>
                          <span className="text-[0.6rem] font-semibold uppercase tracking-wide text-faint">{label}</span>
                        </div>
                      ),
                    )
                  : // placeholder before the client clock resolves (avoids hydration flash)
                    ["Days", "Hrs", "Min", "Sec"].map((label) => (
                      <div key={label} className="flex min-w-[3.7rem] flex-col items-center rounded-xl border border-line bg-white/[0.03] px-2 py-2.5">
                        <span className="text-2xl font-bold tabular-nums text-faint">--</span>
                        <span className="text-[0.6rem] font-semibold uppercase tracking-wide text-faint">{label}</span>
                      </div>
                    ))}
              </div>
            </>
          ) : (
            <p className="mt-3 text-sm text-muted">Everything on the roadmap has shipped. More coming soon.</p>
          )}
          <div className="mt-6">
            <p className="mb-2.5 text-sm text-muted">Get the drop the moment it lands, and help shape what&rsquo;s next.</p>
            <DiscordButton>Join our Discord</DiscordButton>
          </div>
        </div>

        {/* timeline side */}
        <ol className="relative border-l border-line pl-6">
          {MILESTONES.map((m, i) => {
            const shipped = now != null && at(m.date) <= now;
            const isNext = i === nextIdx;
            return (
              <li key={m.date} className="relative pb-6 last:pb-0">
                <span
                  className={`absolute -left-[1.6rem] top-1 grid h-4 w-4 place-items-center rounded-full ring-4 ring-bg ${
                    shipped ? "bg-emerald-400" : isNext ? "bg-accent" : "bg-white/20"
                  }`}
                >
                  {shipped && (
                    <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="#07121f" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  )}
                </span>
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`text-xs font-semibold ${shipped ? "text-emerald-300" : isNext ? "text-accent" : "text-faint"}`}>
                    {fmt(m.date)}
                  </span>
                  {shipped && <span className="rounded bg-emerald-400/20 px-1.5 py-0.5 text-[0.55rem] font-bold uppercase tracking-wide text-emerald-300">Live</span>}
                  {isNext && <span className="rounded bg-accent/20 px-1.5 py-0.5 text-[0.55rem] font-bold uppercase tracking-wide text-accent">Next</span>}
                </div>
                <p className="mt-0.5 font-semibold">{m.title}</p>
                <p className="mt-0.5 text-sm text-muted">{m.desc}</p>
              </li>
            );
          })}
        </ol>
      </div>
    </section>
  );
}
