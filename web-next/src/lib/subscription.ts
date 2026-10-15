/** Server-side Stripe entitlement state.
 *
 * Stripe is the source of billing truth; KV is the fast, durable projection
 * used by request-time quota checks. Webhooks update this projection, and no
 * browser-provided plan value is ever trusted.
 */
import { kvGetJson, kvSetJson } from "@/lib/kv";
import {
  STRIPE_PLUS_MONTHLY_PRICE_ID,
  STRIPE_PLUS_YEARLY_PRICE_ID,
  stripeConfigured,
  stripeGet,
} from "@/lib/stripe";

/** Paid plan limits are intentionally server-side constants: the browser is
 * never trusted to decide whether a request is entitled to Plus. */
export const PLUS_DAILY_BUILDS = 20;
export const PLUS_PLAN = {
  id: "plus",
  name: "WRTrueMeta Plus",
  dailyBuilds: PLUS_DAILY_BUILDS,
  // Only what Plus actually changes. The first draft also promised "all
  // regions" (every region is free to everyone) and "advanced reasoning"
  // (nothing in the advisor reads the plan).
  description: "20 Build Studio generations a day instead of 3.",
} as const;

/** Backwards-compatible names for routes and existing deployments. */
export const PRO_DAILY_BUILDS = PLUS_DAILY_BUILDS;
export const PRO_PLAN = PLUS_PLAN;

export type StripeSubscriptionStatus =
  | "active"
  | "trialing"
  | "past_due"
  | "canceled"
  | "unpaid"
  | "incomplete"
  | "incomplete_expired"
  | "paused";

export interface SubscriptionRecord {
  userSub: string;
  customerId: string | null;
  subscriptionId: string | null;
  priceId: string | null;
  status: StripeSubscriptionStatus;
  currentPeriodEnd: number | null;
  cancelAtPeriodEnd: boolean;
  createdAt: string;
  updatedAt: string;
}

const subscriptionKey = (userSub: string) => `billing:subscription:${userSub}`;
const customerKey = (customerId: string) => `billing:customer:${customerId}`;
const stripeSubscriptionKey = (subscriptionId: string) => `billing:stripe-sub:${subscriptionId}`;

export async function getSubscription(userSub: string): Promise<SubscriptionRecord | null> {
  return kvGetJson<SubscriptionRecord | null>(subscriptionKey(userSub), null);
}

export function isProSubscription(record: SubscriptionRecord | null | undefined): boolean {
  return Boolean(record && (record.status === "active" || record.status === "trialing"));
}

export function subscriptionSummary(record: SubscriptionRecord | null | undefined) {
  return {
    plan: isProSubscription(record) ? PLUS_PLAN.id : "free",
    name: isProSubscription(record) ? PLUS_PLAN.name : "Free",
    active: isProSubscription(record),
    status: record?.status ?? null,
    currentPeriodEnd: record?.currentPeriodEnd ?? null,
    cancelAtPeriodEnd: record?.cancelAtPeriodEnd ?? false,
    dailyBuilds: isProSubscription(record) ? PLUS_DAILY_BUILDS : null,
  };
}

export async function saveSubscription(record: SubscriptionRecord): Promise<void> {
  await kvSetJson(subscriptionKey(record.userSub), record);
  if (record.customerId) await kvSetJson(customerKey(record.customerId), record.userSub);
  if (record.subscriptionId) await kvSetJson(stripeSubscriptionKey(record.subscriptionId), record.userSub);
}

export async function userSubForCustomer(customerId: string | null | undefined): Promise<string | null> {
  if (!customerId) return null;
  return kvGetJson<string | null>(customerKey(customerId), null);
}

export async function userSubForStripeSubscription(subscriptionId: string | null | undefined): Promise<string | null> {
  if (!subscriptionId) return null;
  return kvGetJson<string | null>(stripeSubscriptionKey(subscriptionId), null);
}

type StripeObject = Record<string, unknown>;

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value ? value : null;
}

/** An expandable Stripe field: either the id itself or the expanded object. */
export function stripeId(value: unknown): string | null {
  if (typeof value === "string") return value || null;
  if (value && typeof value === "object") return stringValue((value as StripeObject).id);
  return null;
}

/**
 * The fields we keep from a Stripe subscription.
 *
 * API version 2025-03-31 moved `current_period_end` from the subscription
 * onto each item; read both so the projection works whichever version the
 * account is pinned to.
 */
