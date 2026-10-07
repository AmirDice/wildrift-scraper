"use client";

import { useMemo, useState, type CSSProperties, type ReactNode } from "react";

export type AnalyticsPlayer = {
  r: number;
  p: string;
  w: number;
  g: number;
  s?: number | null;
};

type RegionPoint = { label: string; value: number | null };

export function ChampionAnalytics({
  champion,
  players,
  regions,
  winRate,
  winRateDelta,
  winrateStd,
}: {
  champion: string;
  players: AnalyticsPlayer[];
  regions: RegionPoint[];
  winRate: number;
  winRateDelta?: number | null;
  winrateStd?: number | null;
}) {
  const valid = useMemo(
    () => players.filter((player) => Number.isFinite(player.w) && Number.isFinite(player.g) && player.g > 0),
    [players],
  );
  const [selected, setSelected] = useState<AnalyticsPlayer | null>(null);

  const stats = useMemo(() => {
    if (!valid.length) return null;
    const rates = valid.map((player) => player.w).sort((a, b) => a - b);
    const average = rates.reduce((sum, value) => sum + value, 0) / rates.length;
    const median = rates.length % 2
      ? rates[Math.floor(rates.length / 2)]
      : (rates[rates.length / 2 - 1] + rates[rates.length / 2]) / 2;
    const ranked = [...valid].sort((a, b) => a.r - b.r);
    const band = (from: number, to: number) => {
      const rows = ranked.filter((player) => player.r >= from && player.r <= to);
      return rows.length ? rows.reduce((sum, player) => sum + player.w, 0) / rows.length : null;
    };
    const topFive = band(1, 5);
    const consistency = Math.round(Math.max(0, Math.min(100, 100 - (winrateStd ?? 8) * 2)));
    return {
      average,
      median,
      min: Math.min(...rates),
      max: Math.max(...rates),
      topFive,
      consistency,
      bands: [
        { label: "1–5", value: band(1, 5) },
        { label: "6–10", value: band(6, 10) },
        { label: "11–25", value: band(11, 25) },
        { label: "26–50", value: band(26, 50) },
      ],
    };
  }, [valid, winrateStd]);

  if (!stats) return null;

  return (
    <section aria-label={`${champion} player analytics`} className="grid gap-3 lg:grid-cols-12">
      <GraphCard className="lg:col-span-7" title="Top-player WR spread" value={`Median ${stats.median.toFixed(1)}%`} tip="Each dot is one ranked player. Tap a dot to see the player, games, and win rate.">
        <Distribution players={valid} min={stats.min} max={stats.max} median={stats.median} average={stats.average} selected={selected} onSelect={setSelected} />
        <PlayerReadout player={selected} fallback={`Median ${stats.median.toFixed(1)}% · average ${stats.average.toFixed(1)}%`} />
      </GraphCard>

      <GraphCard className="lg:col-span-5" title="Region pulse" value={`${regions.filter((region) => region.value != null).length} servers`} tip="The same champion compared across every region that currently has a usable sample.">
        <RegionBars regions={regions} />
      </GraphCard>

      <GraphCard className="lg:col-span-7" title="WR × games played" value={`${valid.length} players`} tip="Every dot is a player. This reveals whether a huge win rate comes from a deep sample or a short hot streak.">
        <Scatter players={valid} selected={selected} onSelect={setSelected} />
        <PlayerReadout player={selected} fallback="Tap a player dot" />
      </GraphCard>

      <GraphCard className="lg:col-span-5" title="Skill ceiling" value={stats.topFive == null ? "–" : `${(stats.topFive - winRate).toFixed(1)} pp`} tip="The gap between the first five leaderboard positions and the full tracked pool.">
        <div className="grid grid-cols-[auto_1fr] items-center gap-4 py-1">
          <div className="grid h-[4.5rem] w-[4.5rem] place-items-center rounded-full border border-accent/25 bg-[conic-gradient(#72a7ff_var(--score),#a88dff_var(--score),rgba(255,255,255,.06)_0)] p-1.5 shadow-[0_0_22px_rgba(114,167,255,.14)]" style={{ "--score": `${stats.consistency}%` } as CSSProperties}>
            <div className="grid h-full w-full place-items-center rounded-full bg-[#09111e] text-center">
              <div><strong className="block text-lg leading-none">{stats.consistency}</strong><span className="mt-1 block text-[0.48rem] uppercase tracking-[0.12em] text-faint">Cons.</span></div>
            </div>
          </div>
          <div className="space-y-3">
            <MetricRow label="Elite 5" value={stats.topFive == null ? "–" : `${stats.topFive.toFixed(1)}%`} accent />
            <MetricRow label="All tracked" value={`${stats.average.toFixed(1)}%`} />
            <MetricRow label="Median" value={`${stats.median.toFixed(1)}%`} />
          </div>
        </div>
      </GraphCard>

      <GraphCard className="lg:col-span-7" title="Leaderboard bands" value={`${Math.max(...stats.bands.map((band) => band.value ?? 0)).toFixed(1)}% peak`} tip="Average win rate by leaderboard position. This shows whether performance stays deep or is carried by only a handful of players.">
        <BandBars bands={stats.bands} />
      </GraphCard>

      <GraphCard className="lg:col-span-5" title="Collection momentum" value={winRateDelta == null ? "Fresh" : `${winRateDelta >= 0 ? "+" : ""}${winRateDelta.toFixed(1)} pp`} tip="Change since the previous collected leaderboard snapshot, not a live match-to-match estimate.">
        <Momentum current={winRate} delta={winRateDelta ?? 0} />
      </GraphCard>
    </section>
  );
}

