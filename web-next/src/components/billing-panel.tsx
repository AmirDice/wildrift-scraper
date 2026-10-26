"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { GoogleSignInButton } from "@/components/google-sign-in";
import { useAccount, type AccountUser, type QuotaState } from "@/components/account-provider";
import { CreditPacks } from "@/components/credit-packs";
import { SIGNED_IN_DAILY_BUILDS } from "@/lib/quota-limits";

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

/**
 * The account page: who you are, what you have left today, your credits, and
 * the packs.
 *
 * Credit packs replaced Plus as the paid option on 2026-10-25. The Plus block
 * stays for a deployment that has Plus prices configured, and for anyone who
 * already subscribes, but by default the page is about the balance and the
 * packs. Data loading lives here; the layout is AccountView, which takes
 * plain props so it can be rendered with sample numbers.
 */
export function BillingPanel() {
  const { user, quota, authConfigured, refresh, signOut } = useAccount();
  const [notice, setNotice] = useState<"success" | "cancelled" | null>(null);
  const [billing, setBilling] = useState<BillingState | null>(null);

  // Back from Stripe Checkout. The webhook usually lands within a second or
  // two of the redirect, so the balance is re-read a few times rather than
  // once, and the query string is cleaned so a reload does not repeat it.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const result = params.get("credits");
    if (result !== "success" && result !== "cancelled") return;
    const timer = window.setTimeout(() => setNotice(result), 0);
    params.delete("credits");
    window.history.replaceState(null, "", `${window.location.pathname}${params.size ? `?${params}` : ""}`);
    if (result !== "success") return () => window.clearTimeout(timer);
    const timers = [1500, 4000, 9000].map((ms) => window.setTimeout(() => { void refresh(); }, ms));
    return () => { window.clearTimeout(timer); timers.forEach((id) => window.clearTimeout(id)); };
  }, [refresh]);

  const load = useCallback(async () => {
    try {
      const response = await fetch("/api/billing/me", { cache: "no-store" });
      if (response.ok) setBilling((await response.json()) as BillingState);
    } catch { /* the account page remains useful if billing is unavailable */ }
  }, []);
  useEffect(() => { void load(); }, [load]);

  if (!authConfigured) {
    return <Panel><h2 className="text-xl font-bold text-text">Accounts are being prepared</h2><p className="mt-2 text-sm leading-relaxed text-muted">Sign-in and build credits will appear here once account credentials are enabled.</p></Panel>;
  }

  if (!user) {
    return (
      <Panel className="overflow-hidden">
        <div className="grid gap-6 sm:grid-cols-[1fr_auto] sm:items-center">
          <div>
            <p className="text-[0.65rem] font-bold uppercase tracking-[0.2em] text-accent">Your account</p>
            <h2 className="mt-2 text-2xl font-bold tracking-tight text-text sm:text-3xl">Sign in for {SIGNED_IN_DAILY_BUILDS} free builds a day</h2>
            <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted">
              Your free generations come back every day. When you want more, credit packs add extra builds on top. No subscription.
            </p>
          </div>
          <div className="w-full max-w-xs"><GoogleSignInButton onDone={() => { void refresh(); }} /></div>
        </div>
      </Panel>
    );
  }

  return (
    <AccountView
      user={user}
      quota={quota}
      notice={notice}
      onDismissNotice={() => setNotice(null)}
      onSignOut={() => { void signOut(); }}
      plus={billing && (billing.subscription.active || billing.billingConfigured) ? <PlusBlock billing={billing} /> : null}
    />
  );
}

