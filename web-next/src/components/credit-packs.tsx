"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

/**
 * The credit packs on sale, with the waiver EU law asks for before a digital
 * purchase is delivered at once.
 *
 * Credits are added the moment payment clears, so the buyer's 14-day right of
 * withdrawal ends at delivery -- but only if they agreed to that beforehand,
 * knowingly. Without the agreement a buyer could spend every credit and still
 * withdraw within 14 days. So the buttons stay disabled until the box is
 * ticked, the server refuses a checkout without it, and the timestamp of the
 * agreement travels to Stripe in the session metadata as the record.
 *
 * Prices are Stripe's own (lib/credits.ts reads them back), never typed here.
 *
 * Two layouts: `compact` for the limit wall inside the Build Studio, `cards`
 * for the account page, where there is room to show the price per build.
 */

interface Offer { id: string; credits: number; price: string; amount: number; currency: string }

const LABEL: Record<string, string> = { starter: "Starter", regular: "Regular", big: "Big" };

function perBuild(offer: Offer): string {
  const value = offer.amount / offer.credits / 100;
  return new Intl.NumberFormat("en-IE", { style: "currency", currency: offer.currency, minimumFractionDigits: 2, maximumFractionDigits: 3 })
    .format(value);
}

export function CreditPacks({ variant = "compact", initialOffers }: {
  variant?: "compact" | "cards";
  /** Skips the fetch; for rendering with sample prices. */
  initialOffers?: Offer[];
}) {
  const [offers, setOffers] = useState<Offer[] | null>(initialOffers ?? null);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (initialOffers) return;
    let live = true;
    fetch("/api/billing/credits", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : { offers: [] }))
      .then((d: { offers?: Offer[] }) => { if (live) setOffers(d.offers ?? []); })
      .catch(() => { if (live) setOffers([]); });
    return () => { live = false; };
  }, [initialOffers]);

  if (offers === null) {
    return variant === "cards"
      ? <div className="grid gap-3 sm:grid-cols-3">{[0, 1, 2].map((i) => <div key={i} className="h-40 animate-pulse rounded-2xl bg-white/[0.04]" />)}</div>
      : null;
  }
  if (offers.length === 0) return null;

  const cheapest = Math.min(...offers.map((o) => o.amount / o.credits));
  const best = offers.length > 1 ? offers.find((o) => o.amount / o.credits === cheapest)?.id : undefined;

  async function buy(pack: string) {
    setBusy(pack);
    setError(null);
    try {
      const res = await fetch("/api/billing/credits", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pack, waiveWithdrawal: consent }),
      });
      const data = (await res.json()) as { url?: string; error?: string };
      if (!res.ok || !data.url) throw new Error(data.error || "Could not start checkout.");
      window.location.assign(data.url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start checkout.");
      setBusy(null);
    }
  }

  const consentBox = (
    <label className={`flex items-start gap-2.5 rounded-xl px-3 py-2.5 text-xs leading-relaxed transition ${consent ? "bg-accent/[0.08] text-text" : "bg-white/[0.04] text-muted"}`}>
      <input
        type="checkbox"
        checked={consent}
        onChange={(e) => setConsent(e.target.checked)}
        className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--color-accent)]"
      />
      <span>
        I want the credits added straight away, and I understand that I lose my right of withdrawal once they are.{" "}
        <Link href="/terms#credits" className="underline underline-offset-2 hover:text-text">Terms</Link>
      </span>
    </label>
  );

  if (variant === "compact") {
    return (
      <div className="mt-3 space-y-2.5">
        <div className={`grid gap-2 ${offers.length > 1 ? "sm:grid-cols-3" : ""}`}>
          {offers.map((offer) => (
            <button
              key={offer.id}
              type="button"
              disabled={!consent || busy != null}
              onClick={() => buy(offer.id)}
              className="flex flex-col items-start rounded-xl border border-white/[0.1] bg-white/[0.04] px-3 py-2.5 text-left transition hover:border-accent/50 hover:bg-accent/[0.06] disabled:cursor-not-allowed disabled:opacity-45"
            >
              <span className="text-sm font-semibold text-text">{offer.credits} builds</span>
              <span className="text-xs text-muted">
                {busy === offer.id ? "Opening checkout..." : offer.price}
                {offer.id === best ? <span className="ml-1.5 text-accent">best value</span> : null}
              </span>
            </button>
          ))}
        </div>
        {consentBox}
        {error && <p className="text-xs text-rose-300">{error}</p>}
      </div>
    );
  }

  // The waiver comes FIRST on the account page: below the cards it read as
  // fine print, and the disabled buttons above it looked broken.
  return (
    <div className="space-y-3">
      {consentBox}
      <div className={`grid gap-3 ${offers.length === 3 ? "sm:grid-cols-3" : offers.length === 2 ? "sm:grid-cols-2" : ""}`}>
        {offers.map((offer) => {
          const featured = offer.id === best;
          return (
            <div
              key={offer.id}
              className={`relative flex flex-col rounded-2xl border p-4 transition ${featured ? "border-accent/40 bg-accent/[0.07]" : "border-white/[0.09] bg-white/[0.035]"}`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-[0.65rem] font-bold uppercase tracking-[0.16em] text-faint">{LABEL[offer.id] ?? offer.id}</span>
                {featured && <span className="rounded-full bg-accent/20 px-2 py-0.5 text-[0.6rem] font-bold uppercase tracking-[0.12em] text-accent">Best value</span>}
              </div>
              <p className="mt-3 flex items-baseline gap-1.5">
                <span className="text-3xl font-bold tabular-nums tracking-tight text-text">{offer.credits}</span>
                <span className="text-sm text-muted">builds</span>
              </p>
              <p className="mt-1 text-xs tabular-nums text-faint">{perBuild(offer)} per build</p>
              <button
                type="button"
                disabled={!consent || busy != null}
                onClick={() => buy(offer.id)}
                title={consent ? undefined : "Tick the box below first"}
                className={`mt-4 rounded-xl px-3 py-2.5 text-sm font-semibold tabular-nums transition disabled:cursor-not-allowed disabled:opacity-40 ${featured ? "bg-accent text-slate-950 hover:brightness-110" : "border border-white/[0.14] text-text hover:border-accent/60 hover:bg-accent/[0.08]"}`}
              >
                {busy === offer.id ? "Opening checkout..." : `Buy for ${offer.price}`}
              </button>
            </div>
          );
        })}
      </div>
      {error && <p className="rounded-xl border border-rose-400/25 bg-rose-400/10 px-3 py-2 text-xs text-rose-300">{error}</p>}
    </div>
  );
}
