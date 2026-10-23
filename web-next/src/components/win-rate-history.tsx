"use client";

import { useMemo, useState } from "react";
import type { Point, WinRateHistory as History } from "@/lib/wr-history";
import { REGION_LONG, useRegionScope, type Region } from "@/components/region-scope";

/**
 * A champion's win rate across collections. The selected server is drawn
 * bold, the others faint behind it for context, and balance patches are
 * marked where they landed. China adds Tencent's daily all-ranked line, which
 * measures every game rather than the top players, so it is dashed and
 * labelled as a different thing.
 */
const W = 640;
const H = 230;
const PAD = { l: 34, r: 14, t: 22, b: 26 };
const SERIES: { key: Region; label: string; tone: string }[] = [
  { key: "global", label: "Global", tone: "text-accent" },
  { key: "eu", label: "EU", tone: "text-sky-300" },
  { key: "na", label: "NA", tone: "text-rose-300" },
  { key: "cn", label: "CN", tone: "text-gold" },
];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const day = (date: string) => Date.parse(`${date}T00:00:00Z`) / 86_400_000;
const round = (value: number) => Math.round(value * 10) / 10;
const shortDate = (date: string) => `${Number(date.slice(8, 10))} ${MONTHS[Number(date.slice(5, 7)) - 1]}`;