/** The signed-in layout, from plain props. */
export function AccountView({ user, quota, notice, onDismissNotice, onSignOut, plus, packs }: {
  user: AccountUser;
  quota: QuotaState | null;
  notice?: "success" | "cancelled" | null;
  onDismissNotice?: () => void;
  onSignOut?: () => void;
  plus?: React.ReactNode;
  /** Replaces the live pack picker; for rendering with sample data. */
  packs?: React.ReactNode;
}) {
  const credits = quota?.credits ?? 0;
  const unlimited = Boolean(quota?.unlimited);
  const limit = quota?.limit ?? SIGNED_IN_DAILY_BUILDS;
  const remaining = quota?.remaining ?? limit;
  // Read the clock after mount: during render it would differ between the
  // server and the browser.
  const [hours, setHours] = useState<number | null>(null);
  useEffect(() => {
    if (!quota?.resetAt) return;
    const timer = window.setTimeout(() => setHours(Math.max(1, Math.ceil((quota.resetAt - Date.now()) / 3_600_000))), 0);
    return () => window.clearTimeout(timer);
  }, [quota?.resetAt]);

  return (
    <div className="space-y-5">
      {/* Who you are */}
      <Panel className="flex flex-wrap items-center gap-4">
        {user.picture
          // eslint-disable-next-line @next/next/no-img-element -- Google avatar, external and tiny
          ? <img src={user.picture} alt="" referrerPolicy="no-referrer" className="h-12 w-12 rounded-full border border-white/15" />
          : <span className="grid h-12 w-12 place-items-center rounded-full bg-accent/15 text-lg font-bold text-accent">{(user.name || user.email).slice(0, 1).toUpperCase()}</span>}
        <div className="min-w-0 flex-1">
          <p className="truncate text-lg font-semibold text-text">{user.name || "Your account"}</p>
          <p className="truncate text-sm text-faint">{user.email}</p>
        </div>
        {onSignOut && (
          <button type="button" onClick={onSignOut} className="rounded-xl border border-line px-3.5 py-2 text-sm font-medium text-muted transition hover:text-text">
            Sign out
          </button>
        )}
      </Panel>

      {notice === "success" && (
        <Banner tone="good" onClose={onDismissNotice}>
          Payment received. Your credits are added within a few seconds, and Stripe has emailed your receipt.
        </Banner>
      )}
      {notice === "cancelled" && (
        <Banner tone="muted" onClose={onDismissNotice}>Checkout cancelled. Nothing was charged.</Banner>
      )}

      {/* What you have */}
      <div className="grid grid-cols-2 gap-3 sm:gap-4">
        <Panel>
          <p className="text-[0.65rem] font-bold uppercase tracking-[0.16em] text-faint">Free today</p>
          {unlimited ? (
            <p className="mt-2 text-3xl font-bold text-text">Unlimited</p>
          ) : (
            <>
              <p className="mt-2 flex items-baseline gap-1.5 tabular-nums">
                <span className="text-3xl font-bold text-text">{remaining}</span>
                <span className="text-sm text-muted">of {limit} left</span>
              </p>
              <div className="mt-3 flex gap-1.5" aria-hidden>
                {Array.from({ length: limit }, (_, i) => (
                  <span key={i} className={`h-1.5 flex-1 rounded-full ${i < remaining ? "bg-accent" : "bg-white/[0.1]"}`} />
                ))}
              </div>
              <p className="mt-3 text-xs text-faint">Back to {limit} {hours == null ? "at midnight UTC" : `in about ${hours} ${hours === 1 ? "hour" : "hours"}`}.</p>
            </>
          )}
        </Panel>
        <Panel className={credits > 0 ? "ring-1 ring-accent/25" : ""}>
          <p className="text-[0.65rem] font-bold uppercase tracking-[0.16em] text-faint">Credits</p>
          <p className="mt-2 flex items-baseline gap-1.5 tabular-nums">
            <span className={`text-3xl font-bold ${credits > 0 ? "text-accent" : "text-text"}`}>{credits}</span>
            <span className="text-sm text-muted">{credits === 1 ? "build" : "builds"}</span>
          </p>
          <p className="mt-3 text-xs leading-relaxed text-faint">
            {credits > 0 ? "Used after your free builds run out. They never expire." : "Buy a pack below when the free builds are not enough."}
          </p>
        </Panel>
      </div>

      {/* Buy more */}
      {(packs || quota?.creditsAvailable) && (
        <Panel>
          <h2 className="text-lg font-semibold text-text">Get more builds</h2>
          <p className="mt-1 text-sm text-muted">Pay once. No subscription, nothing renews.</p>
          <div className="mt-4">{packs ?? <CreditPacks variant="cards" />}</div>
        </Panel>
      )}

      {/* How it works */}
      <Panel>
        <h2 className="text-sm font-semibold text-text">How credits work</h2>
        <ul className="mt-3 grid gap-3 text-sm leading-relaxed text-muted sm:grid-cols-3">
          <li className="rounded-xl bg-white/[0.035] p-3"><span className="font-semibold text-text">Free first.</span> Your {SIGNED_IN_DAILY_BUILDS} daily builds are always used before any credit.</li>
          <li className="rounded-xl bg-white/[0.035] p-3"><span className="font-semibold text-text">One per build.</span> Counter builds and &ldquo;why not&rdquo; answers cost one too. A build that fails to start gives its credit back.</li>
          <li className="rounded-xl bg-white/[0.035] p-3"><span className="font-semibold text-text">Never expire.</span> Credits stay on your Google account until you use them.</li>
        </ul>
        <p className="mt-4 text-xs text-faint">
          Payments are handled by Stripe; card details never reach this site.{" "}
          <Link href="/terms#credits" className="underline underline-offset-2 hover:text-text">Terms</Link>
          {" · "}
          <Link href="/impressum" className="underline underline-offset-2 hover:text-text">Impressum</Link>
          {" · "}
          <Link href="/contact" className="underline underline-offset-2 hover:text-text">Problem with a payment?</Link>
        </p>
      </Panel>

      {plus}

      <div>
        <Link href="/build" className="inline-flex rounded-xl border border-line px-4 py-2.5 text-sm font-medium text-muted transition hover:text-text">
          Back to Build Studio
        </Link>
      </div>
    </div>
  );
}

