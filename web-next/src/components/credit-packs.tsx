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
 * withdraw within 14 days. So the button stays disabled until the box is
 * ticked, the server refuses a checkout without it, and the timestamp of the
 * agreement travels to Stripe in the session metadata as the record.
 *
 * Prices are Stripe's own (lib/credits.ts reads them back), never typed here.
 */

interface Offer { id: string; credits: number; price: string; amount: number }

export function CreditPacks({ compact = false }: { compact?: boolean }) {
  const [offers, setOffers] = useState<Offer[] | null>(null);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    fetch("/api/billing/credits", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : { offers: [] }))
      .then((d: { offers?: Offer[] }) => { if (live) setOffers(d.offers ?? []); })
      .catch(() => { if (live) setOffers([]); });
    return () => { live = false; };
  }, []);

  if (!offers || offers.length === 0) return null;

  const cheapest = Math.min(...offers.map((o) => o.amount / o.credits));

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

  return (
    <div className={compact ? "mt-3" : ""}>
      <div className={`grid gap-2 ${offers.length > 1 ? "sm:grid-cols-3" : ""}`}>
        {offers.map((offer) => {
          const per = offer.amount / offer.credits;
          return (
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
                {per === cheapest && offers.length > 1 ? <span className="ml-1.5 text-accent">best value</span> : null}
              </span>
            </button>
          );
        })}
      </div>
      <label className="mt-2.5 flex items-start gap-2 text-[0.7rem] leading-relaxed text-muted">
        <input
          type="checkbox"
          checked={consent}
          onChange={(e) => setConsent(e.target.checked)}
          className="mt-0.5 h-3.5 w-3.5 shrink-0 accent-[var(--color-accent)]"
        />
        <span>
          I want the credits added straight away, and I understand that I lose my right of withdrawal once they are.
          See the <Link href="/terms#credits" className="underline hover:text-text">terms</Link>.
        </span>
      </label>
      <p className="mt-1.5 text-[0.65rem] text-faint">Credits never expire and are used only after your free daily builds.</p>
      {error && <p className="mt-2 text-xs text-rose-300">{error}</p>}
    </div>
  );
}