export function WinRateHistory({ champion, history }: { champion: string; history: History }) {
  const region = useRegionScope()?.region ?? "global";
  const [hover, setHover] = useState<{ key: string; point: Point } | null>(null);

  const ladder: Record<Region, Point[]> = { global: history.global, eu: history.eu, na: history.na, cn: history.cn };
  const primary = ladder[region];
  const daily = region === "cn" ? history.daily : [];

  const frame = useMemo(() => {
    const all = [...history.global, ...history.eu, ...history.na, ...history.cn, ...daily];
    if (!all.length) return null;
    const x0 = Math.min(...all.map(([d]) => day(d)));
    const x1 = Math.max(...all.map(([d]) => day(d)));
    const values = all.map(([, wr]) => wr);
    const lo = Math.floor((Math.min(...values) - 1) / 2) * 2;
    const hi = Math.ceil((Math.max(...values) + 1) / 2) * 2;
    const x = (date: string) => round(PAD.l + ((day(date) - x0) / Math.max(1, x1 - x0)) * (W - PAD.l - PAD.r));
    const y = (wr: number) => round(PAD.t + ((hi - wr) / Math.max(1, hi - lo)) * (H - PAD.t - PAD.b));
    const step = hi - lo > 16 ? 4 : 2;
    const ticks: number[] = [];
    for (let v = lo; v <= hi; v += step) ticks.push(v);
    // Month starts across the window, for the x axis.
    const months: { date: string; label: string }[] = [];
    const start = new Date(x0 * 86_400_000);
    for (let m = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + 1, 1)); day(m.toISOString().slice(0, 10)) <= x1; m = new Date(Date.UTC(m.getUTCFullYear(), m.getUTCMonth() + 1, 1))) {
      months.push({ date: m.toISOString().slice(0, 10), label: MONTHS[m.getUTCMonth()] });
    }
    return { x, y, ticks, months, from: new Date(x0 * 86_400_000).toISOString().slice(0, 10) };
  }, [history, daily]);

  if (!frame || !primary.length) {
    return (
      <article className="rounded-2xl border border-white/[0.09] bg-black/20 p-5">
        <h2 className="text-base font-semibold">Win rate over time</h2>
        <p className="mt-2 text-sm text-muted">{`No ${REGION_LONG[region]} history for ${champion} yet.`}</p>
      </article>
    );
  }

  // `gap` lifts the pen across missing days, so a week with no data is not
  // drawn as a straight-line move.
  const path = (points: Point[], gap = Infinity) => points.map(([d, wr], i) =>
    `${i && day(d) - day(points[i - 1][0]) <= gap ? "L" : "M"}${frame.x(d)} ${frame.y(wr)}`).join(" ");
  const now = primary[primary.length - 1];
  const before = primary.length > 1 ? primary[primary.length - 2] : null;
  const delta = before ? round(now[1] - before[1]) : null;
  const patches = history.patches.filter((p) => p.kind === "balance" && p.date >= frame.from);

  return (
    <article className="relative overflow-hidden rounded-2xl border border-white/[0.09] bg-[linear-gradient(145deg,rgba(214,231,255,.065),rgba(49,83,138,.025)),rgba(7,14,27,.82)] p-4 shadow-[inset_0_1px_rgba(255,255,255,.1)] sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold sm:text-base">{champion} win rate over time</h2>
          <p className="mt-0.5 text-xs text-faint">
            {`${REGION_LONG[region]} top-player boards, one point per collection${region === "cn" && daily.length ? ", plus Tencent's daily rate over every ranked game in China" : ""}.`}
          </p>
        </div>
        <div className="text-right">
          <p className="text-lg font-semibold tabular-nums text-accent">{now[1].toFixed(1)}%</p>
          {delta != null && before && (
            <p className={`text-xs tabular-nums ${delta > 0 ? "text-emerald-300" : delta < 0 ? "text-rose-300" : "text-muted"}`}>
              {`${delta > 0 ? "+" : ""}${delta.toFixed(1)} since ${shortDate(before[0])}`}
            </p>
          )}
        </div>
      </div>

      <div className="mt-3 overflow-x-auto">
        <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full min-w-[480px]" role="img"
          aria-label={`${champion} ${REGION_LONG[region]} win rate: ${primary.map(([d, wr]) => `${shortDate(d)} ${wr}%`).join(", ")}`}
          onMouseLeave={() => setHover(null)}>
          {frame.ticks.map((t) => (
            <g key={t}>
              <line x1={PAD.l} x2={W - PAD.r} y1={frame.y(t)} y2={frame.y(t)} stroke="currentColor" className={t === 50 ? "text-white/25" : "text-white/[0.06]"} strokeDasharray={t === 50 ? "3 3" : undefined} />
              <text x={PAD.l - 6} y={frame.y(t) + 3} textAnchor="end" className="fill-current text-faint" fontSize="10">{t}%</text>
            </g>
          ))}
          {frame.months.map((m) => (
            <text key={m.date} x={frame.x(m.date)} y={H - 8} textAnchor="middle" className="fill-current text-faint" fontSize="10">{m.label}</text>
          ))}
          {patches.map((p) => (
            <g key={`${p.patch}-${p.date}`}>
              <line x1={frame.x(p.date)} x2={frame.x(p.date)} y1={PAD.t - 4} y2={H - PAD.b} stroke="currentColor" className="text-white/20" strokeDasharray="2 4" />
              <text x={frame.x(p.date)} y={PAD.t - 8} textAnchor="middle" className="fill-current text-muted" fontSize="9">{p.patch}</text>
            </g>
          ))}
          {daily.length > 1 && (
            <path d={path(daily, 3)} fill="none" stroke="currentColor" className="text-gold/60" strokeWidth={1.4} strokeDasharray="4 3" />
          )}
          {SERIES.filter((s) => s.key !== region && ladder[s.key].length > 1).map((s) => (
            <path key={s.key} d={path(ladder[s.key])} fill="none" stroke="currentColor" className={`${s.tone} opacity-25`} strokeWidth={1.5} />
          ))}
          {primary.length > 1 && (
            <path d={path(primary)} fill="none" stroke="currentColor" className={SERIES.find((s) => s.key === region)!.tone} strokeWidth={2.6} strokeLinejoin="round" />
          )}
          {primary.map((point) => (
            <circle key={point[0]} cx={frame.x(point[0])} cy={frame.y(point[1])} r={hover?.point === point ? 5.5 : 4}
              fill="currentColor" className={`${SERIES.find((s) => s.key === region)!.tone} cursor-pointer`}
              stroke="#07101d" strokeWidth={1.5}
              onMouseEnter={() => setHover({ key: region, point })} onClick={() => setHover({ key: region, point })}>
              <title>{`${shortDate(point[0])}: ${point[1].toFixed(1)}%`}</title>
            </circle>
          ))}
          {hover && (
            <g pointerEvents="none">
              <rect x={Math.min(W - PAD.r - 112, Math.max(PAD.l, frame.x(hover.point[0]) - 56))} y={Math.max(2, frame.y(hover.point[1]) - 34)} width={112} height={22} rx={6} fill="#0b1424" stroke="rgba(255,255,255,.14)" />
              <text x={Math.min(W - PAD.r - 56, Math.max(PAD.l + 56, frame.x(hover.point[0])))} y={Math.max(2, frame.y(hover.point[1]) - 34) + 15} textAnchor="middle" fontSize="11" className="fill-current text-text">
                {`${shortDate(hover.point[0])} · ${hover.point[1].toFixed(1)}%`}
              </text>
            </g>
          )}
        </svg>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[0.7rem] text-muted">
        {SERIES.filter((s) => ladder[s.key].length).map((s) => (
          <span key={s.key} className={`flex items-center gap-1.5 ${s.key === region ? "text-text" : ""}`}>
            <span className={`h-0.5 w-4 rounded-full bg-current ${s.tone} ${s.key === region ? "" : "opacity-40"}`} />{s.label}
          </span>
        ))}
        {daily.length > 1 && (
          <span className="flex items-center gap-1.5"><span className="w-4 border-t border-dashed border-gold/70" />China, all ranked games (daily)</span>
        )}
        {patches.length > 0 && <span className="flex items-center gap-1.5"><span className="h-3 border-l border-dashed border-white/40" />Balance patch</span>}
      </div>
      {region === "global" && history.globalServers.some((n) => n < 3) && (
        <p className="mt-2 text-[0.7rem] leading-relaxed text-faint">
          Global averages the latest board each server had at the time. Points before China&rsquo;s first collection are EU and NA only.
        </p>
      )}
    </article>
  );
}
