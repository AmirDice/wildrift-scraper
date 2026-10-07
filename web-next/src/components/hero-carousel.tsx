"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { BUILD_TOOLS_LIVE, DRAFT_TOOL_LIVE } from "@/lib/flags";

/* eslint-disable @next/next/no-img-element */

/**
 * The hero, as a slideshow of what the site actually does.
 *
 * One hero could only ever advertise one thing, and it advertised the build
 * generator: someone who landed here never learned the draft assistant, the
 * counter builder or the overlay existed unless they scrolled. Each feature
 * now gets the first screen in turn, with a picture of itself.
 *
 * EVERY SLIDE IS IN THE DOM, ALWAYS. They are stacked in one grid cell, so the
 * hero is as tall as its tallest slide and nothing jumps when it advances --
 * and a crawler reads all of them whether or not it runs the timer. Only the
 * visible one is reachable: `inert` takes the rest out of the tab order and
 * off the accessibility tree.
 *
 * The first slide is server-rendered visible, so the largest paint is text
 * that is already there rather than something a timer produces.
 *
 * THE SHOTS ARE REAL. Every screenshot in here was taken from the running tool
 * (scripted in Chrome, with the site chrome hidden and the wallpaper swapped
 * for a flat ground, so a picture of the site does not end up sitting on top
 * of the same painting), except the overlay's, which is the Android app's own
 * screen. Replacing one is a matter of dropping a new file into public/shots
 * under the same name.
 */

/** Four and a half seconds a slide, and it never stops.
 *
 *  One second was tried and was too fast to read a headline in. This is long
 *  enough to take one in and glance at the picture, and short enough that all
 *  five come round inside a visit. Every slide gets the full dwell, including
 *  one somebody picked by hand -- the timer restarts on each change rather
 *  than running on a fixed drumbeat, so a manual jump is never cut short.
 *
 *  It pauses for the pointer, for keyboard focus, for a finger on the panel
 *  and for a backgrounded tab. Nothing else stops it. */
const ROTATE_MS = 4500;

interface Shot {
  src: string;
  alt: string;
  /** A phone screen rather than a page: fitted into the frame, not filling it. */
  tall?: boolean;
}

interface Slide {
  id: string;
  eyebrow: string;
  /** The <em> is the accent-coloured phrase, not italics. */
  title: ReactNode;
  body: string;
  claims: string[];
  primary: { href: string; label: string };
  secondary?: { href: string; label: string };
  shot: Shot;
}

/** The slides, in the order a new visitor should meet them: what the site
 *  generates, what it generates against, what it does live in a lobby, and
 *  where that is going next. */