/** Plus, for a deployment that sells it or a player who already has it. */
function PlusBlock({ billing }: { billing: BillingState }) {
  const [busy, setBusy] = useState<"checkout" | "portal" | null>(null);
  const [interval, setInterval] = useState<"monthly" | "yearly">("monthly");
  const [error, setError] = useState("");
  const active = billing.subscription.active;

  const open = async (kind: "checkout" | "portal") => {
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

  return (
    <Panel>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-text">WRTrueMeta Plus</h2>
          <p className="mt-1 text-sm text-muted">{billing.plan.dailyBuilds} builds a day instead of {SIGNED_IN_DAILY_BUILDS}.</p>
        </div>
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${active ? "bg-emerald-400/15 text-emerald-300" : "bg-white/[0.08] text-muted"}`}>
          {active ? "Active" : "Not subscribed"}
        </span>
      </div>
      {billing.subscription.cancelAtPeriodEnd && (
        <p className="mt-4 rounded-xl border border-gold/25 bg-gold/10 px-4 py-3 text-sm text-gold">Your Plus access ends at the close of the current billing period.</p>
      )}
      {error && <p className="mt-4 rounded-xl border border-bad/25 bg-bad/10 px-4 py-3 text-sm text-bad">{error}</p>}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        {active ? (
          <button onClick={() => void open("portal")} disabled={busy !== null} className="rounded-xl bg-accent px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:brightness-110 disabled:opacity-60">
            {busy === "portal" ? "Opening..." : "Manage subscription"}
          </button>
        ) : (
          <>
            {(billing.prices?.length ?? 0) > 0 && (
              <div className="flex rounded-xl border border-line bg-white/[0.04] p-1 text-xs">
                {billing.prices!.map((price) => (
                  <button key={price.interval} type="button" onClick={() => setInterval(price.interval)}
                    className={`rounded-lg px-3 py-2 ${interval === price.interval ? "bg-accent text-slate-950" : "text-muted"}`}>
                    {formatPrice(price)}
                  </button>
                ))}
              </div>
            )}
            <button onClick={() => void open("checkout")} disabled={busy !== null} className="rounded-xl bg-accent px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:brightness-110 disabled:opacity-60">
              {busy === "checkout" ? "Opening..." : "Start Plus"}
            </button>
          </>
        )}
      </div>
    </Panel>
  );
}

/** The price exactly as Stripe charges it, in the visitor's locale. */
function formatPrice(price: PlusPrice): string {
  const amount = new Intl.NumberFormat(undefined, { style: "currency", currency: price.currency.toUpperCase() })
    .format(price.amount / 100);
  return `${amount} / ${price.interval === "yearly" ? "year" : "month"}`;
}

function Panel({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <section className={`glass rounded-2xl border border-white/[0.1] p-5 shadow-[0_18px_60px_rgba(0,0,0,.28)] sm:p-6 ${className}`}>{children}</section>;
}

function Banner({ tone, children, onClose }: { tone: "good" | "muted"; children: React.ReactNode; onClose?: () => void }) {
  return (
    <div role="status" className={`glass flex items-start justify-between gap-3 rounded-2xl border px-4 py-3 text-sm ${tone === "good" ? "border-emerald-400/30 text-emerald-200" : "border-line text-muted"}`}>
      <p>{children}</p>
      {onClose && <button type="button" onClick={onClose} aria-label="Dismiss" className="shrink-0 text-lg leading-none opacity-70 hover:opacity-100">&times;</button>}
    </div>
  );
}
