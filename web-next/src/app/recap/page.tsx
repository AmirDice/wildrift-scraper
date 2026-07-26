import type { Metadata } from "next";
import { getChampion } from "@/lib/data";
import { topWinners, topLosers, MOVERS_META, type Mover } from "@/lib/movers";

/* eslint-disable @next/next/no-img-element */

// Season 22 recap poster (single-screen, for a screenshot / share card).
// Not linked in nav/sitemap; renders as a full-bleed overlay.
export const metadata: Metadata = {
  title: "Season 22 Recap · Patch 7.2 Feast On | WrTrueMeta",
  robots: { index: false, follow: false },
};

const YUNARA_ICON = "https://ddragon.leagueoflegends.com/cdn/img/champion/tiles/Yunara_0.jpg";

function fmtDate(yyyymmdd: string) {
  const y = yyyymmdd.slice(0, 4), m = +yyyymmdd.slice(4, 6), d = +yyyymmdd.slice(6, 8);
  return new Date(+y, m - 1, d).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export default function RecapPage() {
  const winners = topWinners(9);
  const losers = topLosers(9);
  const maxAbs = Math.max(...[...winners, ...losers].map((m) => Math.abs(m.delta)), 1);

  return (
    <div className="fixed inset-0 z-[100] flex flex-col overflow-hidden bg-bg">
      <div
        className="pointer-events-none absolute inset-x-0 top-0 h-72"
        style={{ background: "radial-gradient(55% 100% at 50% 0%, rgba(79,141,255,0.18), transparent 70%)" }}
      />
      <div className="relative mx-auto flex h-full w-full max-w-[1440px] flex-col px-6 py-5">
        {/* Header */}
        <header className="flex shrink-0 flex-wrap items-center justify-between gap-4 pb-4">
          <div className="flex items-center gap-4">
            <img src="/logo.png" alt="WrTrueMeta" style={{ height: 40, width: "auto" }} />
            <div className="border-l border-line pl-4">
              <p className="text-[0.6rem] font-bold uppercase tracking-[0.28em] text-accent">
                Season 22 · Patch 7.2
              </p>
              <h1 className="text-2xl font-black leading-tight tracking-tight sm:text-3xl">
                <span className="text-accent">Feast On</span> · Biggest Winners &amp; Losers
              </h1>
            </div>
          </div>
          <div className="text-right text-xs text-muted">
            <p className="font-semibold text-text">{MOVERS_META.scope} win rate</p>
            <p className="mt-0.5">
              {fmtDate(MOVERS_META.before)} → {fmtDate(MOVERS_META.after)} 2026 <span className="text-faint">·</span>{" "}
              <span className="font-semibold text-accent">wrtruemeta.com</span>
            </p>
          </div>
        </header>

        {/* Winners / Losers */}
        <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 sm:grid-cols-2">
          <MoverColumn title="Biggest Winners" tag="Win rate rose since the last scrape" accent="#22c55e" up movers={winners} maxAbs={maxAbs} />
          <MoverColumn title="Biggest Losers" tag="Win rate fell since the last scrape" accent="#ef4444" movers={losers} maxAbs={maxAbs} />
        </div>

        {/* Footer strip: new champion + context */}
        <div className="mt-4 flex shrink-0 flex-wrap items-center justify-between gap-4 rounded-xl border border-line bg-white/[0.03] px-4 py-3">
          <div className="flex items-center gap-3">
            <img src={YUNARA_ICON} alt="" width={40} height={40} className="rounded-full ring-1 ring-accent/40" />
            <div>
              <p className="text-[0.6rem] font-bold uppercase tracking-wide text-accent">New champion</p>
              <p className="text-lg font-black leading-none">Yunara</p>
            </div>
          </div>
          <p className="text-xs text-muted">
            <span className="font-semibold text-text">{winners.length + losers.length}+ champions</span> tracked between China Challenger scrapes.
            Green = rising, red = falling.
          </p>
          <p className="text-sm font-black tracking-tight text-accent">Season 22 · Feast On</p>
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
      <div className="mb-2 flex items-center gap-2">
        <span className="grid h-8 w-8 place-items-center rounded-lg text-lg font-black" style={{ background: `${accent}22`, color: accent }}>
          {up ? "▲" : "▼"}
        </span>
        <div>
          <h3 className="text-base font-black leading-none">{title}</h3>
          <p className="mt-0.5 text-[0.6rem] uppercase tracking-wide text-faint">{tag}</p>
        </div>
      </div>
      <div className="flex min-h-0 flex-1 flex-col justify-between gap-1">
        {movers.map((m) => {
          const champ = getChampion(m.slug);
          const w = Math.round((Math.abs(m.delta) / maxAbs) * 100);
          return (
            <div key={m.slug} className="flex items-center gap-2.5">
              {champ ? (
                <img src={champ.icon} alt="" width={30} height={30} className="shrink-0 rounded-full ring-1 ring-white/10" />
              ) : (
                <span className="grid h-[30px] w-[30px] shrink-0 place-items-center rounded-full bg-white/10 text-[0.6rem] font-bold text-faint">{m.name.slice(0, 2)}</span>
              )}
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="truncate text-sm font-semibold">{m.name}</span>
                  <span className="shrink-0 text-xs text-muted">
                    {m.oldWr.toFixed(1)}<span className="text-faint"> → </span><span className="font-bold text-text">{m.newWr.toFixed(1)}%</span>
                    <span className="ml-1.5 font-black" style={{ color: accent }}>{m.delta > 0 ? "+" : ""}{m.delta}</span>
                  </span>
                </div>
                <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-white/5">
                  <div className="h-full rounded-full" style={{ width: `${w}%`, background: accent }} />
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
