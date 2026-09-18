"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  VIDEO_AD_MAX_MS,
  VIDEO_AD_SKIP_MS,
  VIDEO_AD_TAG,
  VIDEO_AD_TIMEOUT_MS,
  videoAdsAllowedOn,
} from "@/lib/ads";

/**
 * The pre-roll that plays while a build generates.
 *
 * THE WAIT IS WHY THIS IS ACCEPTABLE. A generation takes about 55 seconds of
 * real model work whether or not an ad plays, so a 20-second spot inside it
 * costs the visitor nothing they were not already spending. That is also the
 * line it must not cross: the ad is never allowed to delay the result, and the
 * build is revealed the moment it lands, mid-ad if that is when it happens.
 *
 * FOUR THINGS ARE OURS TO ENFORCE, not the network's:
 *
 *   TWENTY SECONDS, HARD. The player stops the ad at the cap whatever the
 *   creative's own duration is. A 30-second spot trafficked into this slot is
 *   the network's mistake and must not become the visitor's.
 *
 *   SKIPPABLE AT FIVE. The convention everyone already knows.
 *
 *   MUTED UNTIL ASKED. Sound arriving unannounced while somebody is in a lobby
 *   is the single most hated thing a web page can do. There is an unmute
 *   button; there is no autoplay with audio.
 *
 *   A DEADLINE ON THE AD ITSELF. If nothing has started playing within
 *   VIDEO_AD_TIMEOUT_MS, the slot gives up and the plain progress bar takes
 *   over. A generation the visitor has spent quota on never waits on an ad
 *   server.
 *
 * With no VAST tag configured -- or on a route in AD_FREE_ROUTES, which is how
 * the draft assistant stays clean -- this renders one of our own promos and no
 * countdown, so the wait still has something in it.
 */

/* ── the slice of Google's IMA SDK this uses, typed ────────────────────────
   Hand-written rather than pulled from @types/google.ima: five calls and four
   event names do not justify a dependency, and the shapes below are what the
   loader script actually exposes. */

interface ImaManager {
  addEventListener(type: string, handler: () => void): void;
  init(width: number, height: number, viewMode: unknown): void;
  start(): void;
  stop(): void;
  destroy(): void;
  setVolume(volume: number): void;
}

interface ImaRequest {
  adTagUrl: string;
  linearAdSlotWidth: number;
  linearAdSlotHeight: number;
  nonLinearAdSlotWidth: number;
  nonLinearAdSlotHeight: number;
  /** Declaring autoplay and muted is what lets the ad start without a gesture
   *  of its own. Without them the SDK waits for a click that is never coming
   *  -- the visitor already clicked Generate, three network round trips ago --
   *  and the slot times out with nothing played. */
  setAdWillAutoPlay(will: boolean): void;
  setAdWillPlayMuted(muted: boolean): void;
}

/** Both events the loader emits, as one shape: the SDK hands back an object
 *  with getAdsManager on success and getError on failure. */
interface ImaLoaderEvent {
  getAdsManager?(video: HTMLVideoElement): ImaManager;
  getError?(): { getMessage?(): string } | undefined;
}

interface ImaLoader {
  addEventListener(type: string, handler: (event: ImaLoaderEvent) => void, capture: boolean): void;
  requestAds(request: ImaRequest): void;
  destroy(): void;
}

interface ImaContainer {
  initialize(): void;
  destroy(): void;
}

interface Ima {
  AdDisplayContainer: new (container: HTMLElement, video: HTMLVideoElement) => ImaContainer;
  AdsLoader: new (container: ImaContainer) => ImaLoader;
  AdsRequest: new () => ImaRequest;
  AdsManagerLoadedEvent: { Type: { ADS_MANAGER_LOADED: string } };
  AdErrorEvent: { Type: { AD_ERROR: string } };
  AdEvent: { Type: { LOADED: string; STARTED: string; COMPLETE: string; ALL_ADS_COMPLETED: string; SKIPPED: string } };
  ViewMode: { NORMAL: unknown };
}

/** Ad failures are silent by design: the SDK swallows most of them and the
 *  slot is built to fall back rather than complain. That makes "no ad played"
 *  undebuggable without a trace, so there is one, in development only. */
const trace = (...args: unknown[]) => {
  if (process.env.NODE_ENV !== "production") console.debug("[ad]", ...args);
};

const SDK = "https://imasdk.googleapis.com/js/sdkloader/ima3.js";
let sdk: Promise<Ima | null> | null = null;

/** Loaded once per page, on the first generation rather than on page load: an
 *  ad SDK on every visit to every page is 200KB spent on visitors who never
 *  press Generate. */
function loadIma(): Promise<Ima | null> {
  if (sdk) return sdk;
  sdk = new Promise<Ima | null>((resolve) => {
    const existing = (window as unknown as { google?: { ima?: Ima } }).google?.ima;
    if (existing) return resolve(existing);
    const tag = document.createElement("script");
    tag.src = SDK;
    tag.async = true;
    tag.onload = () => resolve((window as unknown as { google?: { ima?: Ima } }).google?.ima ?? null);
    tag.onerror = () => resolve(null);          // blocked, offline, or refused
    document.head.appendChild(tag);
  });
  return sdk;
}

