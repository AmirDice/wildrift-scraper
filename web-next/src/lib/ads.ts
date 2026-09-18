/**
 * Ad configuration: where ads may appear, what fills them, and what never gets
 * one.
 *
 * Data-free and JSX-free on purpose, so a server component can ask where a
 * slot belongs without pulling the client code in with it.
 *
 * ONE PROVIDER SEAM. Nothing outside this file names an ad network. A slot
 * renders a network unit when the network is configured and a house promo when
 * it is not, which means the layout is finished and tested before an account
 * exists, and switching network later is an env change plus one component.
 *
 * WHY HOUSE ADS ARE THE DEFAULT. An unfilled third-party slot is a hole in the
 * page; a slot holding our own Discord or overlay promo is a working page that
 * happens to earn nothing yet. It also means the reserved space is real in
 * development, so nothing about the layout is a surprise on the day the
 * network turns on.
 */

/** Master switch. Only an explicit "0" or "false" turns ads off; anything
 *  else, including unset, leaves them on -- same convention as the build-tool
 *  flags, so a kill switch is one Vercel env var and a redeploy. */
const _flag = process.env.NEXT_PUBLIC_ADS?.toLowerCase();
export const ADS_LIVE = !(_flag === "0" || _flag === "false");

/** AdSense publisher id ("ca-pub-..."). Empty until the account is approved,
 *  which is what selects house promos. */
export const ADSENSE_CLIENT = process.env.NEXT_PUBLIC_ADSENSE_CLIENT ?? "";

export type Placement = "top" | "inline" | "bottom" | "anchor";

/** Per-placement ad unit ids from the network's console. A placement with no
 *  id falls back to a house promo even when the account is live, so units can
 *  be rolled out one at a time. */
export const AD_UNITS: Record<Placement, string> = {
  top: process.env.NEXT_PUBLIC_AD_SLOT_TOP ?? "",
  inline: process.env.NEXT_PUBLIC_AD_SLOT_INLINE ?? "",
  bottom: process.env.NEXT_PUBLIC_AD_SLOT_BOTTOM ?? "",
  anchor: process.env.NEXT_PUBLIC_AD_SLOT_ANCHOR ?? "",
};

/**
 * The anchor exists only when there is something to put in it.
 *
 * Every other placement falls back to a house promo, because an in-content
 * slot holding our own Discord link is a useful signpost. A bar stuck to the
 * bottom of the screen is not: with nothing to serve it is pure furniture,
 * taking a strip of every page and earning nothing. So this one is all or
 * nothing, and while it is nothing the site has no sticky bar at all.
 */
export const ANCHOR_LIVE = ADS_LIVE && Boolean(ADSENSE_CLIENT && AD_UNITS.anchor);

/**
 * Reserved height per placement, as a Tailwind class.
 *
 * Fixed, and applied whether or not anything fills it. An ad that arrives into
 * an unreserved box shoves the article down as the reader is reading it, which
 * is both the classic CLS failure and the reason people say a site "feels like
 * ads". The numbers are the standard responsive heights: a 320x100 mobile
 * banner growing to a 728x90 leaderboard, and 250 for the in-content unit that
 * may serve a 300x250.
 */
export const PLACEMENT_HEIGHT: Record<Placement, string> = {
  top: "min-h-[100px] sm:min-h-[90px]",
  inline: "min-h-[250px]",
  bottom: "min-h-[100px] sm:min-h-[90px]",
  // The anchor's height lives in CSS (--anchor-h in globals.css) because the
  // page padding and the floating corner furniture have to read the same
  // number, and only CSS can hand one value to all three.
  anchor: "h-[var(--anchor-h)]",
};

/**
 * Routes that never carry an ad, by prefix.
 *
 * Only the ones where an ad cannot earn: /admin is the owner's own panel, and
 * /api/ is not a page. Everything a visitor can open carries ads.
 *
 * That includes the draft assistant and the second screen. They were ad-free
 * at first, on the grounds that they are used with a live lobby on the clock;
 * the owner's call on 2026-09-18 was that donations are not paying for the
 * site and ads go everywhere they can. The one concession kept is that no
 * unit is wedged INSIDE those tools -- see draft/page.tsx.
 */
export const AD_FREE_ROUTES = [
  "/admin",
  "/api/",
];

/** Placements the home page skips. Empty: the home page used to skip the top
 *  unit so the hero kept the first screen, and the owner chose revenue over
 *  that on 2026-09-18. The mechanism stays so the call is one line to undo. */
const HOME_SKIPS: Placement[] = [];

export function adsAllowedOn(pathname: string, placement: Placement): boolean {
  if (!ADS_LIVE) return false;
  if (AD_FREE_ROUTES.some((prefix) => pathname === prefix || pathname.startsWith(prefix))) {
    return false;
  }
  if (pathname === "/" && HOME_SKIPS.includes(placement)) return false;
  return true;
}

/** Video follows the same route rules: no pre-roll in a live draft, where the
 *  counter build is generated with a lobby on the clock. */
export function videoAdsAllowedOn(pathname: string): boolean {
  if (!ADS_LIVE) return false;
  return !AD_FREE_ROUTES.some((prefix) => pathname === prefix || pathname.startsWith(prefix));
}

/* ── Video ────────────────────────────────────────────────────────────────
   The generator takes about 55 seconds, which is the whole reason a video ad
   is tolerable here: the wait already exists, so a pre-roll inside it costs
   the visitor nothing they were not already spending. That is also the rule it
   has to keep -- it can never become the reason the wait got longer.        */

/** VAST/VPAID tag URL. With one set, the gate plays a real ad through Google's
 *  IMA SDK; without one it shows a house promo and no countdown. */
export const VIDEO_AD_TAG = process.env.NEXT_PUBLIC_AD_VIDEO_VAST ?? "";

/** Hard ceiling, enforced by us and not by the creative. Twenty seconds is the
 *  owner's cap; the player stops the ad at the limit whatever its own duration
 *  says, because a 30-second creative in a 20-second slot is the network's
 *  problem and must not become the visitor's. */
export const VIDEO_AD_MAX_MS = 20_000;

/** When the skip button arms. Five seconds is the convention people already
 *  know from every other pre-roll. */
export const VIDEO_AD_SKIP_MS = 5_000;

/** How long to wait for the ad to START before giving up and showing the plain
 *  progress bar. A generation the visitor has paid quota for never waits on an
 *  ad network.
 *
 *  Eight seconds, not the two and a half it was first set to: measured
 *  against Google's sample tag, the VAST round trip plus fetching the creative
 *  took longer than six, so the tighter deadline cancelled ads that were
 *  seconds from playing. The clock is also reset once the creative is in hand
 *  (see the LOADED handler), so this only has to cover getting hold of an ad,
 *  not playing it. There are about 55 seconds of generation to hide in. */
export const VIDEO_AD_TIMEOUT_MS = 8_000;
