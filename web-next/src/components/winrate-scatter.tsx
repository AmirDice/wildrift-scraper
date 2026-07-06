"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { Champion } from "@/lib/data";

const TIER_COLOR: Record<string, string> = {
  GOD: "#ffd76e",
  S: "#7fd1ff",
  A: "#4f8dff",
  B: "#8aa0c0",
  C: "#6b7890",
  Ass: "#ff6a6a",
};

const W = 820;
const H = 540;
const M = { l: 56, r: 24, t: 28, b: 54 };

export function WinrateScatter({ champions }: { champions: Champion[] }) {
  const pts = useMemo(
    () =>
      champions
        .filter((c) => c.skillSpread != null)
        .map((c) => ({ c, x: c.wr, y: c.skillSpread as number })),
    [champions]
  );
  const [hover, setHover] = useState<string | null>(null);

  const geom = useMemo(() => {
    const xs = pts.map((p) => p.x);
    const ys = pts.map((p) => p.y);
    const xMin = Math.min(...xs) - 0.5;
    const xMax = Math.max(...xs) + 0.5;
    const yMax = Math.max(...ys) + 2;
    const sx = (v: number) => M.l + ((v - xMin) / (xMax - xMin)) * (W - M.l - M.r);
    const sy = (v: number) => H - M.b - (v / yMax) * (H - M.t - M.b);
    const medY = [...ys].sort((a, b) => a - b)[Math.floor(ys.length / 2)];
    return { xMin, xMax, yMax, sx, sy, medY };
  }, [pts]);

  const { sx, sy, medY, yMax } = geom;
  const xTicks = [46, 48, 50, 52, 54, 56].filter((t) => t >= geom.xMin && t <= geom.xMax);
  const yTicks = [0, 10, 20, 30, 40].filter((t) => t <= yMax);
  const hoveredPt = pts.find((p) => p.c.slug === hover);

  return (
    <div className="glass rounded-2xl p-4 sm:p-6">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Win rate vs skill ceiling scatter">
        {/* grid + ticks */}
        {xTicks.map((t) => (
          <g key={`x${t}`}>
            <line x1={sx(t)} y1={M.t} x2={sx(t)} y2={H - M.b} stroke="rgba(255,255,255,0.05)" />
            <text x={sx(t)} y={H - M.b + 18} textAnchor="middle" className="fill-faint" fontSize="11">
              {t}%
            </text>
          </g>
        ))}
        {yTicks.map((t) => (
          <g key={`y${t}`}>
            <line x1={M.l} y1={sy(t)} x2={W - M.r} y2={sy(t)} stroke="rgba(255,255,255,0.05)" />
            <text x={M.l - 8} y={sy(t) + 4} textAnchor="end" className="fill-faint" fontSize="11">
              {t}
            </text>
          </g>
        ))}

        {/* reference lines: 50% WR (average) + median skill ceiling */}
        <line x1={sx(50)} y1={M.t} x2={sx(50)} y2={H - M.b} stroke="#4f8dff" strokeDasharray="4 4" strokeOpacity="0.5" />
        <line x1={M.l} y1={sy(medY)} x2={W - M.r} y2={sy(medY)} stroke="#ffffff" strokeDasharray="4 4" strokeOpacity="0.15" />

        {/* quadrant labels */}
        <text x={W - M.r - 6} y={M.t + 14} textAnchor="end" className="fill-faint" fontSize="10.5">
          strong · rewards mastery →
        </text>
        <text x={W - M.r - 6} y={H - M.b - 8} textAnchor="end" className="fill-faint" fontSize="10.5">
          strong · consistent
        </text>
        <text x={M.l + 6} y={M.t + 14} className="fill-faint" fontSize="10.5">
          weak · high-variance
        </text>

        {/* dots */}
        {pts.map((p) => {
          const on = p.c.slug === hover;
          return (
            <circle
              key={p.c.slug}
              cx={sx(p.x)}
              cy={sy(p.y)}
              r={on ? 7 : 4.5}
              fill={TIER_COLOR[p.c.tier] ?? "#8aa0c0"}
              fillOpacity={hover && !on ? 0.35 : 0.9}
              stroke={on ? "#fff" : "none"}
              strokeWidth={1.5}
              onMouseEnter={() => setHover(p.c.slug)}
              onMouseLeave={() => setHover(null)}
              style={{ cursor: "pointer", transition: "r 0.1s, fill-opacity 0.1s" }}
            />
          );
        })}

        {/* hovered label */}
        {hoveredPt && (
          <g pointerEvents="none">
            <text
              x={Math.min(sx(hoveredPt.x) + 10, W - M.r - 120)}
              y={sy(hoveredPt.y) - 10}
              className="fill-text"
              fontSize="13"
              fontWeight="600"
            >
              {hoveredPt.c.name}
            </text>
            <text
              x={Math.min(sx(hoveredPt.x) + 10, W - M.r - 120)}
              y={sy(hoveredPt.y) + 6}
              className="fill-muted"
              fontSize="11"
            >
              {hoveredPt.x.toFixed(1)}% · ceiling +{hoveredPt.y.toFixed(1)} · {hoveredPt.c.tier}
            </text>
          </g>
        )}

        {/* axis labels */}
        <text x={(M.l + W - M.r) / 2} y={H - 8} textAnchor="middle" className="fill-muted" fontSize="12">
          Win rate (relative — 50% = average champion)
        </text>
        <text
          transform={`translate(16 ${(M.t + H - M.b) / 2}) rotate(-90)`}
          textAnchor="middle"
          className="fill-muted"
          fontSize="12"
        >
          Skill ceiling (best main − average)
        </text>
      </svg>

      {hoveredPt && (
        <div className="mt-2 text-center text-sm">
          <Link href={`/champions/${hoveredPt.c.slug}`} className="text-accent hover:underline">
            Open {hoveredPt.c.name} →
          </Link>
        </div>
      )}
    </div>
  );
}
