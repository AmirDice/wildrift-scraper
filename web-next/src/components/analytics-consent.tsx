"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ANALYTICS_CONSENT_KEY as KEY } from "@/lib/analytics";

/**
 * A consent banner for Google Analytics alone, as a stopgap.
 *
 * GA4 runs under Consent Mode with analytics denied by default in the EU,
 * EEA, UK and Switzerland (layout.tsx). The grant was meant to come from
 * Google's own consent message, but AdSense serves that only on an APPROVED
 * site, and wrtruemeta.com was still "Getting ready" on 2026-10-26 with the
 * message published and shown 0 times. So no European visitor could say yes,
 * and GA undercounted them badly against Vercel's cookieless numbers -- which
 * mattered because Journey by Mediavine judges eligibility on GA data.
 *
 * This asks for analytics only. Ad storage stays denied; ad consent remains
 * Google's message's job. It retires itself: if Google's banner appears, or
 * Google's consent manager reports a decision, this one is not shown, so a
 * visitor never gets two. After approval it can simply be removed.
 *
 * Reject is as easy as accept (same size, same weight), the choice is kept
 * for a year, and the privacy page can reopen it (ConsentSettingsButton).
 */

const OPEN_EVENT = "wrtm:open-consent";

type Choice = "granted" | "denied";

function stored(): Choice | null {
  try {
    const value = window.localStorage.getItem(KEY);
    if (!value) return null;
    const { choice, at } = JSON.parse(value) as { choice?: Choice; at?: number };
    if ((choice !== "granted" && choice !== "denied") || !at) return null;
    // A year, then ask again.
    if (Date.now() - at > 365 * 86_400_000) return null;
    return choice;
  } catch {
    return null;
  }
}

function apply(choice: Choice) {
  const w = window as unknown as { gtag?: (...args: unknown[]) => void };
  w.gtag?.("consent", "update", { analytics_storage: choice });
}

/** Google's own consent message is on the page, or has already been answered. */
async function googleHandlesConsent(): Promise<boolean> {
  if (document.querySelector(".fc-consent-root, .fc-dialog-container")) return true;
  const w = window as unknown as { __tcfapi?: (cmd: string, v: number, cb: (d: { tcString?: string } | null, ok: boolean) => void) => void };
  if (!w.__tcfapi) return false;
  return new Promise((resolve) => {
    const timer = window.setTimeout(() => resolve(false), 1500);
    try {
      w.__tcfapi!("getTCData", 2, (data, ok) => {
        window.clearTimeout(timer);
        resolve(Boolean(ok && data?.tcString));
      });
    } catch {
      window.clearTimeout(timer);
      resolve(false);
    }
  });
}

export function AnalyticsConsent() {
  const [open, setOpen] = useState(false);

  const decide = useCallback(async (force = false) => {
    if (!force && stored()) return;
    try {
      const res = await fetch("/api/geo", { cache: "no-store" });
      const { consentRequired } = (await res.json()) as { consentRequired?: boolean };
      if (!consentRequired) return;
    } catch {
      // Unknown region: ask, which is the safe side.
    }
    // Give Google's message a moment to appear first; it wins when present.
    await new Promise((r) => window.setTimeout(r, 2500));
    if (!force && (await googleHandlesConsent())) return;
    setOpen(true);
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => { void decide(); }, 0);
    const reopen = () => { void decide(true); };
    window.addEventListener(OPEN_EVENT, reopen);
    return () => { window.clearTimeout(timer); window.removeEventListener(OPEN_EVENT, reopen); };
  }, [decide]);

  // Google's banner can arrive after ours opened: step aside for it.
  useEffect(() => {
    if (!open) return;
    const observer = new MutationObserver(() => {
      if (document.querySelector(".fc-consent-root, .fc-dialog-container")) setOpen(false);
    });
    observer.observe(document.body, { childList: true });
    return () => observer.disconnect();
  }, [open]);

  const choose = (choice: Choice) => {
    try { window.localStorage.setItem(KEY, JSON.stringify({ choice, at: Date.now() })); } catch { /* still applied for this visit */ }
    apply(choice);
    setOpen(false);
  };

  if (!open) return null;
  return (
    <div role="dialog" aria-modal="false" aria-labelledby="consent-title" className="fixed inset-x-4 bottom-4 z-[70] mx-auto max-w-xl sm:bottom-6">
      {/* Denser than a page panel: it floats over whatever is underneath,
          including the brightly coloured footer buttons. */}
      <div className="glass rounded-2xl border border-white/[0.12] p-4 shadow-[0_24px_80px_rgba(0,0,0,.45)] sm:p-5" style={{ backgroundColor: "rgba(7,15,29,0.86)" }}>
        <p id="consent-title" className="text-sm font-semibold text-text">Can we count your visit?</p>
        <p className="mt-1.5 text-xs leading-relaxed text-muted">
          We use Google Analytics to see which pages people use, so we know what to improve. Allowing it lets Google set
          analytics cookies. Ads are not affected by this choice.{" "}
          <Link href="/privacy" className="underline underline-offset-2 hover:text-text">Privacy</Link>
        </p>
        <div className="mt-3 grid grid-cols-2 gap-2">
          <button type="button" onClick={() => choose("denied")} className="rounded-xl border border-white/[0.16] px-3 py-2 text-sm font-semibold text-text transition hover:bg-white/[0.06]">
            Reject
          </button>
          <button type="button" onClick={() => choose("granted")} className="rounded-xl border border-white/[0.16] px-3 py-2 text-sm font-semibold text-text transition hover:bg-white/[0.06]">
            Allow
          </button>
        </div>
      </div>
    </div>
  );
}

/** Reopens the banner, for the privacy page: withdrawing must be as easy as agreeing. */
export function ConsentSettingsButton() {
  return (
    <button
      type="button"
      onClick={() => {
        try { window.localStorage.removeItem(KEY); } catch { /* nothing stored */ }
        apply("denied");
        window.dispatchEvent(new Event(OPEN_EVENT));
      }}
      className="mt-3 rounded-xl border border-line px-3.5 py-2 text-sm font-medium text-muted transition hover:text-text"
    >
      Change analytics choice
    </button>
  );
}
