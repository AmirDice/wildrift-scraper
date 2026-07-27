"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { track } from "@/components/share-build";

export interface TourStep {
  /** Value of the data-tour attribute on the element to spotlight. Steps whose
   *  target is missing still show, just without a spotlight. */
  target?: string;
  title: string;
  body: string;
  /** Marks a step as covering a control the player can ignore entirely. Badged
   *  in the card so nobody reads the tour as a required checklist. */
  optional?: boolean;
}

type Rect = { top: number; left: number; width: number; height: number };

const PADDING = 8;
/** Smallest gap the card keeps from the viewport edge. */
const MARGIN = 16;
/** Gap between the spotlight and the card when they sit side by side. */
const GAP = 12;

function rectFor(target: string | undefined): Rect | null {
  if (!target || typeof document === "undefined") return null;
  const node = document.querySelector<HTMLElement>(`[data-tour="${target}"]`);
  if (!node) return null;
  const box = node.getBoundingClientRect();
  if (box.width === 0 && box.height === 0) return null;
  return {
    top: box.top - PADDING,
    left: box.left - PADDING,
    width: box.width + PADDING * 2,
    height: box.height + PADDING * 2,
  };
}

/**
 * First-run guided tour for the build tools.
 *
 * Walks through the page one control at a time, dimming everything else. Runs
 * once per storage key (bump the key when the tool changes shape), can be
 * skipped at any step, and can be replayed from the "Tour" button that stays in
 * the corner afterwards.
 */
export function BuildTour({
  storageKey,
  steps,
  label = "Tour",
}: {
  storageKey: string;
  steps: TourStep[];
  label?: string;
}) {
  const [index, setIndex] = useState<number | null>(null);
  const [rect, setRect] = useState<Rect | null>(null);

  const open = index != null;
  const step = open ? steps[index] : null;

  // First visit: start on the next frame, once the page has laid out.
  useEffect(() => {
    let seen = true;
    try {
      seen = localStorage.getItem(storageKey) === "1";
    } catch {
      /* storage unavailable: treat as seen so we never nag in a loop */
    }
    if (seen) return;
    const timer = window.setTimeout(() => {
      setIndex(0);
      track("tour_started");
    }, 600);
    return () => window.clearTimeout(timer);
  }, [storageKey]);

  // Track the spotlight to its target across scroll, resize and step changes.
  useEffect(() => {
    if (!open || !step) return;
    const node = step.target
      ? document.querySelector<HTMLElement>(`[data-tour="${step.target}"]`)
      : null;
    node?.scrollIntoView({ behavior: "smooth", block: "center" });

    const update = () => setRect(rectFor(step.target));
    update();
    const raf = window.setTimeout(update, 350); // after the smooth scroll settles
    window.addEventListener("scroll", update, true);
    window.addEventListener("resize", update);
    return () => {
      window.clearTimeout(raf);
      window.removeEventListener("scroll", update, true);
      window.removeEventListener("resize", update);
    };
  }, [open, step]);

  const finish = useCallback(
    (reason: "completed" | "skipped") => {
      try {
        localStorage.setItem(storageKey, "1");
      } catch {
        /* ignore */
      }
      track(reason === "completed" ? "tour_completed" : "tour_skipped");
      setIndex(null);
      setRect(null);
    },
    [storageKey],
  );

  // Escape skips, arrow keys move.
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") finish("skipped");
      if (event.key === "ArrowRight") setIndex((current) => (current == null ? current : Math.min(steps.length - 1, current + 1)));
      if (event.key === "ArrowLeft") setIndex((current) => (current == null ? current : Math.max(0, current - 1)));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, finish, steps.length]);

  const restart = () => {
    setIndex(0);
    track("tour_started");
  };

  return (
    <>
      <button
        onClick={restart}
        className="fixed bottom-4 right-[4.5rem] z-40 grid h-11 place-items-center rounded-full border border-line bg-[#0e1322]/90 px-4 text-xs font-bold text-accent shadow-2xl backdrop-blur transition hover:border-accent/60"
      >
        {label}
      </button>

      {open && step && (
        <div className="fixed inset-0 z-[60]" role="dialog" aria-modal="true" aria-label="Guided tour">
          {/* The dim is a giant spread shadow around the spotlight, so the
              highlighted control stays fully interactive-looking and crisp. */}
          {rect ? (
            <div
              className="pointer-events-none absolute rounded-xl ring-2 ring-accent/70 transition-all duration-200"
              style={{
                top: rect.top,
                left: rect.left,
                width: rect.width,
                height: rect.height,
                boxShadow: "0 0 0 9999px rgba(3, 6, 14, 0.74)",
              }}
            />
          ) : (
            <div className="absolute inset-0 bg-[#03060e]/74" />
          )}

          <TourCard
            rect={rect}
            step={step}
            index={index!}
            total={steps.length}
            onSkip={() => finish("skipped")}
            onBack={() => setIndex((current) => Math.max(0, (current ?? 0) - 1))}
            onNext={() => {
              if (index! >= steps.length - 1) finish("completed");
              else setIndex(index! + 1);
            }}
          />
        </div>
      )}
    </>
  );
}