function slides(): Slide[] {
  const out: Slide[] = [];
  if (BUILD_TOOLS_LIVE) {
    out.push({
      id: "build",
      eyebrow: "Builds reasoned, not repeated",
      title: <>Build for <em className="not-italic text-accent">this game</em> - not every game.</>,
      body:
        "Stop copying the same build every match. Generate a personalized Wild Rift build for your "
        + "champion, role, playstyle, and enemy team backed by current patch data and real "
        + "top-player win rates.",
      claims: ["AI-powered reasoning", "Rule-checked", "Explained item by item"],
      primary: { href: "/build?tab=generate", label: "Generate my build" },
      secondary: { href: "/build", label: "Open Build Studio" },
      shot: { src: "/shots/build.jpg", alt: "The Build Studio, with the personal build generator open on Hecarim" },
    });
    out.push({
      id: "counter",
      eyebrow: "Counter builder",
      title: <>Build against <em className="not-italic text-emerald-300">their five</em>, item by item.</>,
      body:
        "Name your champion and the five you are up against, and get the items, runes and purchase "
        + "order shaped to beat exactly those picks, each with the reason it is there.",
      claims: ["Reads their whole comp", "Measured in the fight engine", "Every swap explained"],
      primary: { href: "/build?tab=counter", label: "Build vs enemy team" },
      secondary: { href: "/counter", label: "See how it reads a comp" },
      shot: { src: "/shots/counter.jpg", alt: "The Build vs Enemy Team tab, with five enemy slots to fill" },
    });
  } else {
    out.push({
      id: "tier",
      eyebrow: "Real top-player win rates",
      title: <>What actually wins, <em className="not-italic text-accent">not what is loud</em>.</>,
      body:
        "Every champion ranked by the real win rates of its best players, confidence-adjusted so "
        + "hype and lucky streaks never make the cut.",
      claims: ["EU, NA and China", "Confidence-adjusted", "Updated every patch"],
      primary: { href: "/tier-list", label: "See what actually wins" },
      secondary: { href: "/meta", label: "Read the meta overview" },
      shot: { src: "/shots/tier.jpg", alt: "The tier list, showing the GOD tier with each champion's win rate" },
    });
  }
  if (DRAFT_TOOL_LIVE) {
    out.push({
      id: "draft",
      eyebrow: "Draft assistant",
      title: <>Win the draft <em className="not-italic text-gold">before the game starts</em>.</>,
      body:
        "Tap the lobby as it happens: all ten bans, their picks, your team. It ranks what to pick "
        + "from the champions you actually play, then turns their comp into a counter build.",
      claims: ["Ban targets", "Picks from your own pool", "One-tap counter build"],
      primary: { href: "/draft", label: "Open the draft assistant" },
      shot: { src: "/shots/draft.jpg", alt: "The draft assistant, with bans, both teams and the read on the enemy comp" },
    });
  }
  out.push({
    id: "overlay",
    eyebrow: "Android overlay · alpha",
    title: <>Your draft, <em className="not-italic text-emerald-300">on top of the game</em>.</>,
    body:
      "An overlay that reads champion select on your phone and shows the picks, the bans and the "
      + "build you need, without ever leaving Wild Rift.",
    claims: ["Reads champion select", "Builds against their five", "Never leaves the game"],
    primary: { href: "/overlay", label: "See the overlay" },
    shot: { src: "/shots/overlay.jpg", alt: "The Wild Rift draft overlay app on an Android phone", tall: true },
  });
  // The tier list is the fallback slide's picture when the build tools are
  // shut; with them open it is still the site's other half, so it closes the
  // deck rather than being left out.
  if (BUILD_TOOLS_LIVE) {
    out.push({
      id: "tier",
      eyebrow: "Real top-player win rates",
      title: <>What actually wins, <em className="not-italic text-accent">not what is loud</em>.</>,
      body:
        "Every champion ranked by the real win rates of its best players, confidence-adjusted so "
        + "hype and lucky streaks never make the cut. It is the evidence the builds are made from.",
      claims: ["EU, NA and China", "Confidence-adjusted", "Updated every patch"],
      primary: { href: "/tier-list", label: "See what actually wins" },
      secondary: { href: "/meta", label: "Read the meta overview" },
      shot: { src: "/shots/tier.jpg", alt: "The tier list, showing the GOD tier with each champion's win rate" },
    });
  }
  return out;
}

function Arrow({ dir, onClick }: { dir: "prev" | "next"; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      aria-label={dir === "prev" ? "Previous feature" : "Next feature"}
      className="glass glass-hover grid h-9 w-9 place-items-center rounded-full text-muted transition hover:text-text"
    >
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"
        strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <path d={dir === "prev" ? "m15 18-6-6 6-6" : "m9 6 6 6-6 6"} />
      </svg>
    </button>
  );
}

