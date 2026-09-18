"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ADSENSE_CLIENT, AD_UNITS, PLACEMENT_HEIGHT, adsAllowedOn, type Placement } from "@/lib/ads";

/**
 * One ad position.
 *
 * Three things it always does, because each one is a way ad code ruins a page:
 *
 *   RESERVES ITS SPACE. The height is fixed before anything loads, so a unit
 *   arriving late cannot shove the article the reader is halfway through.
 *
 *   LOADS LATE. Nothing is requested until the slot is within 300px of the
 *   viewport, so a footer unit costs nothing on a visit that never scrolls.
 *
 *   ALWAYS RENDERS SOMETHING. With no network configured, or no unit id for
 *   this placement, it shows one of our own promos instead of leaving a hole.
 *   That is also what makes the layout testable before an ad account exists.
 *
 * It never appears on the routes in AD_FREE_ROUTES. The draft assistant and
 * the second screen are used with a lobby on the clock, and an ad in the
 * middle of a ban phase is worth less than the person who leaves because of
 * it.
 */

/** Our own promos, used when there is nothing to serve. Internal links only:
 *  a house ad is a signpost to the rest of the site, not a banner exchange. */
const HOUSE = [
  {
    eyebrow: "Draft overlay · alpha",
    title: "Your draft, on top of the game",
    body: "It reads champion select on your phone and builds against their five without leaving Wild Rift.",
    href: "/overlay",
    cta: "See the overlay",
  },
  {
    eyebrow: "Build Studio",
    title: "Build for this game, not every game",
    body: "A build reasoned for your champion, your role and the five you are up against.",
    href: "/build?tab=generate",
    cta: "Generate a build",
  },
  {
    eyebrow: "Every champion, ranked",
    title: "What actually wins on your server",
    body: "Real top-50 win rates for EU, NA and China, confidence-adjusted every patch.",
    href: "/tier-list",
    cta: "Open the tier list",
  },
] as const;

/** Chosen by placement rather than at random: a random pick would render one
 *  promo on the server and another in the browser, which is a hydration
 *  mismatch for the sake of variety nobody asked for. */
const HOUSE_FOR: Record<Placement, number> = { top: 2, inline: 0, bottom: 1, anchor: 0 };

function HouseAd({ placement }: { placement: Placement }) {
  const promo = HOUSE[HOUSE_FOR[placement]];
  return (
    <Link
      href={promo.href}
      className="glass glass-hover no-plate flex h-full w-full flex-wrap items-center justify-between gap-3 rounded-2xl px-4 py-3 text-left"
    >
      <span className="min-w-0">
        <span className="block text-[0.6rem] font-bold uppercase tracking-[0.18em] text-accent">
          {promo.eyebrow}
        </span>
        <span className="mt-1 block text-sm font-bold text-text">{promo.title}</span>
        <span className="mt-0.5 block text-xs text-muted">{promo.body}</span>
      </span>
      <span className="shrink-0 text-xs font-semibold text-accent">{promo.cta} →</span>
    </Link>
  );
}

export function AdSlot({ placement, className = "", bare = false }: {
  placement: Placement;
  className?: string;
  /** Already inside a page's Container: drop the slot's own width and gutter
   *  so the unit does not sit in two nested paddings. */
  bare?: boolean;
}) {
  const pathname = usePathname() || "/";
  const box = useRef<HTMLDivElement | null>(null);
  const pushed = useRef(false);
  const [near, setNear] = useState(false);

  // The anchor is components/anchor-ad.tsx, not a slot in the page flow: it is
  // fixed to the viewport, reserves space through a CSS variable and can be
  // closed, none of which this component does.
  const allowed = placement !== "anchor" && adsAllowedOn(pathname, placement);
  const unit = AD_UNITS[placement];
  const network = Boolean(ADSENSE_CLIENT && unit);

  // Within 300px of the viewport is close enough to be about to be seen, and
  // far enough that the unit is filled by the time it is.
  useEffect(() => {
    if (!allowed || near || !box.current) return;
    const el = box.current;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setNear(true);
          io.disconnect();
        }
      },
      { rootMargin: "300px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [allowed, near]);

  // One push per <ins>, ever. React runs effects twice in development, and a
  // second push on the same element is the "already have ads in them" error
  // that leaves the slot permanently blank.
  useEffect(() => {
    if (!near || !network || pushed.current) return;
    pushed.current = true;
    try {
      const w = window as unknown as { adsbygoogle?: unknown[] };
      w.adsbygoogle = w.adsbygoogle || [];
      w.adsbygoogle.push({});
    } catch { /* blocked or not loaded: the reserved space just stays empty */ }
  }, [near, network]);

  if (!allowed) return null;

  return (
    <div
      ref={box}
      // no-plate: the slot brings its own panel, and the reading-halo rule in
      // globals.css would otherwise draw a second backing around it.
      className={`no-plate w-full ${bare ? "" : "mx-auto max-w-6xl px-5"} ${className}`}
    >
      {/* The reserved height applies only when a network unit can arrive. It
          exists so a late ad cannot shove the page; a house promo is not late
          and never grows, and reserving 250px around an 80px card left a hole
          in the middle of the tier list. */}
      <div className={`relative flex w-full items-stretch ${network ? PLACEMENT_HEIGHT[placement] : ""}`}>
        {near && network ? (
          <>
            {/* Labelled, because an ad that reads as site content is both a
                policy breach and a trick. */}
            <span className="pointer-events-none absolute -top-4 left-0 text-[0.6rem] uppercase tracking-wide text-faint">
              Advertisement
            </span>
            <ins
              className="adsbygoogle block w-full"
              style={{ display: "block", width: "100%" }}
              data-ad-client={ADSENSE_CLIENT}
              data-ad-slot={unit}
              data-ad-format="auto"
              data-full-width-responsive="true"
            />
          </>
        ) : (
          <HouseAd placement={placement} />
        )}
      </div>
    </div>
  );
}
