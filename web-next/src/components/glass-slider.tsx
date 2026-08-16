"use client";

import { useRef, useState } from "react";

/**
 * A slider that feels like one. The native range input renders the OS widget:
 * tiny track, themed thumb, hard snapping between stops mid-drag -- which
 * reads as "broken" rather than "discrete". This one drags as a smooth float
 * and animates onto the nearest stop on release, so the hand gets a slider
 * and the caller still gets an integer. A real (invisible) range input stays
 * in the tree for keyboard and screen readers; the pointer never touches it.
 *
 * Two looks:
 * - "fill": a plain progression (the Lab's level slider) -- an accent fill
 *   growing from the left up to the thumb.
 * - "bias": a lean between two poles -- a blue-into-gold gradient track with
 *   a dot per stop, and the thumb ringed in the colour of the side it sits on.
 */
export function GlassSlider({
  min,
  max,
  value,
  onDrag,
  onCommit,
  ariaLabel,
  ariaValueText,
  variant = "fill",
  ticks = false,
}: {
  min: number;
  max: number;
  /** Committed integer stop. */
  value: number;
  /** Fired with the nearest stop while dragging, so labels track the thumb. */
  onDrag: (v: number) => void;
  /** Fired once on release / keyboard settle with the final stop. */
  onCommit: (v: number) => void;
  ariaLabel: string;
  ariaValueText?: string;
  variant?: "fill" | "bias";
  /** Draw a dot per stop. Right for five stops, noise for fifteen. */
  ticks?: boolean;
}) {
  const trackRef = useRef<HTMLDivElement>(null);
  // Float position while a pointer drag is live; null otherwise. The thumb
  // rides the float during the drag and animates to the snapped stop after.
  const [drag, setDrag] = useState<number | null>(null);
  const span = Math.max(max - min, 1);
  const visual = drag ?? value;
  const pct = ((visual - min) / span) * 100;
  const rounded = Math.round(visual);
  const mid = (min + max) / 2;
  // Only the bias look colours by side; fill is always the accent.
  const side = variant !== "bias" ? "low" : rounded === mid ? "center" : rounded > mid ? "high" : "low";

  const posFrom = (clientX: number) => {
    const rect = trackRef.current!.getBoundingClientRect();
    const x = Math.min(Math.max(clientX - rect.left, 0), rect.width);
    return rect.width ? min + (x / rect.width) * span : min;
  };
  const start = (e: React.PointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture?.(e.pointerId);
    const p = posFrom(e.clientX);
    setDrag(p);
    onDrag(Math.round(p));
  };
  const move = (e: React.PointerEvent<HTMLDivElement>) => {
    if (drag === null) return;
    const p = posFrom(e.clientX);
    setDrag(p);
    onDrag(Math.round(p));
  };
  const end = () => {
    if (drag === null) return;
    const v = Math.round(drag);
    setDrag(null);
    onCommit(v);
  };

  return (
    <div
      ref={trackRef}
      onPointerDown={start}
      onPointerMove={move}
      onPointerUp={end}
      onPointerCancel={end}
      className="relative min-w-0 flex-1 cursor-pointer touch-none select-none py-2.5"
    >
      {/* keyboard / screen-reader path; the pointer is handled by the div */}
      <input
        type="range" min={min} max={max} step={1} value={value}
        onChange={(e) => onDrag(Number(e.target.value))}
        onKeyUp={(e) => onCommit(Number((e.target as HTMLInputElement).value))}
        onBlur={(e) => onCommit(Number(e.target.value))}
        aria-label={ariaLabel} aria-valuetext={ariaValueText}
        className="peer pointer-events-none absolute inset-0 h-full w-full opacity-0"
      />
      {variant === "bias" ? (
        <div className="h-1.5 rounded-full bg-gradient-to-r from-accent/70 via-white/[0.14] to-gold/70 ring-1 ring-white/10" />
      ) : (
        <>
          <div className="h-1.5 rounded-full bg-white/[0.08] ring-1 ring-white/10" />
          <div
            className="absolute top-1/2 left-0 h-1.5 -translate-y-1/2 rounded-full bg-gradient-to-r from-accent/50 to-accent"
            style={{ width: `${pct}%` }}
          />
        </>
      )}
      {ticks && Array.from({ length: span + 1 }, (_, i) => min + i).map((stop) => (
        <span
          key={stop}
          aria-hidden
          className={`absolute top-1/2 h-[7px] w-[7px] -translate-x-1/2 -translate-y-1/2 rounded-full transition ${
            variant === "bias" && stop === mid ? "h-[9px] w-[9px] bg-white/50" : "bg-white/30"} ${
            rounded === stop ? "opacity-0" : "opacity-100"}`}
          style={{ left: `${((stop - min) / span) * 100}%` }}
        />
      ))}
      {/* thumb: exact under the finger while dragging, animates onto the stop after */}
      <span
        aria-hidden
        className={`absolute top-1/2 z-10 h-[18px] w-[18px] -translate-x-1/2 -translate-y-1/2 rounded-full border-2 bg-[#0e1322]/90 shadow-lg backdrop-blur transition-transform peer-focus-visible:ring-2 peer-focus-visible:ring-accent/70 ${
          drag !== null ? "scale-125" : "scale-100"} ${
          side === "high" ? "border-gold shadow-gold/30" : side === "low" ? "border-accent shadow-accent/30" : "border-white/50 shadow-black/40"}`}
        style={{
          left: `${pct}%`,
          transition: drag === null
            ? "left 180ms cubic-bezier(0.22, 1, 0.36, 1), transform 120ms ease"
            : "transform 120ms ease",
        }}
      >
        <span className={`absolute inset-[3px] rounded-full ${
          side === "high" ? "bg-gold" : side === "low" ? "bg-accent" : "bg-white/70"}`} />
      </span>
    </div>
  );
}