function HousePromo() {
  return (
    <Link
      href="/overlay"
      className="no-plate flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line/70 bg-white/[0.02] px-3.5 py-3"
    >
      <span className="min-w-0">
        <span className="block text-[0.6rem] font-bold uppercase tracking-[0.18em] text-accent">
          While you wait
        </span>
        <span className="mt-1 block text-sm font-bold text-text">
          The overlay does this inside the game
        </span>
        <span className="mt-0.5 block text-xs text-muted">
          It reads champion select on your phone and builds against their five, with no tab to switch to.
        </span>
      </span>
      <span className="shrink-0 text-xs font-semibold text-accent">See the overlay →</span>
    </Link>
  );
}

/**
 * @param delayMs mount nothing until the wait has lasted this long.
 *
 * The Build Studio always takes about a minute, so it starts at once. The draft
 * assistant answers a known matchup instantly and a fresh one in 15-30 seconds,
 * and without a delay every instant answer flashed an empty black player box
 * for a frame. With one, a cached build never sees the ad slot at all, and a
 * real wait gets the ad a moment in.
 */
export function VideoAdGate({ delayMs = 0 }: { delayMs?: number } = {}) {
  const [armed, setArmed] = useState(delayMs <= 0);
  useEffect(() => {
    if (armed) return;
    const id = window.setTimeout(() => setArmed(true), delayMs);
    return () => window.clearTimeout(id);
  }, [armed, delayMs]);
  // A separate component, so the player mounts FRESH when the delay ends:
  // starting it half-armed would leave it with no elements to attach to.
  return armed ? <VideoAdPlayer /> : null;
}

