import Link from "next/link";
import { getChampion } from "@/lib/data";
import { topWinners, topLosers, MOVERS_META, type Mover } from "@/lib/movers";
import { CURRENT_PATCH } from "@/lib/patch";

/* eslint-disable @next/next/no-img-element */

// Highlighted home-page section: the biggest CN Challenger movers.
export function MoversHighlight() {
  const winners = topWinners(5);
  const losers = topLosers(5);
  if (!winners.length && !losers.length) return null;

  return (
    <div
      className="glass relative overflow-hidden rounded-2xl border border-accent/30 p-5 sm:p-6"
      style={{ background: "radial-gradient(60% 130% at 100% 0%, rgba(34,197,94,0.10), transparent 60%), radial-gradient(60% 130% at 0% 100%, rgba(239,68,68,0.10), transparent 60%), linear-gradient(110deg,#10131d,#0b0e16)" }}
    >
      <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
        <div>
          <p className="text-[0.65rem] font-bold uppercase tracking-[0.18em] text-accent">China · biggest movers</p>
          <h2 className="mt-1 text-xl font-black tracking-tight sm:text-2xl">
            Patch {CURRENT_PATCH || "7.2a"} Biggest Winners &amp; Losers
          </h2>
          <p className="mt-0.5 text-xs text-muted">{MOVERS_META.scope} win rate</p>
        </div>
        <Link href="/recap" className="rounded-lg border border-line bg-white/[0.04] px-3 py-1.5 text-sm font-semibold text-accent transition hover:border-accent/50">
          See full recap →
        </Link>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <MoverList title="Biggest Winners" accent="#22c55e" up movers={winners} />
        <MoverList title="Biggest Losers" accent="#ef4444" movers={losers} />
      </div>
    </div>
  );
}

function MoverList({ title, accent, movers, up = false }: { title: string; accent: string; movers: Mover[]; up?: boolean }) {
  return (
    <div className="rounded-xl bg-white/[0.03] p-3">
      <div className="mb-2 flex items-center gap-2">
        <span className="grid h-6 w-6 place-items-center rounded-md text-sm font-black" style={{ background: `${accent}22`, color: accent }}>{up ? "▲" : "▼"}</span>
        <h3 className="text-sm font-bold">{title}</h3>
      </div>
      <div className="flex flex-col gap-1">
        {movers.map((m) => {
          const champ = getChampion(m.slug);
          return (
            <Link key={m.slug} href={`/champions/${m.slug}`} className="flex items-center gap-2.5 rounded-lg px-1.5 py-1 transition hover:bg-white/[0.05]">
              {champ ? (
                <img src={champ.icon} alt="" width={28} height={28} className="shrink-0 rounded-full ring-1 ring-white/10" />
              ) : (
                <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-white/10 text-[0.55rem] font-bold text-faint">{m.name.slice(0, 2)}</span>
              )}
              <span className="min-w-0 flex-1 truncate text-sm font-medium">{m.name}</span>
              <span className="shrink-0 text-xs text-muted">{m.oldWr.toFixed(1)}<span className="text-faint"> → </span><span className="font-semibold text-text">{m.newWr.toFixed(1)}%</span></span>
              <span className="w-12 shrink-0 text-right text-sm font-black" style={{ color: accent }}>{m.delta > 0 ? "+" : ""}{m.delta}</span>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