function GraphCard({ title, value, tip, className = "", children }: { title: string; value: string; tip: string; className?: string; children: ReactNode }) {
  return (
    <article className={`relative overflow-hidden rounded-2xl border border-white/[0.09] bg-[linear-gradient(145deg,rgba(214,231,255,.065),rgba(49,83,138,.025)),rgba(7,14,27,.82)] p-4 shadow-[inset_0_1px_rgba(255,255,255,.1)] sm:p-5 ${className}`}>
      <div className="flex items-start justify-between gap-3">
        <h2 className="text-sm font-semibold sm:text-base">{title}</h2>
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-accent">{value}</span>
          <InfoTip text={tip} />
        </div>
      </div>
      <div className="mt-4">{children}</div>
    </article>
  );
}

function InfoTip({ text }: { text: string }) {
  return (
    <details className="group relative">
      <summary className="grid h-5 w-5 list-none cursor-pointer place-items-center rounded-full border border-white/10 text-[0.65rem] font-bold text-faint hover:text-text">?</summary>
      <span className="absolute right-0 top-7 z-30 w-56 rounded-xl border border-white/10 bg-[#0b1424] p-3 text-xs font-normal leading-relaxed text-muted shadow-2xl">{text}</span>
    </details>
  );
}

function Distribution({ players, min, max, median, average, selected, onSelect }: { players: AnalyticsPlayer[]; min: number; max: number; median: number; average: number; selected: AnalyticsPlayer | null; onSelect: (player: AnalyticsPlayer) => void }) {
  const low = Math.max(0, Math.floor(min - 3));
  const high = Math.min(100, Math.ceil(max + 3));
  const width = 640;
  const x = (value: number) => 20 + ((value - low) / Math.max(1, high - low)) * (width - 40);
  return (
    <div>
      <svg viewBox={`0 0 ${width} 112`} className="h-auto w-full" role="img" aria-label="Win rate distribution">
        <line x1="20" y1="82" x2={width - 20} y2="82" stroke="rgba(255,255,255,.12)" />
        {[low, Math.round((low + high) / 2), high].map((tick) => <g key={tick}><line x1={x(tick)} y1="78" x2={x(tick)} y2="88" stroke="rgba(255,255,255,.18)"/><text x={x(tick)} y="105" textAnchor="middle" fill="#7e8da6" fontSize="11">{tick}%</text></g>)}
        <line x1={x(median)} y1="15" x2={x(median)} y2="82" stroke="#76e3d1" strokeDasharray="4 4" />
        <line x1={x(average)} y1="15" x2={x(average)} y2="82" stroke="#9e87ff" strokeDasharray="4 4" />
        {players.map((player, index) => {
          const color = ["#72a7ff", "#78e3d4", "#a88dff", "#f2ca72"][Math.min(3, Math.floor(index / Math.max(1, Math.ceil(players.length / 4))))];
          return <circle key={`${player.r}-${player.p}`} cx={x(player.w)} cy={65 - (index % 4) * 12} r={selected?.r === player.r ? 5.5 : 4} fill={selected?.r === player.r ? "#ffffff" : color} opacity={selected && selected.r !== player.r ? .38 : .9} style={{ filter: `drop-shadow(0 0 ${selected?.r === player.r ? 7 : 3}px ${color})` }} onClick={() => onSelect(player)} className="cursor-pointer outline-none" tabIndex={0} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") onSelect(player); }}><title>{player.p}: {player.w.toFixed(1)}% over {player.g} games</title></circle>;
        })}
      </svg>
      <div className="flex gap-4 text-[0.62rem] uppercase tracking-[0.12em] text-faint"><span className="text-emerald-300">Median</span><span className="text-violet-300">Average</span></div>
    </div>
  );
}

