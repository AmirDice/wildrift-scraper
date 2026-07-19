"use client";

import { useState } from "react";
import type {
  TierCount, HistBin, ScatterPoint, ClassStat, RoleStat, HeatRow, DifficultyStat,
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

          {/* points */}
          {points.map((p) => (
            <circle
              key={p.slug}
              cx={x(p.games)} cy={y(p.wr)} r={hover?.slug === p.slug ? r(p.ceiling) + 2 : r(p.ceiling)}
              fill={TIER_COLOR[p.tier]} fillOpacity={dim(p) ? 0.12 : 0.82}
              stroke={hover?.slug === p.slug ? "#fff" : "rgba(0,0,0,0.35)"} strokeWidth={hover?.slug === p.slug ? 1.5 : 0.6}
              onMouseEnter={() => setHover(p)} onMouseLeave={() => setHover(null)}
              className="cursor-pointer transition-[r]"
            />
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

/* ------------------------------------------------------------- class radar */

export function ClassRadar({ rows }: { rows: ClassStat[] }) {
  const S = 300, c = S / 2, R = 108;
  const n = rows.length;
  const [lo, hi] = niceExtent(rows.map((r) => r.wr), 0.4);
  const norm = (wr: number) => (wr - lo) / (hi - lo);
  const angle = (i: number) => (Math.PI * 2 * i) / n - Math.PI / 2;
  const pt = (i: number, rad: number) => [c + Math.cos(angle(i)) * rad, c + Math.sin(angle(i)) * rad];

  const rings = [0.25, 0.5, 0.75, 1];
  const poly = rows.map((r, i) => pt(i, norm(r.wr) * R).join(",")).join(" ");

  return (
    <svg viewBox={`0 0 ${S} ${S}`} className="mx-auto w-full max-w-[320px]" role="img" aria-label="Win rate by class radar">
      {rings.map((rr) => (
        <polygon key={rr} points={rows.map((_, i) => pt(i, rr * R).join(",")).join(" ")} fill="none" stroke={GRID} />
      ))}
      {rows.map((_, i) => {
        const [ex, ey] = pt(i, R);
        return <line key={i} x1={c} y1={c} x2={ex} y2={ey} stroke={GRID} />;
      })}
      <polygon points={poly} fill="rgba(79,141,255,0.22)" stroke="var(--color-accent)" strokeWidth="2" />
      {rows.map((r, i) => {
        const [px, py] = pt(i, norm(r.wr) * R);
        const [lx, ly] = pt(i, R + 20);
        return (
          <g key={r.class}>
            <circle cx={px} cy={py} r="3.5" fill="var(--color-accent)" />
            <text x={lx} y={ly} textAnchor="middle" fontSize="10.5" fill={AXIS}>{r.class}</text>
            <text x={lx} y={ly + 12} textAnchor="middle" fontSize="9.5" fill="rgba(255,255,255,0.7)" fontWeight="600">{r.wr.toFixed(1)}%</text>
          </g>
        );
      })}
    </svg>
  );
}

/* -------------------------------------------------------------- heatmap */

export function RoleTierHeatmap({ rows }: { rows: HeatRow[] }) {
  const tiers = rows[0]?.cells ?? [];
  const maxInRow = (row: HeatRow) => Math.max(1, ...row.cells.map((cc) => cc.count));
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
          {rows.map((row) => {
            const mx = maxInRow(row);
            return (
              <tr key={row.role}>
                <td className="pr-2 text-left font-medium text-muted">{row.role}</td>
                {row.cells.map((cc) => (
                  <td key={cc.tier}>
                    <div
                      className="grid h-9 place-items-center rounded-md font-semibold"
                      style={{
                        background: cc.count === 0 ? "rgba(255,255,255,0.03)" : TIER_COLOR[cc.tier],
                        opacity: cc.count === 0 ? 1 : 0.28 + 0.72 * (cc.count / mx),
                        color: cc.count === 0 ? "rgba(255,255,255,0.25)" : "rgba(0,0,0,0.82)",
                      }}
                    >
                      {cc.count || ""}
                    </div>
                  </td>
                ))}
              </tr>
            );
          })}
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

/* ---------------------------------------------------- difficulty vs win rate */

export function DifficultyBars({ rows }: { rows: DifficultyStat[] }) {
  const max = Math.max(...rows.map((r) => r.wr));
  const min = Math.min(...rows.map((r) => r.wr));
  const span = max - min || 1;
  return (
    <div className="flex flex-col gap-3">
      {rows.map((r) => {
        const pct = ((r.wr - min) / span) * 100;
        return (
          <div key={r.difficulty} className="flex items-center gap-3">
            <span className="w-24 shrink-0 text-sm font-medium">{r.difficulty}</span>
            <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
              <div className="h-full rounded-full bg-gold" style={{ width: `${Math.max(6, pct)}%` }} />
            </div>
            <span className="w-24 text-right text-xs text-muted">{r.wr.toFixed(1)}% · {r.nChampions}</span>
          </div>
        );
      })}
    </div>
  );
}

export { TIER_COLOR, ROLE_DOT };
