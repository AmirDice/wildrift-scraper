"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ADSENSE_CLIENT, ANCHOR_LIVE, AD_UNITS, adsAllowedOn } from "@/lib/ads";

/**
 * The sticky bar along the bottom of the screen.
 *
 * WHY THIS ONE. It earns more than any other unit on a site like this, because
 * it is the only one that is on screen for the whole visit rather than for the
 * seconds it takes to scroll past, and because this audience is playing a
 * phone game -- the traffic is mobile, and the anchor is a mobile format. The
 * alternative was a desktop sidebar rail, which serves a minority of visits and
 * would mean re-laying out forty centred pages to make room for it.
 *
 * WHAT IT COSTS AND HOW THAT IS PAID. A bar fixed over the page hides content
 * and covers whatever floats in the corner. So:
 *
 *   IT RESERVES ITS OWN HEIGHT. `--anchor-h` (globals.css) pads the body while
 *   the bar is up, so the last line of every page is still reachable, and
 *   iPhone home-bar inset is part of that number.
 *
 *   THE CORNER FURNITURE MOVES. The social dock, the flagship nudge and the
 *   build tour button all position off the same variable, so they sit above the
 *   bar rather than behind it.
 *
 *   IT CLOSES. One tap, and it stays closed for the rest of the session. The
 *   close button sits on the bar's edge rather than over the ad, which is both
 *   the policy and the only honest place for it.
 *
 *   IT IS NOT THERE WHEN IT IS EMPTY. See ANCHOR_LIVE: with no ad unit
 *   configured this component renders nothing at all, rather than a permanent
 *   house banner across the bottom of the site.
 *
 * If Google's Auto ads "anchor" format is ever switched on in the AdSense
 * console, turn this off -- two anchors would stack and both would be wrong.
 */

const CLOSED_KEY = "wtm_anchor_closed";

export function AnchorAd() {
  const pathname = usePathname() || "/";
  const [closed, setClosed] = useState(false);
  /** null until mounted, then whether this is a wide screen. Decided in the
   *  browser because the unit is a FIXED size and the server does not know
   *  which one; the bar's frame renders either way, so nothing shifts. */
  const [wide, setWide] = useState<boolean | null>(null);
  const pushed = useRef(false);

  useEffect(() => {
    setWide(window.matchMedia("(min-width: 640px)").matches);
  }, []);

  // Session-scoped, not permanent: a visitor who closes it is telling us about
  // this visit, not signing up to never see one again.
  useEffect(() => {
    try {
      if (sessionStorage.getItem(CLOSED_KEY) === "1") setClosed(true);
    } catch { /* private mode: it simply shows */ }
  }, []);

  const show = ANCHOR_LIVE && adsAllowedOn(pathname, "anchor") && !closed;

  // The class is the switch for every layout consequence: the body's padding
  // and the three floating elements all key off it, so there is one place that
  // decides whether the bar exists.
  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("has-anchor", show);
    return () => root.classList.remove("has-anchor");
  }, [show]);

  useEffect(() => {
    if (!show || wide === null || pushed.current) return;
    pushed.current = true;
    try {
      const w = window as unknown as { adsbygoogle?: unknown[] };
      w.adsbygoogle = w.adsbygoogle || [];
      w.adsbygoogle.push({});
    } catch { /* blocked: the bar stays empty and the page is unchanged */ }
  }, [show, wide]);

  if (!show) return null;

  const dismiss = () => {
    setClosed(true);
    try {
      sessionStorage.setItem(CLOSED_KEY, "1");
    } catch { /* private mode: closed for this page view */ }
  };

  // A FIXED unit size, not a responsive one, and this is not a style choice.
  // A responsive `<ins>` makes Google's script walk up the tree and stamp
  // `height: auto !important` on the bar to let the unit size itself, which it
  // then did: a 390px square covering half the screen on a phone. The standard
  // fixed anchor sizes are honoured as given, and the outer wrapper clips
  // anything that still tries to grow.
  const unitSize = wide ? { width: 728, height: 90 } : { width: 320, height: 50 };

  return (
    <div
      style={{ height: "var(--anchor-h)", overflow: "hidden" }}
      className="no-plate fixed inset-x-0 bottom-0 z-40 print:hidden"
    >
      <div className="relative mx-auto flex h-full w-full max-w-5xl items-center justify-center overflow-hidden border-t border-line bg-[#080b14]/95 pb-[env(safe-area-inset-bottom,0px)] backdrop-blur">
        <button
          onClick={dismiss}
          aria-label="Close ad"
          className="absolute -top-7 right-2 grid h-7 w-7 place-items-center rounded-t-md border border-b-0 border-line bg-[#080b14]/95 text-xs font-bold text-muted backdrop-blur transition hover:text-text"
        >
          ✕
        </button>
        <span className="pointer-events-none absolute -top-[18px] left-2 rounded-t-sm bg-[#080b14]/95 px-1.5 text-[0.55rem] uppercase tracking-wide text-faint">
          Advertisement
        </span>
        {wide !== null && (
          <ins
            className="adsbygoogle"
            style={{ display: "inline-block", ...unitSize }}
            data-ad-client={ADSENSE_CLIENT}
            data-ad-slot={AD_UNITS.anchor}
          />
        )}
      </div>
    </div>
  );
}
