import type { Metadata } from "next";
import { getChampion } from "@/lib/data";
import { topWinners, topLosers, MOVERS_META, type Mover } from "@/lib/movers";
import { CURRENT_PATCH } from "@/lib/patch";

/* eslint-disable @next/next/no-img-element */

// Patch-movers poster (single-screen, for a screenshot / Reddit share card).
// Not linked in nav/sitemap; renders as a full-bleed overlay above the chrome.
//
// Everything on it is DERIVED: patch label from stat_rules via CURRENT_PATCH,
// dates and rows from cn_movers.json. The previous version hardcoded
// "Season 22 · Patch 7.2 Feast On" and went stale the moment 7.2a landed; a
// poster that gets screenshotted is the worst place to discover a stale label.
export const metadata: Metadata = {
  // The layout template appends "| WrTrueMeta" itself.
  title: `Patch ${CURRENT_PATCH} Day One Movers`,
  robots: { index: false, follow: false },
};

function fmtDate(yyyymmdd: string) {
  const y = yyyymmdd.slice(0, 4), m = +yyyymmdd.slice(4, 6), d = +yyyymmdd.slice(6, 8);
  return new Date(+y, m - 1, d).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export default function RecapPage() {
  const winners = topWinners(8);
  const losers = topLosers(8);
  const maxAbs = Math.max(...[...winners, ...losers].map((m) => Math.abs(m.delta)), 1);
  const topUp = winners[0];
  const topDown = losers[0];

  return (
    <div className="fixed inset-0 z-[100] flex flex-col overflow-hidden bg-bg">
      {/* The site's own backdrop, same three layers as app/layout.tsx, so the
          poster reads as a page of the site rather than a leftover of the old
          flat design. */}
      <div className="absolute inset-0 bg-cover bg-center" style={{ backgroundImage: "url(/ionia2.jpg)" }} />
      <div className="absolute inset-0" style={{ background: "linear-gradient(180deg, rgba(7,10,18,0.46) 0%, rgba(7,10,18,0.52) 45%, rgba(7,10,18,0.56) 100%)" }} />
      <div className="absolute inset-0" style={{ background: "radial-gradient(125% 105% at 50% 45%, transparent 55%, rgba(3,5,11,0.42) 88%, rgba(3,5,11,0.62) 100%)" }} />

      <div className="relative mx-auto flex h-full w-full max-w-[1440px] flex-col px-6 py-5">
        {/* Header */}
        <header className="flex shrink-0 flex-wrap items-end justify-between gap-4 pb-4">
          <div>
            <p className="text-sm font-extrabold uppercase tracking-[0.18em] text-accent">
              WRTRUE<span className="text-text">META</span>
            </p>
            <h1 className="mt-1 text-3xl font-black leading-tight tracking-tight sm:text-4xl">
              Patch {CURRENT_PATCH} · Day One on the Ladder
            </h1>
            <p className="mt-1.5 max-w-xl text-sm leading-relaxed text-muted">
              First day on the new patch, measured on the{" "}
              <span className="text-text">China Challenger</span> ladder: the same champions,
              the day before against the day after.
            </p>
          </div>
          <div className="flex gap-3">
            {topUp && (
              <div className="glass min-w-[136px] rounded-2xl px-4 py-3 text-center">
                <p className="text-2xl font-black tabular-nums text-emerald-400">+{topUp.delta}</p>
                <p className="mt-0.5 text-[0.6rem] font-bold uppercase tracking-[0.12em] text-faint">{topUp.name}</p>
              </div>
            )}
            {topDown && (
              <div className="glass min-w-[136px] rounded-2xl px-4 py-3 text-center">
                <p className="text-2xl font-black tabular-nums text-bad">{topDown.delta}</p>
                <p className="mt-0.5 text-[0.6rem] font-bold uppercase tracking-[0.12em] text-faint">{topDown.name}</p>
              </div>
            )}
          </div>
        </header>

        {/* Winners / Losers */}
        <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 sm:grid-cols-2 [&>*]:min-w-0">
          <MoverColumn
            title="Rising"
            tag={`Win rate rose on day one of ${CURRENT_PATCH}`}
            accent="#34d399"
            up
            movers={winners}
            maxAbs={maxAbs}
          />
          <MoverColumn
            title="Falling"
            tag={`Win rate fell on day one of ${CURRENT_PATCH}`}
            accent="#ff6a6a"
            movers={losers}
            maxAbs={maxAbs}
          />
        </div>

        {/* Method strip */}
        <div className="glass mt-4 flex shrink-0 flex-wrap items-center justify-between gap-3 rounded-2xl px-4 py-3">
          <p className="text-xs leading-relaxed text-muted">
            <span className="font-semibold text-text">{fmtDate(MOVERS_META.before)} vs {fmtDate(MOVERS_META.after)}</span>
            {" "}· official China server data, Challenger bracket. One day of games, so treat it as
            the first read, not the verdict.
          </p>
          <p className="text-sm font-black tracking-tight text-accent">wrtruemeta.com</p>
        </div>
      </div>
    </div>
  );
}

function MoverColumn({ title, tag, accent, movers, maxAbs, up = false }: {
  title: string; tag: string; accent: string; movers: Mover[]; maxAbs: number; up?: boolean;
}) {
  return (
    <div className="glass flex min-h-0 flex-col overflow-hidden rounded-2xl p-4">
      <div className="mb-2.5 flex items-center gap-2.5">
        <span
          className="grid h-9 w-9 place-items-center rounded-xl text-lg font-black"
          style={{ background: `${accent}1f`, color: accent, boxShadow: `inset 0 0 0 1px ${accent}44` }}
        >
          {up ? "▲" : "▼"}
        </span>
        <div>
          <h3 className="text-lg font-black leading-none tracking-tight">{title}</h3>
          <p className="mt-1 text-[0.6rem] font-bold uppercase tracking-[0.12em] text-faint">{tag}</p>
        </div>
      </div>
      <div className="flex min-h-0 flex-1 flex-col justify-between gap-1">
        {movers.map((m, i) => {
          const champ = getChampion(m.slug);
          const w = Math.round((Math.abs(m.delta) / maxAbs) * 100);
          return (
            <div key={m.slug} className="flex items-center gap-3">
              <span className="w-4 shrink-0 text-right text-[0.65rem] font-bold tabular-nums text-faint">{i + 1}</span>
              {champ ? (
                <img src={champ.icon} alt="" width={34} height={34} className="shrink-0 rounded-xl ring-1 ring-white/15" />
              ) : (
                <span className="grid h-[34px] w-[34px] shrink-0 place-items-center rounded-xl bg-white/10 text-[0.6rem] font-bold text-faint">{m.name.slice(0, 2)}</span>
              )}
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="truncate text-sm font-bold">{m.name}</span>
                  <span className="shrink-0 text-xs tabular-nums text-muted">
                    {m.oldWr.toFixed(1)}<span className="text-faint"> to </span><span className="font-bold text-text">{m.newWr.toFixed(1)}%</span>
                    <span className="ml-2 font-black" style={{ color: accent }}>{m.delta > 0 ? "+" : ""}{m.delta}</span>
                  </span>
                </div>
                <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
                  <div className="h-full rounded-full" style={{ width: `${Math.max(w, 4)}%`, background: `linear-gradient(90deg, ${accent}55, ${accent})` }} />
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
