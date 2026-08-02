"use client";

/* eslint-disable @next/next/no-img-element -- champion icons come from external CDNs */

import { useState } from "react";
import type {
  TierCount, HistBin, ScatterPoint, HeatRow,
} from "@/lib/meta-stats";

// Lightweight, dependency-free SVG charts for the Meta Report. Everything is a
// plain <svg> with a viewBox so it scales fluidly; the only interactivity is
// hover highlighting and the scatter's role filter.

const TIER_COLOR: Record<string, string> = {
  GOD: "#ff9d3c", S: "#ff7f3a", A: "#f3b400", B: "#4f8dff", C: "#8a92a6", Ass: "#4a5266",
};
const GRID = "rgba(255,255,255,0.08)";
const AXIS = "rgba(255,255,255,0.45)";

function niceExtent(vals: number[], pad: number): [number, number] {
  return [Math.floor(Math.min(...vals) - pad), Math.ceil(Math.max(...vals) + pad)];
}

/* ------------------------------------------------------------------ scatter */

const ROLE_DOT: Record<string, string> = {
  Baron: "#ff8f5a", Jungle: "#5fd08a", Mid: "#5b9dff", Dragon: "#ffd45a", Support: "#c78bff",
};

export function MetaScatter({ points }: { points: ScatterPoint[] }) {
  const [role, setRole] = useState<string>("All");
  const [hover, setHover] = useState<ScatterPoint | null>(null);

  const roles = ["All", ...Array.from(new Set(points.map((p) => p.role)))];

  const W = 820, H = 470;
  const m = { top: 24, right: 20, bottom: 46, left: 46 };
  const iw = W - m.left - m.right;
  const ih = H - m.top - m.bottom;

  const [wrLo, wrHi] = niceExtent(points.map((p) => p.wr), 0.5);
  const gLo = Math.log10(Math.max(100, Math.min(...points.map((p) => p.games))));
  const gHi = Math.log10(Math.max(...points.map((p) => p.games)));

  const x = (g: number) => m.left + ((Math.log10(g) - gLo) / (gHi - gLo)) * iw;
  const y = (wr: number) => m.top + (1 - (wr - wrLo) / (wrHi - wrLo)) * ih;
  const cMin = Math.min(...points.map((p) => p.ceiling));
  const cMax = Math.max(...points.map((p) => p.ceiling));
  const r = (c: number) => 4 + ((c - cMin) / (cMax - cMin || 1)) * 6;

  const yTicks: number[] = [];
  for (let v = Math.ceil(wrLo); v <= wrHi; v++) yTicks.push(v);
  const xTicks = [500, 1000, 2500, 5000, 10000, 25000, 50000].filter(
    (v) => Math.log10(v) >= gLo && Math.log10(v) <= gHi,
  );
  const fmtGames = (v: number) => (v >= 1000 ? `${v / 1000}k` : `${v}`);

  const dim = (p: ScatterPoint) => role !== "All" && p.role !== role;

  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-1.5">
        {roles.map((rn) => (
          <button
            key={rn}
            onClick={() => setRole(rn)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition ${
              role === rn ? "bg-accent text-[#07121f]" : "bg-white/[0.05] text-muted hover:text-text"
            }`}
          >
            {rn}
          </button>
        ))}
      </div>

      <div className="relative">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Win rate versus games played">
          {/* y grid + labels */}
          {yTicks.map((v) => (
            <g key={`y${v}`}>
              <line x1={m.left} x2={W - m.right} y1={y(v)} y2={y(v)} stroke={v === 50 ? "rgba(255,255,255,0.25)" : GRID} strokeDasharray={v === 50 ? "4 4" : undefined} />
              <text x={m.left - 8} y={y(v) + 3} textAnchor="end" fontSize="10" fill={AXIS}>{v}%</text>
            </g>
          ))}
          {/* x labels */}
          {xTicks.map((v) => (
            <text key={`x${v}`} x={x(v)} y={H - m.bottom + 16} textAnchor="middle" fontSize="10" fill={AXIS}>{fmtGames(v)}</text>
          ))}
          <text x={m.left + iw / 2} y={H - 6} textAnchor="middle" fontSize="11" fill={AXIS}>Games played (log scale)</text>
          <text x={-(m.top + ih / 2)} y={14} transform="rotate(-90)" textAnchor="middle" fontSize="11" fill={AXIS}>Win rate</text>

          {/* points: visible mark + an invisible, larger hit target so hover
              never requires landing dead-center on a 4px dot */}
          {points.map((p) => (
            <g key={p.slug}
              onMouseEnter={() => setHover(p)} onMouseLeave={() => setHover(null)}
              className="cursor-pointer">
              <circle
                cx={x(p.games)} cy={y(p.wr)} r={hover?.slug === p.slug ? r(p.ceiling) + 2 : r(p.ceiling)}
                fill={TIER_COLOR[p.tier]} fillOpacity={dim(p) ? 0.12 : 0.82}
                stroke={hover?.slug === p.slug ? "#fff" : "rgba(0,0,0,0.35)"} strokeWidth={hover?.slug === p.slug ? 1.5 : 0.6}
                className="transition-[r]"
              />
              <circle cx={x(p.games)} cy={y(p.wr)} r={Math.max(12, r(p.ceiling) + 4)} fill="transparent" />
            </g>
          ))}
        </svg>

        {hover && (
          <div className="pointer-events-none absolute left-1/2 top-2 -translate-x-1/2 rounded-lg border border-line bg-[#0e1322] px-3 py-1.5 text-xs shadow-xl">
            <span className="font-semibold text-text">{hover.name}</span>
            <span className="text-muted"> · {hover.role} · {hover.wr.toFixed(1)}% WR · {hover.ceiling.toFixed(0)}% ceiling · {hover.games.toLocaleString()} games</span>
          </div>
        )}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-faint">
        <span>Bubble size = skill ceiling.</span>
        <span className="inline-flex items-center gap-3">
          {(["GOD", "S", "A", "B", "C", "Ass"] as const).map((t) => (
            <span key={t} className="inline-flex items-center gap-1">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: TIER_COLOR[t] }} />
              {t === "Ass" ? "L" : t}
            </span>
          ))}
        </span>
      </div>
    </div>
  );
}

/* --------------------------------------------------------------- tier bars */

export function TierBars({ rows }: { rows: TierCount[] }) {
  const max = Math.max(...rows.map((r) => r.count));
  return (
    <div className="flex flex-col gap-2.5">
      {rows.map((r) => (
        <div key={r.tier} className="flex items-center gap-3">
          <span className="w-7 shrink-0 text-sm font-bold" style={{ color: TIER_COLOR[r.tier] }}>{r.label}</span>
          <div className="h-5 flex-1 overflow-hidden rounded-md bg-white/[0.05]">
            <div className="flex h-full items-center rounded-md pl-2 text-[0.7rem] font-semibold text-black/80"
              style={{ width: `${Math.max(6, (r.count / max) * 100)}%`, background: TIER_COLOR[r.tier] }}>
              {r.count}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

/* -------------------------------------------------------------- heatmap */

export function RoleTierHeatmap({ rows }: { rows: HeatRow[] }) {
  const tiers = rows[0]?.cells ?? [];
  // ONE sequential scale for the whole grid (single hue, more = darker), so any
  // two cells are comparable. Per-row normalization made "20" in one row look
  // like "7" in another.
  const globalMax = Math.max(1, ...rows.flatMap((r) => r.cells.map((cc) => cc.count)));
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-separate border-spacing-1 text-center text-xs">
        <thead>
          <tr>
            <th className="text-left font-medium text-faint"></th>
            {tiers.map((t) => (
              <th key={t.tier} className="pb-1 font-bold" style={{ color: TIER_COLOR[t.tier] }}>{t.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.role}>
              <td className="pr-2 text-left font-medium text-muted">{row.role}</td>
              {row.cells.map((cc) => {
                const t = cc.count / globalMax; // 0..1 on the shared scale
                return (
                  <td key={cc.tier}>
                    <div
                      className="grid h-9 place-items-center rounded-md font-semibold"
                      title={`${row.role} · ${cc.label} tier: ${cc.count} champion${cc.count === 1 ? "" : "s"}`}
                      style={{
                        background: cc.count === 0
                          ? "rgba(255,255,255,0.03)"
                          : `rgba(79,141,255,${0.15 + 0.85 * t})`,
                        color: cc.count === 0
                          ? "rgba(255,255,255,0.25)"
                          : t > 0.55 ? "#07121f" : "rgba(255,255,255,0.9)",
                      }}
                    >
                      {cc.count || ""}
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ------------------------------------------------------------- histogram */

export function WrHistogram({ bins }: { bins: HistBin[] }) {
  const max = Math.max(...bins.map((b) => b.count));
  const W = 640, H = 220, pad = 28;
  const bw = (W - pad * 2) / bins.length;
  const color = (mid: number) => (mid >= 50 ? "var(--color-accent)" : "var(--color-bad)");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Win rate distribution">
      {bins.map((b, i) => {
        const h = (b.count / max) * (H - pad * 2);
        const bx = pad + i * bw;
        return (
          <g key={i}>
            <rect x={bx + 1} y={H - pad - h} width={bw - 2} height={h} rx="2" fill={color(b.mid)} fillOpacity={0.8}>
              <title>{`${b.lo}-${b.hi}%: ${b.count} champions`}</title>
            </rect>
            {b.count > 0 && <text x={bx + bw / 2} y={H - pad - h - 4} textAnchor="middle" fontSize="9" fill={AXIS}>{b.count}</text>}
            {b.lo % 2 === 0 && <text x={bx} y={H - pad + 13} textAnchor="middle" fontSize="9" fill={AXIS}>{b.lo}</text>}
          </g>
        );
      })}
      <line x1={pad} x2={W - pad} y1={H - pad} y2={H - pad} stroke={GRID} />
    </svg>
  );
}

/* --------------------------------------------------------------- simple bars */

export function ValueBars({ rows, unit = "%", accentTop = true }: { rows: { label: string; value: number }[]; unit?: string; accentTop?: boolean }) {
  const max = Math.max(...rows.map((r) => r.value));
  const min = Math.min(...rows.map((r) => r.value));
  const span = max - min || 1;
  return (
    <div className="flex flex-col gap-3">
      {rows.map((r) => {
        const lead = accentTop && r.value === max;
        const pct = ((r.value - min) / span) * 100;
        return (
          <div key={r.label} className="flex items-center gap-3">
            <span className="w-20 shrink-0 text-sm font-medium">{r.label}</span>
            <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
              <div className="h-full rounded-full" style={{ width: `${Math.max(6, pct)}%`, background: lead ? "var(--color-accent)" : "rgba(255,255,255,0.28)" }} />
            </div>
            <span className={`w-14 text-right text-sm font-semibold ${lead ? "text-accent" : "text-muted"}`}>{r.value.toFixed(1)}{unit}</span>
          </div>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------- elo-skew dumbbell */

export type SkewRow = {
  slug: string; name: string; icon: string; role: string;
  low: number;   // win rate in the Diamond+ bracket
  high: number;  // win rate in the Challenger bracket
  skew: number;  // high - low
};

const UP = "#4ade80";    // climbs with elo (site-wide "up" color)
const DOWN = "#fb7185";  // falls off at the top

/**
 * Dumbbell: each champion's win rate at Diamond+ (hollow dot) vs Challenger
 * (filled dot), on ONE shared axis so slopes are comparable. The signed delta
 * is direct-labeled on every row (this doubles as the CVD-safe secondary
 * encoding for the green/red pair, alongside the two spatially separate groups).
 */
function DumbbellRow({ r, color, pct, active, onHover }: {
  r: SkewRow; color: string; pct: (v: number) => number;
  active: boolean; onHover: (slug: string | null) => void;
}) {
  const a = pct(r.low), b = pct(r.high);
  const [left, right] = a < b ? [a, b] : [b, a];
  return (
    <div
      className={`flex items-center gap-3 rounded-lg px-2 py-1.5 transition ${active ? "bg-white/[0.05]" : ""}`}
      onMouseEnter={() => onHover(r.slug)} onMouseLeave={() => onHover(null)}
    >
      <span className="h-7 w-7 shrink-0 overflow-hidden rounded-full ring-1 ring-white/10">
        <img src={r.icon} alt="" width={28} height={28} loading="lazy" className="h-full w-full scale-[1.12] object-cover" />
      </span>
      <span className="w-24 shrink-0 truncate text-sm font-medium sm:w-28">{r.name}</span>
      <div className="relative h-7 flex-1">
        {/* 50% reference */}
        <span className="absolute inset-y-0 w-px bg-white/15" style={{ left: `${pct(50)}%` }} />
        {/* connector */}
        <span
          className="absolute top-1/2 h-[3px] -translate-y-1/2 rounded-full"
          style={{ left: `${left}%`, width: `${Math.max(0.5, right - left)}%`, background: color, opacity: active ? 0.9 : 0.55 }}
        />
        {/* Diamond+ (start): hollow */}
        <span
          className="absolute top-1/2 h-[9px] w-[9px] -translate-x-1/2 -translate-y-1/2 rounded-full border-2 bg-bg"
          style={{ left: `${a}%`, borderColor: color }}
        />
        {/* Challenger (end): filled */}
        <span
          className="absolute top-1/2 h-[11px] w-[11px] -translate-x-1/2 -translate-y-1/2 rounded-full"
          style={{ left: `${b}%`, background: color, boxShadow: "0 0 0 2px rgba(7,10,18,0.9)" }}
        />
        {/* values on hover */}
        {active && (
          <span className="absolute -top-1.5 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-md border border-line bg-[#0e1322] px-2 py-0.5 text-[0.68rem] text-muted shadow-xl">
            Diamond+ {r.low.toFixed(1)}% → Challenger {r.high.toFixed(1)}%
          </span>
        )}
      </div>
      <span className="w-12 shrink-0 text-right text-sm font-semibold tabular-nums" style={{ color }}>
        {r.skew > 0 ? "+" : "−"}{Math.abs(r.skew).toFixed(1)}
      </span>
    </div>
  );
}

// margins mirror the DumbbellRow layout exactly (px-2 + icon 28px + gap-3 +
// name w-24/sm:w-28 + gap-3 left; gap-3 + delta w-12 + px-2 right), so the
// tick labels sit precisely under the shared track column.
function DumbbellAxis({ lo, hi, pct }: { lo: number; hi: number; pct: (v: number) => number }) {
  return (
    <div className="relative ml-[9.75rem] mr-[4.25rem] mt-1 h-4 text-[0.65rem] text-faint sm:ml-[10.75rem]">
      <span className="absolute -translate-x-1/2" style={{ left: "0%" }}>{lo}%</span>
      <span className="absolute -translate-x-1/2" style={{ left: `${pct(50)}%` }}>50%</span>
      <span className="absolute -translate-x-1/2" style={{ left: "100%" }}>{hi}%</span>
    </div>
  );
}

export function SkewDumbbell({ climbers, fallers }: { climbers: SkewRow[]; fallers: SkewRow[] }) {
  const [hover, setHover] = useState<string | null>(null);
  const all = [...climbers, ...fallers];
  const lo = Math.floor(Math.min(50, ...all.flatMap((r) => [r.low, r.high])) - 1);
  const hi = Math.ceil(Math.max(50, ...all.flatMap((r) => [r.low, r.high])) + 1);
  const pct = (v: number) => ((v - lo) / (hi - lo)) * 100;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-muted">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-[9px] w-[9px] rounded-full border-2 border-white/60" /> Diamond+ bracket
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-[9px] w-[9px] rounded-full bg-white/70" /> Challenger bracket
        </span>
        <span className="text-faint">Same axis for every row · vertical line marks 50%</span>
      </div>

      <div className="grid gap-8 lg:grid-cols-2">
        <div>
          <p className="mb-2 text-sm font-semibold text-emerald-300">Scales with elo · win rate climbs at the top</p>
          <div className="flex flex-col gap-0.5">
            {climbers.map((r) => (
              <DumbbellRow key={r.slug} r={r} color={UP} pct={pct} active={hover === r.slug} onHover={setHover} />
            ))}
          </div>
          <DumbbellAxis lo={lo} hi={hi} pct={pct} />
        </div>
        <div>
          <p className="mb-2 text-sm font-semibold text-rose-300">Falls off · strong low, fades vs the best</p>
          <div className="flex flex-col gap-0.5">
            {fallers.map((r) => (
              <DumbbellRow key={r.slug} r={r} color={DOWN} pct={pct} active={hover === r.slug} onHover={setHover} />
            ))}
          </div>
          <DumbbellAxis lo={lo} hi={hi} pct={pct} />
        </div>
      </div>
    </div>
  );
}

export { TIER_COLOR, ROLE_DOT };
