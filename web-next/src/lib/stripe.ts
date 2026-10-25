/** Small, dependency-free Stripe HTTP client.
 *
 * Keeping this on fetch instead of adding a second SDK means the site can
 * deploy before Stripe is configured. Every billing route is inert until the
 * server-side Stripe secret, at least one Plus price, and webhook secret are
 * configured.
 */
import crypto from "node:crypto";

export const STRIPE_SECRET_KEY = process.env.STRIPE_SECRET_KEY ?? "";
export const STRIPE_WEBHOOK_SECRET = process.env.STRIPE_WEBHOOK_SECRET ?? "";
export const STRIPE_PLUS_MONTHLY_PRICE_ID =
  process.env.STRIPE_PLUS_MONTHLY_PRICE_ID ?? process.env.STRIPE_PRO_PRICE_ID ?? "";
export const STRIPE_PLUS_YEARLY_PRICE_ID = process.env.STRIPE_PLUS_YEARLY_PRICE_ID ?? "";
/** Legacy alias retained so an existing test deployment keeps working while
 * its environment variables are migrated to the Plus names. */
export const STRIPE_PRO_PRICE_ID = STRIPE_PLUS_MONTHLY_PRICE_ID;
export const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL ?? "https://wrtruemeta.com").replace(/\/$/, "");

/** Plus (the subscription) can be sold: the key and at least one Plus price.
 *  Kept under its original name because every Plus route reads it. */
export function stripeConfigured(): boolean {
  return Boolean(STRIPE_SECRET_KEY && (STRIPE_PLUS_MONTHLY_PRICE_ID || STRIPE_PLUS_YEARLY_PRICE_ID));
}

/** Any Stripe product can be sold. Credit packs need only this plus their
 *  own price ids (lib/credits.ts), so they work with Plus left unconfigured. */
export function stripeKeyConfigured(): boolean {
  return Boolean(STRIPE_SECRET_KEY);
}

/** EU VAT is owner's decision. Off by default (a Kleinunternehmer under
 *  section 19 UStG charges none); STRIPE_AUTOMATIC_TAX=1 turns on Stripe Tax
 *  for every checkout, which needs a tax registration set in the Dashboard. */
export const STRIPE_AUTOMATIC_TAX = process.env.STRIPE_AUTOMATIC_TAX === "1";

export function webhookConfigured(): boolean {
  return Boolean(STRIPE_WEBHOOK_SECRET);
}

/** Stripe recommends an integration identifier for Checkout sessions on recent
 * API versions. Keep the label stable for this app while adding a short random
 * suffix so individual flows remain distinguishable in the Dashboard. */
export function stripeIntegrationIdentifier(flow: string): string {
  const suffix = crypto.randomBytes(4).toString("hex");
  return `wrtruemeta_${flow}_${suffix}`;
}

export async function stripeRequest<T>(path: string, params: URLSearchParams): Promise<T> {
  const response = await fetch(`https://api.stripe.com/v1/${path}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${STRIPE_SECRET_KEY}`,
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: params.toString(),
    cache: "no-store",
  });
  const data = (await response.json()) as T & { error?: { message?: string } };
  if (!response.ok) throw new Error(data.error?.message || `Stripe returned HTTP ${response.status}`);
  return data;
}

/** GET a Stripe object. The webhook reads the subscription itself rather
 *  than trusting the event payload: events can arrive out of order, and a
 *  late `updated` would otherwise overwrite a newer status. */
export async function stripeGet<T>(path: string): Promise<T> {
  const response = await fetch(`https://api.stripe.com/v1/${path}`, {
    headers: { Authorization: `Bearer ${STRIPE_SECRET_KEY}` },
    cache: "no-store",
  });
  const data = (await response.json()) as T & { error?: { message?: string } };
  if (!response.ok) throw new Error(data.error?.message || `Stripe returned HTTP ${response.status}`);
  return data;
}

function signatureParts(header: string): { timestamp: number; signatures: string[] } | null {
  let timestamp = 0;
  const signatures: string[] = [];
  for (const part of header.split(",")) {
    const [key, value] = part.split("=", 2);
    if (key === "t") timestamp = Number(value);
    if (key === "v1" && value) signatures.push(value);
  }
  return Number.isFinite(timestamp) && timestamp > 0 && signatures.length
    ? { timestamp, signatures } : null;
}

/** Verify Stripe's signed raw request body before parsing JSON. */
export function verifyStripeWebhook(rawBody: string, header: string | null): boolean {
  if (!STRIPE_WEBHOOK_SECRET || !header) return false;
  const parts = signatureParts(header);
  if (!parts || Math.abs(Date.now() / 1000 - parts.timestamp) > 300) return false;
  const expected = crypto
    .createHmac("sha256", STRIPE_WEBHOOK_SECRET)
    .update(`${parts.timestamp}.${rawBody}`)
    .digest("hex");
  return parts.signatures.some((signature) => {
    if (signature.length !== expected.length) return false;
    return crypto.timingSafeEqual(Buffer.from(signature), Buffer.from(expected));
  });
}
