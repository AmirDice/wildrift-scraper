"use client";

import { useEffect, useRef, useState } from "react";
import { monteCarlo, monteCarloCompare, type MonteCarloResult, type MonteCarloCompare } from "@/lib/engine";

const TARGETS: { key: string; label: string }[] = [
  { key: "adc", label: "ADC" }, { key: "mage", label: "Mage" },
  { key: "fighter", label: "Fighter" }, { key: "bruiser", label: "Bruiser" },
  { key: "tank", label: "Tank" },
];

/** Histogram of kill-times: x = seconds to kill (left = faster), bar height =
 *  how many of the simulated fights landed in that time bucket; the line marks
 *  the average. Shared x-axis so two builds can be compared directly. */
function Histogram({ r, color, span, showAxis }: { r: MonteCarloResult; color: string; span: [number, number]; showAxis?: boolean }) {
  const [lo, hi] = span;
  const bins = 14;
  const width = (hi - lo) / bins || 1;
  const counts = new Array(bins).fill(0);
  for (const s of r.samples) {
    const idx = Math.min(bins - 1, Math.max(0, Math.floor((s - lo) / width)));
    counts[idx]++;
  }
  const peak = Math.max(1, ...counts);
  const meanPct = ((r.meanTtk - lo) / (hi - lo || 1)) * 100;
  const clampedMean = Math.min(100, Math.max(0, meanPct));
  return (
    <div>
      <div className="relative flex h-16 items-end gap-[2px]" title="Taller bar = more fights killed in that time">
        {counts.map((c, i) => (
          <div key={i} className={`flex-1 rounded-sm ${color}`} style={{ height: `${(c / peak) * 100}%`, opacity: 0.85 }} />
        ))}
        {/* average marker */}
        <div className="absolute inset-y-0 w-px bg-white" style={{ left: `${clampedMean}%` }} />
        <div className="absolute -top-1 -translate-x-1/2 rounded bg-white px-1 text-[0.55rem] font-bold text-black" style={{ left: `${clampedMean}%` }}>
          avg {r.meanTtk.toFixed(1)}s
        </div>
      </div>
      {showAxis && (
        <div className="mt-1 flex justify-between text-[0.55rem] text-faint">
          <span>← faster · {lo.toFixed(1)}s</span>
          <span>seconds to kill</span>
          <span>{hi.toFixed(1)}s · slower →</span>
        </div>
      )}
    </div>
  );
}

function DistLine({ label, r, cls }: { label: string; r: MonteCarloResult; cls: string }) {
  return (
    <div className="flex items-baseline justify-between text-xs">
      <span className={`font-semibold ${cls}`}>{label}</span>
      <span className="text-muted">
        mean <span className="font-semibold text-text">{r.meanTtk.toFixed(2)}s</span>
        {" · "}95% CI {r.ci95[0].toFixed(2)}–{r.ci95[1].toFixed(2)}s
        {" · "}range {r.bestTtk.toFixed(2)}–{r.worstTtk.toFixed(2)}s
      </span>
    </div>
  );
}

/** Monte Carlo head-to-head: races the edited build vs the recommended one over
 *  hundreds of randomized fights (crit rolls, misses, timing jitter). */
