import type { BracketPoint } from "@/lib/skew";

const UP = "#4ade80"; // emerald
const DOWN = "#fb7185"; // rose
const FLAT = "#8aa0b6"; // muted

function color(skew: number) {
  if (skew >= 2) return UP;
  if (skew <= -2) return DOWN;
  return FLAT;
}

/**
 * Win-rate-across-rank curve. Compact sparkline for tables (labeled=false, fixed
 * domain so slopes are comparable between champions) or a labelled chart for the
 * champion page (labeled=true, auto-scaled to the champion's own range).
 */
export function BracketCurve({
  curve,
  skew,
  labeled = false,
  width = 96,
  height = 34,
  className = "",
}: {
  curve: BracketPoint[];
  skew: number;
  labeled?: boolean;
  width?: number;
  height?: number;
  className?: string;
}) {
  const c = color(skew);
  const wrs = curve.map((p) => p.wr);
  const padX = labeled ? 34 : 3;
  const padTop = labeled ? 14 : 5;
  const padBot = labeled ? 22 : 5;

  const [dMin, dMax] = labeled
    ? (() => {
        const lo = Math.min(50, ...wrs) - 1;
        const hi = Math.max(50, ...wrs) + 1;
        return [lo, hi];
      })()
    : [43, 57];

  const x = (i: number) => padX + (i / (curve.length - 1)) * (width - padX - (labeled ? 8 : padX));
  const y = (wr: number) => {
    const t = (Math.max(dMin, Math.min(dMax, wr)) - dMin) / (dMax - dMin || 1);
    return height - padBot - t * (height - padTop - padBot);
  };
  const y50 = y(50);
  const pts = curve.map((p, i) => `${x(i)},${y(p.wr)}`).join(" ");

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className={`overflow-visible ${className}`}>
      {/* 50% reference */}
      <line x1={padX} y1={y50} x2={width - (labeled ? 8 : padX)} y2={y50} stroke="rgba(255,255,255,0.14)" strokeWidth="1" strokeDasharray="3 3" />
      {labeled && (
        <text x={padX - 6} y={y50} textAnchor="end" dominantBaseline="middle" className="fill-faint" fontSize="9">
          50
        </text>
      )}
      {/* curve */}
      <polyline points={pts} fill="none" stroke={c} strokeWidth={labeled ? 2.5 : 2} strokeLinejoin="round" strokeLinecap="round" />
      {curve.map((p, i) => (
        <g key={p.key}>
          <circle cx={x(i)} cy={y(p.wr)} r={labeled ? 3.5 : 2.4} fill={c} />
          {labeled && (
            <>
              <text x={x(i)} y={y(p.wr) - 8} textAnchor="middle" className="fill-text" fontSize="10" fontWeight="600">
                {p.wr.toFixed(1)}
              </text>
              <text x={x(i)} y={height - 6} textAnchor="middle" className="fill-faint" fontSize="9">
                {p.short}
              </text>
            </>
          )}
        </g>
      ))}
    </svg>
  );
}
