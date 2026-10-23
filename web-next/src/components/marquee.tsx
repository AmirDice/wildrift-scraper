"use client";

import { useEffect, useRef, useState } from "react";

/** Pixels per second the sentence travels. Slow enough to read on a phone. */
const MARQUEE_SPEED = 45;
/** Blank space between the end of one copy of the sentence and the next. */
const MARQUEE_GAP = 48;

/**
 * Scrolls `text` horizontally, but only when it does not fit.
 *
 * The banner used to `truncate`, which cut the sentence off mid-word on a
 * phone. Scrolling unconditionally would be worse: on a desktop the sentence
 * fits with room to spare, and moving text that had no need to move is just
 * noise. So it is measured, and the animation is attached only when the text is
 * actually wider than the space for it.
 */
export function Marquee({ text, className = "", textClassName = "text-muted" }: { text: string; className?: string; textClassName?: string }) {
  const viewport = useRef<HTMLDivElement>(null);
  const copy = useRef<HTMLSpanElement>(null);
  const [shift, setShift] = useState(0);

  useEffect(() => {
    const outer = viewport.current;
    const inner = copy.current;
    if (!outer || !inner) return;

    const measure = () => {
      const available = outer.clientWidth;
      // getBoundingClientRect, NOT scrollWidth: the sentence is an inline
      // element, and scrollWidth reports 0 for those, so the overflow check
      // silently never fired.
      const needed = inner.getBoundingClientRect().width;
      setShift(needed > available ? needed + MARQUEE_GAP : 0);
    };
    measure();

    const observer = new ResizeObserver(measure);
    observer.observe(outer);
    observer.observe(inner);
    return () => observer.disconnect();
  }, [text]);

  const moving = shift > 0;

  return (
    <div ref={viewport} className={`min-w-0 overflow-hidden ${className}`}>
      <div
        className={
          moving
            ? "flex w-max motion-safe:animate-[marquee_linear_infinite] hover:[animation-play-state:paused]"
            : "truncate"
        }
        style={moving
          ? {
              ["--marquee-shift" as string]: `${shift}px`,
              animationDuration: `${shift / MARQUEE_SPEED}s`,
            }
          : undefined}
      >
        <span ref={copy} className={`whitespace-nowrap ${textClassName}`} title={moving ? undefined : text}>{text}</span>
        {/* Second copy trails the first so the loop never shows a gap at the
            end. Hidden from assistive tech, which should hear the sentence once. */}
        {moving && (
          <span aria-hidden className={`whitespace-nowrap ${textClassName}`}
            style={{ paddingLeft: MARQUEE_GAP }}>
            {text}
          </span>
        )}
      </div>
    </div>
  );
}