function VideoAdPlayer() {
  const pathname = usePathname() || "/";
  const wanted = Boolean(VIDEO_AD_TAG) && videoAdsAllowedOn(pathname);

  const [phase, setPhase] = useState<"starting" | "playing" | "over">(wanted ? "starting" : "over");
  const [left, setLeft] = useState(Math.round(VIDEO_AD_MAX_MS / 1000));
  const [canSkip, setCanSkip] = useState(false);
  const [muted, setMuted] = useState(true);

  /** Read inside a timeout without making the timeout depend on the state. */
  const phaseRef = useRef(phase);
  useEffect(() => { phaseRef.current = phase; }, [phase]);

  const slot = useRef<HTMLDivElement | null>(null);
  const video = useRef<HTMLVideoElement | null>(null);
  const manager = useRef<ImaManager | null>(null);
  const loader = useRef<ImaLoader | null>(null);
  const container = useRef<ImaContainer | null>(null);

  /** Drop the SDK objects. Says nothing about whether an ad played, which is
   *  the whole point of it being separate from finish():
   *
   *  React runs an effect, throws the result away and runs it again in
   *  development. When teardown and "the ad is over" were one function, that
   *  throwaway first run flipped the slot to its fallback before the real run
   *  started, and the player then had no elements to attach to -- an ad could
   *  never play in dev, and any future cleanup would have done the same in
   *  production. */
  const teardown = useCallback(() => {
    try {
      manager.current?.stop();
      manager.current?.destroy();
      loader.current?.destroy();
      container.current?.destroy();
    } catch { /* the SDK throws on double teardown; nothing left to clean */ }
    manager.current = null;
    loader.current = null;
    container.current = null;
  }, []);

  /** The ad is over, by any route: played out, skipped, errored, or never
   *  started. The house promo takes the slot. */
  const finish = useCallback(() => {
    teardown();
    setPhase("over");
  }, [teardown]);

  useEffect(() => {
    if (!wanted) return;
    let dead = false;
    const timers: number[] = [];

    void (async () => {
      const ima = await loadIma();
      if (dead) return teardown();          // a cancelled run, not a failure
      const host = slot.current;
      const player = video.current;
      if (!ima || !host || !player) {
        finish();
        return;
      }
      // Nothing playing by the deadline: hand the wait back to the progress bar.
      let deadline = window.setTimeout(() => {
        if (phaseRef.current !== "playing") {
          trace("no ad in hand within", VIDEO_AD_TIMEOUT_MS, "ms");
          finish();
        }
      }, VIDEO_AD_TIMEOUT_MS);
      timers.push(deadline);

      trace("sdk ready");
      try {
        const display = new ima.AdDisplayContainer(host, player);
        display.initialize();                    // must happen in the click's task chain
        container.current = display;
        const ads = new ima.AdsLoader(display);
        loader.current = ads;
        trace("container + loader ready");

        ads.addEventListener(
          ima.AdErrorEvent.Type.AD_ERROR,
          (event) => {
            // Logged rather than swallowed: "no ad played" has half a dozen
            // causes (empty response, autoplay refused, blocked host) and the
            // message is the only thing that separates them.
            trace("error", event.getError?.()?.getMessage?.() ?? "unknown");
            finish();
          },
          false,
        );
        ads.addEventListener(
          ima.AdsManagerLoadedEvent.Type.ADS_MANAGER_LOADED,
          (event) => {
            trace("manager loaded");
            const get = event.getAdsManager;
            if (dead || !get) return finish();
            const m = get.call(event, player);
            manager.current = m;
            // The creative is downloaded and ready. Getting hold of an ad is
            // the slow part; playing it is not, so the deadline is reset to a
            // short one here rather than left to cancel an ad that is about to
            // start.
            m.addEventListener(ima.AdEvent.Type.LOADED, () => {
              trace("creative loaded");
              window.clearTimeout(deadline);
              deadline = window.setTimeout(() => {
                if (phaseRef.current !== "playing") {
                  trace("loaded but never started");
                  finish();
                }
              }, 4_000);
              timers.push(deadline);
            });
            m.addEventListener(ima.AdEvent.Type.STARTED, () => {
              trace("started");
              setPhase("playing");
              // The cap, the skip and the countdown all start from the first
              // frame rather than from the request, so a slow ad server does
              // not eat the twenty seconds.
              timers.push(window.setTimeout(finish, VIDEO_AD_MAX_MS));
              timers.push(window.setTimeout(() => setCanSkip(true), VIDEO_AD_SKIP_MS));
              const tick = window.setInterval(() => {
                setLeft((n) => (n <= 1 ? 0 : n - 1));
              }, 1000);
              timers.push(tick);
            });
            m.addEventListener(ima.AdEvent.Type.COMPLETE, finish);
            m.addEventListener(ima.AdEvent.Type.ALL_ADS_COMPLETED, finish);
            m.addEventListener(ima.AdEvent.Type.SKIPPED, finish);
            const box = host.getBoundingClientRect();
            m.init(Math.round(box.width) || 640, Math.round(box.height) || 360, ima.ViewMode.NORMAL);
            m.setVolume(0);
            m.start();
          },
          false,
        );

        const request = new ima.AdsRequest();
        request.adTagUrl = VIDEO_AD_TAG;
        request.setAdWillAutoPlay(true);
        request.setAdWillPlayMuted(true);
        const box = host.getBoundingClientRect();
        request.linearAdSlotWidth = Math.round(box.width) || 640;
        request.linearAdSlotHeight = Math.round(box.height) || 360;
        request.nonLinearAdSlotWidth = request.linearAdSlotWidth;
        request.nonLinearAdSlotHeight = Math.round(request.linearAdSlotHeight / 3);
        trace("requesting", request.linearAdSlotWidth, "x", request.linearAdSlotHeight);
        ads.requestAds(request);
      } catch (err) {
        trace("threw", err);
        finish();
      }
    })();

    return () => {
      dead = true;
      timers.forEach((id) => { window.clearTimeout(id); window.clearInterval(id); });
      teardown();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wanted, finish, teardown]);

  // Elapsed is the countdown read backwards, so both numbers come off one
  // timer rather than two that can disagree.
  const elapsed = Math.round(VIDEO_AD_MAX_MS / 1000) - left;
  const untilSkip = Math.max(0, Math.round(VIDEO_AD_SKIP_MS / 1000) - elapsed);

  const unmute = () => {
    manager.current?.setVolume(muted ? 1 : 0);
    setMuted((m) => !m);
  };

  if (phase === "over") return <HousePromo />;

  return (
    // 420px, not the full panel width. At full width the player was 600px tall
    // on a desktop and dwarfed the build it was standing in front of; a small
    // one in the corner of a wait reads as an ad in a slot rather than as the
    // page turning into an ad break. IMA sizes the creative from this box, so
    // the request shrinks with it.
    <div className="no-plate mx-auto w-full max-w-[420px] overflow-hidden rounded-xl border border-line/70 bg-black/60">
      <div className="relative aspect-video w-full">
        {/* IMA draws into its own container and needs a video element beside
            it, even for a linear creative it renders itself. */}
        <video ref={video} className="h-full w-full" playsInline muted />
        <div ref={slot} className="absolute inset-0" />
        {phase === "starting" && (
          <p className="absolute inset-0 grid place-items-center text-xs text-faint">
            Loading a short ad…
          </p>
        )}
      </div>
      <div className="flex items-center justify-between gap-3 px-3 py-2">
        <p className="text-[0.7rem] text-faint">
          {phase === "playing"
            ? `Ad · ${left}s left. Your build is generating behind this.`
            : "Your build is generating."}
        </p>
        <span className="flex shrink-0 items-center gap-2">
          <button
            onClick={unmute}
            className="rounded-lg border border-line px-2.5 py-1 text-[0.7rem] font-semibold text-muted transition hover:text-text"
          >
            {muted ? "Unmute" : "Mute"}
          </button>
          <button
            onClick={finish}
            disabled={!canSkip}
            className="rounded-lg border border-line px-2.5 py-1 text-[0.7rem] font-semibold text-text transition hover:border-accent/60 disabled:opacity-40"
          >
            {canSkip ? "Skip ad" : `Skip in ${untilSkip}s`}
          </button>
        </span>
      </div>
    </div>
  );
}
