"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { BUILD_TOOLS_LIVE } from "@/lib/flags";

// Top-of-page highlight for the newest feature. Dismissible (remembered in
// localStorage) so it grabs attention once without nagging forever. Bump the
// key when a new feature should re-surface it for everyone.
//
// While the build tools are held back, the banner promotes the Meta Report
// instead; when they launch it flips to advertising them (and re-surfaces via
// its own dismiss key).
const PROMO = BUILD_TOOLS_LIVE
  ? {
      // One tool, not two: "Build Optimizer & Counter Builder are live:
      // generate a full build, runes and item order for any champion or
      // matchup" wrapped to three lines on a phone and buried the point.
      // The Counter Builder is one tab away once they arrive.
      key: "wtm-feature-builders-v4",
      href: "/build",
      title: "Build Studio",
      body: " is live: generate by playstyle, or craft builds with live item, rune and ability stats.",
      hideOn: ["/build", "/counter"],
    }
  : {
      key: "wtm-feature-meta-report-v1",
      href: "/meta",
      title: "New: Meta Report",
      body: " maps the whole meta in charts, tier splits, win rate by class and role, and a win-rate-vs-popularity map of every champion.",
      hideOn: ["/meta"],
    };
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
      <div className="relative mx-auto flex max-w-6xl items-center gap-2.5 px-5 py-2 text-sm sm:gap-3">
        <span className="text-emerald-300 motion-safe:animate-pulse"><SparklesGlyph /></span>
        <span className="hidden shrink-0 items-center gap-1 sm:inline-flex">
          <span className="rounded bg-emerald-400/20 px-1.5 py-0.5 text-[0.6rem] font-bold uppercase tracking-wide text-emerald-300">
            New
          </span>
          <span className="rounded bg-gold/20 px-1.5 py-0.5 text-[0.6rem] font-bold uppercase tracking-wide text-gold">
            Beta
          </span>
        </span>
        <p className="min-w-0 flex-1 truncate">
          <span className="font-semibold text-text">{PROMO.title}</span>
          <span className="text-muted">{PROMO.body}</span>
        </p>
        <Link
          href={PROMO.href}
          className="inline-flex shrink-0 items-center gap-1 rounded-lg bg-emerald-400 px-3 py-1 text-xs font-bold text-black transition hover:brightness-110"
        >
          Try it <span aria-hidden>→</span>
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
