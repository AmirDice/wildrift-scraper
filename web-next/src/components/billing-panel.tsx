"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { GoogleSignInButton } from "@/components/google-sign-in";
import { useAccount } from "@/components/account-provider";

type PlusPrice = { interval: "monthly" | "yearly"; amount: number; currency: string };

type BillingState = {
  billingConfigured: boolean;
  prices?: PlusPrice[];
  plan: { id: string; name: string; dailyBuilds: number; description?: string };
  subscription: {
    plan: string;
    name: string;
    active: boolean;
    status: string | null;
    currentPeriodEnd: number | null;
    cancelAtPeriodEnd: boolean;
    dailyBuilds: number | null;
  };
};

export function BillingPanel() {
  const { user, authConfigured, refresh } = useAccount();
  const [billing, setBilling] = useState<BillingState | null>(null);
  const [busy, setBusy] = useState<"checkout" | "portal" | null>(null);
  const [interval, setInterval] = useState<"monthly" | "yearly">("monthly");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const response = await fetch("/api/billing/me", { cache: "no-store" });
      if (response.ok) setBilling((await response.json()) as BillingState);
    } catch { /* the account page remains useful if billing is unavailable */ }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const openBilling = async (kind: "checkout" | "portal") => {
    setBusy(kind);
    setError("");
    try {
      const response = await fetch(`/api/billing/${kind}`, {
        method: "POST",
        headers: kind === "checkout" ? { "Content-Type": "application/json" } : undefined,
        body: kind === "checkout" ? JSON.stringify({ interval }) : undefined,
      });
      const data = (await response.json()) as { url?: string; error?: string };
      if (!response.ok || !data.url) throw new Error(data.error || "Billing is unavailable right now.");
      window.location.assign(data.url);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Billing is unavailable right now.");
      setBusy(null);
    }
  };

  if (!authConfigured) {
    return <Notice title="Accounts are being prepared" body="Sign-in and subscriptions will appear here once account credentials are enabled." />;
  }

  if (!user) {
    return (
      <div className="glass-card rounded-2xl p-6 sm:p-8">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">WRTrueMeta Plus</p>
        <h1 className="mt-3 text-2xl font-bold text-text sm:text-3xl">More room to test your builds.</h1>
        <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted">
          Plus raises the daily Build Studio allowance from 3 generations to {billing?.plan.dailyBuilds ?? 20}.
          Sign in first so the subscription stays attached to your account.
        </p>
        <div className="mt-6 max-w-xs"><GoogleSignInButton onDone={() => { void refresh(); }} /></div>
        <p className="mt-4 text-xs text-faint">You can keep using the free tier without subscribing.</p>
      </div>
    );
  }

  const active = billing?.subscription.active ?? false;
  return (
    <div className="glass-card rounded-2xl p-6 sm:p-8">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">Account & billing</p>
      <div className="mt-3 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-text sm:text-3xl">{active ? "WRTrueMeta Plus" : "Unlock WRTrueMeta Plus"}</h1>
          <p className="mt-2 text-sm text-muted">Signed in as {user.email}</p>
        </div>
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${active ? "bg-emerald-400/15 text-emerald-300" : "bg-white/[0.08] text-muted"}`}>
          {active ? "Active" : "Free plan"}
        </span>
      </div>
      {/* Only what Plus changes. Regions and the advisor itself are the same
          for everyone; the first draft listed both as Plus features. */}
      <div className="mt-6 grid gap-3 sm:grid-cols-2">
        <Feature title={`${billing?.plan.dailyBuilds ?? 20} builds a day`} body="Up from 3. Test more champions, biases, matchups and team comps in one session." />
        <Feature title="Keeps the free tier running" body="Every generation is a paid model call. Plus covers that cost for the people who use it most." />
      </div>
      {billing?.subscription.cancelAtPeriodEnd && (
        <p className="mt-5 rounded-xl border border-gold/25 bg-gold/10 px-4 py-3 text-sm text-gold">Your Plus access is scheduled to end at the current billing period.</p>
      )}
      {error && <p className="mt-5 rounded-xl border border-bad/25 bg-bad/10 px-4 py-3 text-sm text-bad">{error}</p>}
      <div className="mt-6 flex flex-wrap gap-3">
        {active ? (
          <button onClick={() => void openBilling("portal")} disabled={busy !== null} className="rounded-xl bg-accent px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:brightness-110 disabled:opacity-60">
            {busy === "portal" ? "Opening…" : "Manage subscription"}
          </button>
        ) : (
          <div className="flex flex-wrap items-center gap-2">
            {(billing?.prices?.length ?? 0) > 0 && (
              <div className="flex rounded-xl border border-line bg-white/[0.04] p-1 text-xs">
                {billing!.prices!.map((price) => (
                  <button key={price.interval} type="button" onClick={() => setInterval(price.interval)}
                    className={`rounded-lg px-3 py-2 ${interval === price.interval ? "bg-accent text-slate-950" : "text-muted"}`}>
                    {formatPrice(price)}
                  </button>
                ))}
              </div>
            )}
            <button onClick={() => void openBilling("checkout")} disabled={busy !== null || billing?.billingConfigured === false} className="rounded-xl bg-accent px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:brightness-110 disabled:opacity-60">
              {busy === "checkout" ? "Opening…" : "Start Plus"}
            </button>
          </div>
        )}
        <Link href="/build" className="rounded-xl border border-line px-4 py-2.5 text-sm font-medium text-muted transition hover:text-text">Back to Build Studio</Link>
      </div>
      {billing?.billingConfigured === false && <p className="mt-4 text-xs text-faint">Subscriptions are being connected. Checkout will appear here when Stripe is enabled.</p>}
      <p className="mt-4 text-xs text-faint">Payments and cancellation are handled by Stripe. Cancel anytime from Manage subscription.</p>
    </div>
  );
}

/** The price exactly as Stripe charges it, in the visitor's locale. */
function formatPrice(price: PlusPrice): string {
  const amount = new Intl.NumberFormat(undefined, { style: "currency", currency: price.currency.toUpperCase() })
    .format(price.amount / 100);
  return `${amount} / ${price.interval === "yearly" ? "year" : "month"}`;
}

function Feature({ title, body }: { title: string; body: string }) {
  return <div className="rounded-xl border border-line bg-white/[0.04] p-4"><p className="text-sm font-semibold text-text">{title}</p><p className="mt-1 text-xs leading-relaxed text-faint">{body}</p></div>;
}

function Notice({ title, body }: { title: string; body: string }) {
  return <div className="glass-card rounded-2xl p-6 sm:p-8"><h1 className="text-2xl font-bold text-text">{title}</h1><p className="mt-3 text-sm leading-relaxed text-muted">{body}</p></div>;
}