export function HeroCarousel() {
  const deck = useRef(slides()).current;
  const [at, setAt] = useState(0);
  const [paused, setPaused] = useState(false);
  /** Where a swipe started, in page pixels. */
  const swipe = useRef<number | null>(null);

  const step = useCallback(
    (by: number) => setAt((i) => (i + by + deck.length) % deck.length),
    [deck.length],
  );

  // A timeout per slide rather than one interval: `at` is a dependency, so
  // whatever moved the deck -- the timer, an arrow, a dot, a swipe -- the next
  // slide still gets its full dwell.
  useEffect(() => {
    if (deck.length < 2 || paused) return;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const id = window.setTimeout(() => step(1), ROTATE_MS);
    return () => window.clearTimeout(id);
  }, [at, deck.length, paused, step]);

  // A slideshow advancing in a tab nobody is looking at is wasted motion, and
  // it means coming back to the page mid-transition.
  useEffect(() => {
    const onVisibility = () => setPaused(document.hidden);
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);

  return (
    // ON GLASS, not on the art. The hero is the one block of text the whole
    // site is judged by, and the background is a painting: over its bright half
    // the body paragraph measured about 2:1. A radial scrim was holding it up
    // and losing; the panel is the material the rest of the site already uses,
    // it covers every slide at once, and the reading-halo rule in globals.css
    // leaves anything inside glass alone.
    <div
      className="home-cinema glass mx-auto max-w-6xl overflow-hidden rounded-[2rem]"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={() => setPaused(false)}
      // Swipe, for the phones this site is mostly read on. A finger down holds
      // the deck; 40px of travel decides whether it was a swipe or a tap, and
      // nothing is prevented, so scrolling the page still works.
      onTouchStart={(e) => {
        swipe.current = e.touches[0]?.clientX ?? null;
        setPaused(true);
      }}
      onTouchEnd={(e) => {
        const from = swipe.current;
        swipe.current = null;
        setPaused(false);
        const to = e.changedTouches[0]?.clientX;
        if (from == null || to == null || Math.abs(to - from) < 40) return;
        step(to < from ? 1 : -1);
      }}
      // Arrow keys once anything in the hero has focus, which is how the
      // arrows below behave for a keyboard in the first place.
      onKeyDown={(e) => {
        if (e.key === "ArrowRight") step(1);
        else if (e.key === "ArrowLeft") step(-1);
      }}
    >
      <div className="grid">
        {deck.map((s, i) => {
          const live = i === at;
          const Heading = i === 0 ? "h1" : "h2";
          return (
            <div
              key={s.id}
              // Every slide in the same cell, so the hero never changes height,
              // and centred in it: the cell is as tall as the longest slide, and
              // a shorter one left all of that slack underneath itself.
              //
              // 200ms, not 500: at a one-second cadence a half-second crossfade
              // means the hero is always mid-fade and never simply readable.
              className={`col-start-1 row-start-1 w-full place-self-center transition-opacity duration-200 motion-reduce:transition-none ${
                live ? "opacity-100" : "pointer-events-none opacity-0"
              }`}
              inert={!live}
              aria-hidden={!live}
            >
              <div className="grid min-h-[31rem] lg:grid-cols-[0.92fr_1.08fr]">
                <div className="home-cinema-copy flex flex-col justify-center px-6 py-9 text-left sm:px-9 lg:px-12 lg:py-12">
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">
                    {s.eyebrow}
                  </p>
                  <Heading className="display-title mt-4 max-w-[11ch] text-5xl leading-[0.94] sm:text-6xl lg:text-[4.5rem]">
                    {s.title}
                  </Heading>
                  <p className="mt-6 max-w-xl text-base leading-relaxed text-muted sm:text-lg">
                    {s.body}
                  </p>
                  <div className="mt-7 flex flex-wrap items-center gap-3">
                    <Link
                      href={s.primary.href}
                      className="primary-action rounded-xl bg-accent px-6 py-3 font-semibold text-[#07121f] transition hover:brightness-110"
                    >
                      {s.primary.label}
                    </Link>
                    {s.secondary && (
                      <Link
                        href={s.secondary.href}
                        className="glass glass-hover rounded-xl px-6 py-3 font-semibold text-text"
                      >
                        {s.secondary.label}
                      </Link>
                    )}
                  </div>
                  <div className="home-proof-grid mt-8 grid grid-cols-3 overflow-hidden rounded-2xl border border-white/[0.07]">
                    {s.claims.map((c, claimIndex) => (
                      <div key={c} className="min-w-0 px-3 py-3 sm:px-4">
                        <span className="mb-1 block text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-faint">
                          0{claimIndex + 1}
                        </span>
                        <span className="block text-xs font-semibold leading-snug text-text sm:text-sm">{c}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* The picture is a link to the thing in it: someone who looks
                    at a screenshot long enough to want it should not have to
                    find the button again. */}
                <Link
                  href={s.primary.href}
                  tabIndex={-1}
                  aria-hidden
                  className="home-cinema-shot group/shot relative flex min-h-[20rem] items-center justify-center overflow-hidden border-t border-line bg-[#080b14] p-5 transition sm:p-8 lg:min-h-full lg:border-l lg:border-t-0 lg:p-10"
                >
                  <img
                    src={s.shot.src}
                    alt={s.shot.alt}
                    loading={i === 0 ? "eager" : "lazy"}
                    decoding="async"
                    // 16:9 is the shape the captures come in, so a page shot
                    // fills the frame without losing its bottom rows; the
                    // phone shot is fitted into the same frame instead, which
                    // is what makes a portrait screenshot read as a phone.
                    className={`relative z-[1] max-h-[27rem] w-full rounded-2xl border border-white/10 shadow-2xl transition duration-700 group-hover/shot:scale-[1.015] ${
                      s.shot.tall ? "h-[27rem] object-contain" : "h-auto object-contain"
                    }`}
                  />
                  <span aria-hidden className="absolute inset-0 bg-[radial-gradient(circle_at_72%_16%,rgba(85,165,210,.16),transparent_52%),linear-gradient(135deg,rgba(18,38,66,.7),rgba(4,9,18,.92))]" />
                  <span className="absolute bottom-4 left-4 right-4 z-[2] flex items-end justify-between rounded-2xl border border-white/10 bg-[#070d18]/78 p-4 backdrop-blur-xl sm:bottom-6 sm:left-6 sm:right-6">
                    <span>
                      <span className="block text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-faint">Live signal</span>
                      <span className="mt-1 block text-sm font-semibold text-white">Built from top-player data</span>
                    </span>
                    <svg viewBox="0 0 120 34" className="h-8 w-28" aria-hidden>
                      <defs>
                        <linearGradient id={`pulse-${s.id}`} x1="0" x2="1">
                          <stop offset="0" stopColor="#6fa8ff" stopOpacity=".25" />
                          <stop offset="1" stopColor="#7ff7df" />
                        </linearGradient>
                      </defs>
                      <path d="M2 28 C18 26 18 17 32 19 S48 28 61 15 S80 18 92 9 S108 8 118 3" fill="none" stroke={`url(#pulse-${s.id})`} strokeWidth="2.5" strokeLinecap="round" />
                    </svg>
                  </span>
                </Link>
              </div>
            </div>
          );
        })}
      </div>

      {/* The controls say "you can move this yourself".
          Dots alone did not: they read as a position indicator, and at speed
          people reach for something to stop the thing moving rather than
          something to move it. Two arrows around them is the shape everyone
          already knows, it is a target a thumb can hit, and it gives the swipe
          and the arrow keys a visible counterpart. */}
      {deck.length > 1 && (
        <div className="home-cinema-controls flex items-center justify-center gap-3 border-t border-white/[0.07] px-5 py-4">
          <Arrow dir="prev" onClick={() => step(-1)} />
          <div className="flex items-center gap-2">
            {deck.map((s, i) => (
              <button
                key={s.id}
                onClick={() => setAt(i)}
                aria-label={`Show ${s.eyebrow}`}
                aria-current={i === at}
                className={`h-2 rounded-full transition-all ${
                  i === at ? "w-7 bg-accent" : "w-4 bg-white/30 hover:bg-white/60"
                }`}
              />
            ))}
          </div>
          <Arrow dir="next" onClick={() => step(1)} />
        </div>
      )}
    </div>
  );
}