/** Viewport height, tracking the mobile URL bar via visualViewport when present. */
function useViewportHeight(): number {
  const [height, setHeight] = useState(() =>
    typeof window === "undefined" ? 800 : window.visualViewport?.height ?? window.innerHeight);

  useEffect(() => {
    const update = () =>
      setHeight(window.visualViewport?.height ?? window.innerHeight);
    update();
    const vv = window.visualViewport;
    vv?.addEventListener("resize", update);
    window.addEventListener("resize", update);
    window.addEventListener("orientationchange", update);
    return () => {
      vv?.removeEventListener("resize", update);
      window.removeEventListener("resize", update);
      window.removeEventListener("orientationchange", update);
    };
  }, []);

  return height;
}

function TourCard({
  rect, step, index, total, onSkip, onBack, onNext,
}: {
  rect: Rect | null;
  step: TourStep;
  index: number;
  total: number;
  onSkip: () => void;
  onBack: () => void;
  onNext: () => void;
}) {
  const card = useRef<HTMLDivElement>(null);
  const viewportHeight = useViewportHeight();
  const [cardHeight, setCardHeight] = useState(0);

  // The card has to be MEASURED, not assumed. Its height swings from ~150px to
  // over 300px with the length of the body copy, and the old code hard-coded
  // 220px: anything taller ran off the bottom, and a target near the top of the
  // screen pushed the card off the TOP, which is how a step could show with its
  // heading cut off.
  useLayoutEffect(() => {
    const node = card.current;
    if (!node) return;
    const measure = () => setCardHeight(node.getBoundingClientRect().height);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, [step]);

  const maxHeight = Math.max(120, viewportHeight - MARGIN * 2);
  // Before the first measurement, assume the worst so the opening frame is
  // never the one that overflows.
  const height = Math.min(cardHeight || maxHeight, maxHeight);

  let top: number;
  if (!rect) {
    top = (viewportHeight - height) / 2;
  } else {
    const belowTop = rect.top + rect.height + GAP;
    const aboveTop = rect.top - GAP - height;
    if (belowTop + height <= viewportHeight - MARGIN) {
      top = belowTop;
    } else if (aboveTop >= MARGIN) {
      top = aboveTop;
    } else {
      // Neither side fits. Overlapping the spotlight is the lesser evil against
      // clipping the text, so sit on whichever side has more room and let the
      // clamp below keep the whole card on screen.
      const roomBelow = viewportHeight - (rect.top + rect.height);
      top = roomBelow >= rect.top ? viewportHeight - MARGIN - height : MARGIN;
    }
  }
  // The invariant: whatever the branch above decided, the card is on screen.
  top = Math.min(Math.max(top, MARGIN), Math.max(MARGIN, viewportHeight - MARGIN - height));

  const style: React.CSSProperties = {
    position: "absolute",
    top,
    left: MARGIN,
    right: MARGIN,
    margin: "0 auto",
    maxWidth: 380,
    // A card longer than the screen (small phone, long step) scrolls inside
    // itself rather than losing its bottom half.
    maxHeight,
    overflowY: "auto",
  };

  return (
    <div ref={card} style={style} className="glass-menu rounded-2xl p-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[0.6rem] font-bold uppercase tracking-wide text-faint">
          Step {index + 1} of {total}
        </p>
        <button onClick={onSkip} className="text-xs font-medium text-muted transition hover:text-text">
          Skip tour
        </button>
      </div>
      <h3 className="mt-1.5 flex flex-wrap items-center gap-2 text-base font-bold text-text">
        {step.title}
        {step.optional && (
          <span className="rounded-full border border-line bg-white/[0.06] px-2 py-0.5 text-[0.6rem] font-bold uppercase tracking-wide text-faint">
            Optional
          </span>
        )}
      </h3>
      <p className="mt-1 text-sm leading-relaxed text-muted">{step.body}</p>
      <div className="mt-3 flex items-center gap-2">
        {index > 0 && (
          <button onClick={onBack} className="rounded-lg border border-line px-3 py-1.5 text-xs font-semibold text-muted transition hover:text-text">
            Back
          </button>
        )}
        <button onClick={onNext} className="ml-auto rounded-lg bg-accent px-4 py-1.5 text-xs font-bold text-black transition hover:opacity-90">
          {index >= total - 1 ? "Got it" : "Next"}
        </button>
      </div>
    </div>
  );
}
