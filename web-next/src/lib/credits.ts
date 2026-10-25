import { kvGetNumber, kvIncr, kvPushCapped, kvSetAdd } from "@/lib/kv";
import { STRIPE_SECRET_KEY, stripeGet, stripeKeyConfigured } from "@/lib/stripe";
import { impressumComplete } from "@/lib/impressum";

/**
 * Generation credits: paid top-ups on the daily allowance.
 *
 * Chosen over the Plus subscription on 2026-10-25. Usage showed occasional
 * heavy days rather than daily heavy users (4 signed-in limit hits in 30
 * days), which a pack fits and a subscription does not, and a one-off
 * payment has no renewals, dunning or cancellation flow to run.
 *
 * How they are spent: the free daily allowance first, then one credit per
 * generation, so a buyer never pays for something the free tier would have
 * covered. Credits never expire. Only signed-in players hold credits; the
 * balance is keyed to the Google account, not the device.
 *
 * Prices live in Stripe, not here: each pack is a one-time Price whose id is
 * an environment variable, and the amount shown on the site is read back from
 * Stripe, so the page can never show a price the checkout does not charge.
 * A pack with no price id configured is simply not offered.
 */

export interface CreditPack {
  id: "starter" | "regular" | "big";
  credits: number;
  priceId: string;
}

export const CREDIT_PACKS: CreditPack[] = [
  { id: "starter", credits: 25, priceId: process.env.STRIPE_CREDITS_STARTER_PRICE_ID ?? "" },
  { id: "regular", credits: 75, priceId: process.env.STRIPE_CREDITS_REGULAR_PRICE_ID ?? "" },
  { id: "big", credits: 200, priceId: process.env.STRIPE_CREDITS_BIG_PRICE_ID ?? "" },
];

/** Packs on sale. Nothing is offered until Stripe is set up AND the seller
 *  can be named on /impressum: a consumer sale needs both. */
export function availablePacks(): CreditPack[] {
  if (!stripeKeyConfigured() || !impressumComplete()) return [];
  return CREDIT_PACKS.filter((p) => p.priceId);
}

export function creditsConfigured(): boolean {
  return availablePacks().length > 0;
}

export function packById(id: unknown): CreditPack | undefined {
  return availablePacks().find((p) => p.id === id);
}

const balanceKey = (userSub: string) => `credits:balance:${userSub}`;
/** Every checkout session ever credited. The webhook can deliver the same
 *  event more than once; membership here is what makes a top-up happen once. */
const CREDITED_SESSIONS = "credits:sessions";
const LOG = "credits:log";

export async function getCredits(userSub: string): Promise<number> {
  return Math.max(0, await kvGetNumber(balanceKey(userSub)));
}

/** Adds a paid pack exactly once per checkout session. Returns the new
 *  balance, or null when the session had already been credited. */
export async function grantCredits(userSub: string, credits: number, sessionId: string): Promise<number | null> {
  if (!(await kvSetAdd(CREDITED_SESSIONS, sessionId))) return null;
  const balance = await kvIncr(balanceKey(userSub), credits);
  await kvPushCapped(LOG, JSON.stringify({ at: new Date().toISOString(), userSub, credits, sessionId, balance }), 5000)
    .catch(() => undefined);
  return balance;
}

/** Spends one credit. Atomic against concurrent generations: the decrement
 *  happens first and is undone when it went below zero, so two parallel
 *  requests can never both spend the last credit. */
export async function spendCredit(userSub: string): Promise<{ ok: boolean; balance: number }> {
  const next = await kvIncr(balanceKey(userSub), -1);
  if (next < 0) {
    await kvIncr(balanceKey(userSub), 1);
    return { ok: false, balance: 0 };
  }
  return { ok: true, balance: next };
}

/** Gives back a credit spent on a generation that failed before the model ran. */
export async function refundCredit(userSub: string): Promise<number> {
  return kvIncr(balanceKey(userSub), 1);
}

export interface PackOffer {
  id: CreditPack["id"];
  credits: number;
  /** Formatted by Stripe's own amount and currency, e.g. "€2.99". */
  price: string;
  amount: number;
  currency: string;
}

let offerCache: { at: number; offers: PackOffer[] } | null = null;
const OFFER_TTL_MS = 10 * 60 * 1000;

/** The packs on sale with their real Stripe prices, cached for ten minutes.
 *  A pack whose price cannot be read is left out rather than shown wrong. */
export async function packOffers(): Promise<PackOffer[]> {
  if (!STRIPE_SECRET_KEY) return [];
  if (offerCache && Date.now() - offerCache.at < OFFER_TTL_MS) return offerCache.offers;
  const offers = (await Promise.all(availablePacks().map(async (pack) => {
    try {
      const price = await stripeGet<{ unit_amount?: number; currency?: string; active?: boolean }>(
        `prices/${encodeURIComponent(pack.priceId)}`);
      if (!price.active || typeof price.unit_amount !== "number" || !price.currency) return null;
      const currency = price.currency.toUpperCase();
      const formatted = new Intl.NumberFormat("en-IE", { style: "currency", currency })
        .format(price.unit_amount / 100);
      return { id: pack.id, credits: pack.credits, price: formatted, amount: price.unit_amount, currency };
    } catch (error) {
      console.error(`Could not read the Stripe price for the ${pack.id} pack`, error);
      return null;
    }
  }))).filter((o): o is PackOffer => o != null);
  offerCache = { at: Date.now(), offers };
  return offers;
}