export function projectStripeSubscription(object: StripeObject) {
  const items = object.items as StripeObject | undefined;
  const first = (Array.isArray(items?.data) ? items.data : [])[0] as StripeObject | undefined;
  const price = first?.price as StripeObject | undefined;
  const periodEnd = typeof object.current_period_end === "number"
    ? object.current_period_end
    : typeof first?.current_period_end === "number" ? first.current_period_end : null;
  const metadata = object.metadata as StripeObject | undefined;
  return {
    subscriptionId: stringValue(object.id),
    customerId: stripeId(object.customer),
    priceId: stringValue(price?.id),
    status: (stringValue(object.status) ?? "incomplete") as StripeSubscriptionStatus,
    currentPeriodEnd: periodEnd,
    cancelAtPeriodEnd: object.cancel_at_period_end === true,
    userSub: stringValue(metadata?.user_sub),
  };
}

/** The subscription an invoice belongs to. API 2025-03-31 moved it from
 *  `invoice.subscription` to `invoice.parent.subscription_details`. */
export function invoiceSubscriptionId(invoice: StripeObject): string | null {
  const legacy = stripeId(invoice.subscription);
  if (legacy) return legacy;
  const parent = invoice.parent as StripeObject | undefined;
  const details = parent?.subscription_details as StripeObject | undefined;
  return stripeId(details?.subscription);
}

export interface PlusPrice {
  interval: "monthly" | "yearly";
  /** Minor units, as Stripe stores it (499 = 4.99). */
  amount: number;
  currency: string;
}

const PRICE_CACHE_KEY = "billing:plus-prices:v1";

/**
 * The Plus prices as Stripe will actually charge them, for the account page.
 * The first draft hard-coded "4.99 / month" in the button, which drifts the
 * moment a price changes in the Dashboard. Cached for an hour.
 */
export async function plusPrices(): Promise<PlusPrice[]> {
  if (!stripeConfigured()) return [];
  const cached = await kvGetJson<{ ids: string; prices: PlusPrice[] } | null>(PRICE_CACHE_KEY, null);
  const ids = `${STRIPE_PLUS_MONTHLY_PRICE_ID}|${STRIPE_PLUS_YEARLY_PRICE_ID}`;
  if (cached && cached.ids === ids) return cached.prices;
  const wanted: [PlusPrice["interval"], string][] = [
    ["monthly", STRIPE_PLUS_MONTHLY_PRICE_ID],
    ["yearly", STRIPE_PLUS_YEARLY_PRICE_ID],
  ];
  const prices: PlusPrice[] = [];
  for (const [interval, id] of wanted) {
    if (!id) continue;
    try {
      const price = await stripeGet<{ unit_amount?: number | null; currency?: string; active?: boolean }>(
        `prices/${encodeURIComponent(id)}`);
      if (price.active !== false && typeof price.unit_amount === "number" && price.currency) {
        prices.push({ interval, amount: price.unit_amount, currency: price.currency });
      }
    } catch (error) {
      console.error(`Stripe ${interval} Plus price lookup failed`, error);
    }
  }
  if (prices.length) await kvSetJson(PRICE_CACHE_KEY, { ids, prices }, 3600);
  return prices;
}

export function makeSubscriptionRecord(input: {
  userSub: string;
  customerId?: string | null;
  subscriptionId?: string | null;
  priceId?: string | null;
  status: StripeSubscriptionStatus;
  currentPeriodEnd?: number | null;
  cancelAtPeriodEnd?: boolean;
  previous?: SubscriptionRecord | null;
}): SubscriptionRecord {
  const now = new Date().toISOString();
  return {
    userSub: input.userSub,
    customerId: input.customerId ?? input.previous?.customerId ?? null,
    subscriptionId: input.subscriptionId ?? input.previous?.subscriptionId ?? null,
    priceId: input.priceId ?? input.previous?.priceId ?? null,
    status: input.status,
    currentPeriodEnd: input.currentPeriodEnd ?? input.previous?.currentPeriodEnd ?? null,
    cancelAtPeriodEnd: input.cancelAtPeriodEnd ?? input.previous?.cancelAtPeriodEnd ?? false,
    createdAt: input.previous?.createdAt ?? now,
    updatedAt: now,
  };
}