function Scatter({ players, selected, onSelect }: { players: AnalyticsPlayer[]; selected: AnalyticsPlayer | null; onSelect: (player: AnalyticsPlayer) => void }) {
  const width = 640;
  const height = 190;
  const maxGames = Math.max(...players.map((player) => player.g));
  const minWr = Math.floor(Math.min(...players.map((player) => player.w)) - 3);
  const maxWr = Math.ceil(Math.max(...players.map((player) => player.w)) + 3);
  const x = (games: number) => 38 + (Math.log1p(games) / Math.log1p(maxGames)) * (width - 58);
  const y = (wr: number) => 12 + ((maxWr - wr) / Math.max(1, maxWr - minWr)) * (height - 42);
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-auto w-full" role="img" aria-label="Win rate versus games played">
      {[0, .25, .5, .75, 1].map((step) => <line key={step} x1="38" x2={width - 20} y1={12 + step * (height - 42)} y2={12 + step * (height - 42)} stroke="rgba(255,255,255,.055)" />)}
      <text x="38" y={height - 5} fill="#7e8da6" fontSize="10">games →</text>
      {players.map((player, index) => { const color = ["#72a7ff", "#78e3d4", "#a88dff", "#f2ca72"][index % 4]; return <circle key={`${player.r}-${player.p}`} cx={x(player.g)} cy={y(player.w)} r={selected?.r === player.r ? 6 : 4.2} fill={selected?.r === player.r ? "#ffffff" : color} opacity={selected && selected.r !== player.r ? .35 : .82} style={{ filter: `drop-shadow(0 0 ${selected?.r === player.r ? 7 : 3}px ${color})` }} onClick={() => onSelect(player)} className="cursor-pointer" tabIndex={0} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") onSelect(player); }}><title>{player.p}: {player.w.toFixed(1)}% · {player.g} games</title></circle>; })}
    </svg>
  );
}

function PlayerReadout({ player, fallback }: { player: AnalyticsPlayer | null; fallback: string }) {
  return <p className="mt-2 min-h-5 truncate text-xs text-muted">{player ? <><span className="font-semibold text-text">#{player.r} {player.p}</span> · {player.w.toFixed(1)}% · {player.g} games</> : fallback}</p>;
}

function RegionBars({ regions }: { regions: RegionPoint[] }) {
  const valid = regions.filter((region) => region.value != null) as { label: string; value: number }[];
  if (!valid.length) return <p className="py-10 text-center text-sm text-muted">Regional samples are still being collected.</p>;
  const max = Math.max(...valid.map((region) => region.value), 1);
  const min = Math.min(...valid.map((region) => region.value));
  const colors: Record<string, string> = { EU: "linear-gradient(90deg,#4f83ec,#72a7ff)", NA: "linear-gradient(90deg,#35b99f,#78e3d4)", CN: "linear-gradient(90deg,#d85f88,#a88dff)" };
  return <div className="space-y-4">{regions.map((region) => <div key={region.label} className="grid grid-cols-[2rem_1fr_3.5rem] items-center gap-3"><span className="text-xs font-semibold text-muted">{region.label}</span><div className="h-2.5 overflow-hidden rounded-full bg-white/[0.055]"><span className="block h-full rounded-full shadow-[0_0_12px_rgba(114,167,255,.35)]" style={{ width: region.value == null ? "0%" : `${18 + ((region.value - min) / Math.max(1, max - min)) * 82}%`, background: colors[region.label] ?? colors.EU }} /></div><span className="text-right text-sm font-semibold text-text">{region.value == null ? "–" : `${region.value.toFixed(1)}%`}</span></div>)}</div>;
}

function MetricRow({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  return <div className="flex items-center justify-between gap-3 border-b border-white/[0.06] pb-2 text-sm last:border-0"><span className="text-muted">{label}</span><strong className={accent ? "text-emerald-300" : "text-text"}>{value}</strong></div>;
}

function BandBars({ bands }: { bands: { label: string; value: number | null }[] }) {
  const values = bands.map((band) => band.value ?? 0);
  const max = Math.max(...values, 1);
  const populated = values.filter(Boolean);
  const min = populated.length ? Math.min(...populated) : 0;
  const fills = ["linear-gradient(to top,#3f6ac7,#72a7ff)", "linear-gradient(to top,#5272d8,#a88dff)", "linear-gradient(to top,#279f8c,#78e3d4)", "linear-gradient(to top,#b78634,#f2ca72)"];
  return <div className="grid h-40 grid-cols-4 items-end gap-3">{bands.map((band, index) => <div key={band.label} className="flex h-full flex-col justify-end text-center"><span className="mb-2 text-xs font-semibold text-text">{band.value == null ? "–" : `${band.value.toFixed(1)}%`}</span><span className="mx-auto w-full max-w-14 rounded-t-xl shadow-[0_0_18px_rgba(93,161,235,.24)]" style={{ height: band.value == null ? "0%" : `${32 + ((band.value - min) / Math.max(1, max - min)) * 62}%`, background: fills[index] }} /><span className="mt-2 text-[0.65rem] font-semibold text-muted">{band.label}</span></div>)}</div>;
}

function Momentum({ current, delta }: { current: number; delta: number }) {
  const previous = current - delta;
  const up = delta >= 0;
  return <div><svg viewBox="0 0 320 120" className="h-auto w-full" role="img" aria-label="Win rate change since the previous collection"><defs><linearGradient id="momentum" x1="0" x2="1"><stop stopColor="#657ce5"/><stop offset="1" stopColor={up ? "#73e3d1" : "#ff8293"}/></linearGradient></defs><line x1="18" x2="302" y1="94" y2="94" stroke="rgba(255,255,255,.08)"/><path d={`M24 ${up ? 76 : 38} C92 ${up ? 72 : 44} 130 ${up ? 60 : 58} 172 ${up ? 62 : 54} S250 ${up ? 32 : 74} 296 ${up ? 24 : 86}`} fill="none" stroke="url(#momentum)" strokeWidth="4" strokeLinecap="round"/><circle cx="24" cy={up ? 76 : 38} r="5" fill="#657ce5"/><circle cx="296" cy={up ? 24 : 86} r="6" fill={up ? "#73e3d1" : "#ff8293"}/></svg><div className="flex items-center justify-between text-xs"><span className="text-muted">Previous <b className="text-text">{previous.toFixed(1)}%</b></span><span className={up ? "text-emerald-300" : "text-bad"}>Current <b>{current.toFixed(1)}%</b></span></div></div>;
}