export function MonteCarloComparePanel({
  name, current, base, currentLabel = "Your build", baseLabel = "Recommended",
}: {
  name: string;
  current: { items: string[]; runes: string[] };
  base: { items: string[]; runes: string[] };
  currentLabel?: string;
  baseLabel?: string;
}) {
  const [targetKind, setTargetKind] = useState("bruiser");
  const [res, setRes] = useState<MonteCarloCompare | null>(null);
  const [solo, setSolo] = useState<MonteCarloResult | null>(null);
  const [running, setRunning] = useState(false);
  const mounted = useRef(true);
  useEffect(() => () => { mounted.current = false; }, []);

  // only a head-to-head when the build actually differs from the recommended
  const edited = current.items.join(",") !== base.items.join(",")
    || current.runes.join(",") !== base.runes.join(",");

  const run = () => {
    setRunning(true);
    // defer so the button can show its running state before the sync compute
    setTimeout(() => {
      if (!mounted.current) return;
      if (edited) {
        setRes(monteCarloCompare({ name, ...current }, { name, ...base }, { targetKind, trials: 400 }));
        setSolo(null);
      } else {
        setSolo(monteCarlo(name, current.items, current.runes, { targetKind, trials: 400 }));
        setRes(null);
      }
      setRunning(false);
    }, 20);
  };

  const span: [number, number] | null = res
    ? [Math.min(res.a.bestTtk, res.b.bestTtk), Math.max(res.a.worstTtk, res.b.worstTtk)]
    : solo ? [solo.bestTtk, solo.worstTtk] : null;
  const winA = res?.winRateA ?? 0;

  return (
    <div className="glass mt-4 rounded-2xl p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <p className="text-[0.65rem] font-bold uppercase tracking-wide text-faint">
          Monte Carlo · {edited ? `${currentLabel} vs ${baseLabel}` : "kill-time distribution"}
        </p>
        <div className="flex items-center gap-1 rounded-lg border border-line bg-white/[0.03] p-0.5">
          {TARGETS.map((t) => (
            <button
              key={t.key}
              onClick={() => { setTargetKind(t.key); setRes(null); setSolo(null); }}
              className={`rounded-md px-2 py-1 text-[0.7rem] font-semibold transition ${
                targetKind === t.key ? "bg-accent/20 text-accent" : "text-muted hover:text-text"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <button
        onClick={run}
        disabled={running}
        className="w-full rounded-lg bg-accent/15 py-2 text-sm font-semibold text-accent transition hover:bg-accent/25 disabled:opacity-60"
      >
        {running ? "Simulating 400 fights…" : res ? "Re-run simulation" : `Run 400-fight simulation vs ${TARGETS.find((t) => t.key === targetKind)?.label}`}
      </button>

      {res && span && (
        <div className="mt-4">
          {/* headline win-rate */}
          <div className="mb-4 text-center">
            <div className={`text-3xl font-bold ${winA >= 50 ? "text-emerald-300" : "text-bad"}`}>{winA}%</div>
            <div className="text-xs text-muted">
              of fights, <span className="font-semibold text-text">{currentLabel}</span> secures the kill first
              {winA >= 50 ? " (edit is better)" : " (recommended is better)"}
            </div>
          </div>

          <p className="mb-2 text-center text-[0.65rem] text-muted">
            Each build fought a {TARGETS.find((t) => t.key === targetKind)?.label} {res.a.trials} times with random crits, misses and timing.
            Bars show how often the kill took a given time — <span className="text-text">a bar pile further left means faster kills</span>.
          </p>
          {/* distributions on a shared axis */}
          <div className="space-y-3">
            <div>
              <DistLine label={currentLabel} r={res.a} cls="text-accent" />
              <Histogram r={res.a} color="bg-accent" span={span} />
            </div>
            <div>
              <DistLine label={baseLabel} r={res.b} cls="text-gold" />
              <Histogram r={res.b} color="bg-gold" span={span} showAxis />
            </div>
          </div>
        </div>
      )}

      {solo && span && (
        <div className="mt-4">
          <div className="mb-3 text-center">
            <div className="text-3xl font-bold text-gold">{solo.meanTtk.toFixed(2)}s</div>
            <div className="text-xs text-muted">
              average time to kill a {TARGETS.find((t) => t.key === targetKind)?.label}
              {" · "}95% of fights land {solo.ci95[0].toFixed(2)}–{solo.ci95[1].toFixed(2)}s
            </div>
          </div>
          <p className="mb-2 text-center text-[0.65rem] text-muted">
            {solo.trials} fights with random crits, misses and timing. Bars show how often the kill took a given time.
          </p>
          <DistLine label="This build" r={solo} cls="text-gold" />
          <Histogram r={solo} color="bg-gold" span={span} showAxis />
          <p className="mt-2 text-center text-[0.65rem] text-faint">
            Edit an item or rune to race your version against this build.
          </p>
        </div>
      )}
    </div>
  );
}
