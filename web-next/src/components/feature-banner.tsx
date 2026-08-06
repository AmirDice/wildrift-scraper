"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { BUILD_TOOLS_LIVE } from "@/lib/flags";

// Top-of-page highlight for the newest feature. Dismissible (remembered in
// localStorage) so it grabs attention once without nagging forever. Bump the
// key when a new feature should re-surface it for everyone.
//
// While the build tools are held back, the banner promotes the Meta Report
// instead; when they launch it flips to advertising them (and re-surfaces via
// its own dismiss key).
const FLAG_PROMO = BUILD_TOOLS_LIVE
  ? {
      // The two headline facts of this release in one line: the EU win rates
      // are freshly collected (the full roster, this patch) and the Build
      // Studio is open. Key bumped to v5 so people who dismissed the old
      // banner see this one once.
      key: "wtm-feature-builders-v5",
      href: "/build",
      lead: "EU win rates & Build Studio are live",
      body: "fresh top-50 win rates for every champion, and a generator that builds around how you play.",
      hideOn: ["/build", "/counter"],  // /counter redirects into /build
      badges: ["New"],
      cta: "Try it",
    }
  : {
      key: "wtm-feature-meta-report-v1",
      href: "/meta",
      lead: "New: Meta Overview",
      body: "maps the whole meta in charts, tier splits, win rate by class and role, and a win-rate-vs-popularity map of every champion.",
      hideOn: ["/meta"],
      badges: ["New"],
      cta: "See it",
    };

// The "EU data refresh incoming" countdown banner that used to override this
// was removed 2026-08-06, the day the refresh shipped -- the full roster is
// collected and live, which is exactly what the current banner announces.
const PROMO = FLAG_PROMO;
const DISMISS_KEY = PROMO.key;
// pages the banner points at -- no reason to show it there
const HIDE_ON = PROMO.hideOn;

function SparklesGlyph() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
      <path d="M18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456z" />
      <path d="M16.894 20.567L16.5 21.75l-.394-1.183a2.25 2.25 0 00-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 001.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 001.423 1.423l1.183.394-1.183.394a2.25 2.25 0 00-1.423 1.423z" />
    </svg>
  );
}

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
function Marquee({ text, className = "" }: { text: string; className?: string }) {
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
        <span ref={copy} className="whitespace-nowrap text-muted">{text}</span>
        {/* Second copy trails the first so the loop never shows a gap at the
            end. Hidden from assistive tech, which should hear the sentence once. */}
        {moving && (
          <span aria-hidden className="whitespace-nowrap text-muted"
            style={{ paddingLeft: MARQUEE_GAP }}>
            {text}
          </span>
        )}
      </div>
    </div>
  );
}

export function FeatureBanner() {
  const pathname = usePathname();
  const [show, setShow] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || localStorage.getItem(DISMISS_KEY)) return;
    const frame = requestAnimationFrame(() => setShow(true));
    return () => cancelAnimationFrame(frame);
  }, []);

  // never show on the pages it points to
  if (!show || HIDE_ON.includes(pathname)) return null;

  const dismiss = () => {
    try { localStorage.setItem(DISMISS_KEY, "1"); } catch { /* ignore */ }
    setShow(false);
  };

  return (
    <div className="relative overflow-hidden border-b border-emerald-400/25 bg-gradient-to-r from-accent/20 via-emerald-400/15 to-accent/20">
      {/* moving sheen to draw the eye */}
      <div aria-hidden className="pointer-events-none absolute inset-y-0 -left-1/3 w-1/3 skew-x-[-20deg] bg-white/10 blur-md motion-safe:animate-[sheen_3.5s_ease-in-out_infinite]" />
      {/* Wraps on a phone: the headline and the buttons hold the first row and
          the sentence gets the whole of the second, because sharing one row
          left it about 70px to scroll through, which is unreadable. From sm up
          there is room for everything on one line. */}
      <div className="relative mx-auto flex max-w-6xl flex-wrap items-center gap-x-2.5 gap-y-1 px-5 py-2 text-sm sm:flex-nowrap sm:gap-3">
        <span className="text-emerald-300 motion-safe:animate-pulse"><SparklesGlyph /></span>
        <span className="hidden shrink-0 items-center gap-1 sm:inline-flex">
          {PROMO.badges.map((badge, i) => (
            <span
              key={badge}
              className={
                i === 0
                  ? "rounded bg-emerald-400/20 px-1.5 py-0.5 text-[0.6rem] font-bold uppercase tracking-wide text-emerald-300"
                  : "rounded bg-gold/20 px-1.5 py-0.5 text-[0.6rem] font-bold uppercase tracking-wide text-gold"
              }
            >
              {badge}
            </span>
          ))}
        </span>
        <span className="shrink-0 whitespace-nowrap font-semibold text-text">
          {PROMO.lead}
        </span>
        <Marquee
          text={PROMO.body}
          className="order-last w-full sm:order-none sm:w-auto sm:flex-1"
        />
        <Link
          href={PROMO.href}
          className="ml-auto inline-flex shrink-0 items-center gap-1 rounded-lg bg-emerald-400 px-3 py-1 text-xs font-bold text-black transition hover:brightness-110 sm:ml-0"
        >
          {PROMO.cta} <span aria-hidden>→</span>
        </Link>
        <button
          onClick={dismiss}
          aria-label="Dismiss announcement"
          className="grid h-6 w-6 shrink-0 place-items-center rounded-md text-muted transition hover:bg-white/10 hover:text-text"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
            <line x1="6" y1="6" x2="18" y2="18" />
            <line x1="18" y1="6" x2="6" y2="18" />
          </svg>
        </button>
      </div>
    </div>
  );
}
