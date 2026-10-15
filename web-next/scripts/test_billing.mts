/** Billing tests: the Stripe webhook projection, signature check and prices.
 *
 *    npx tsx --test scripts/test_billing.mts
 *
 * Stripe is a stubbed fetch and KV is the in-memory fallback: the KV
 * variables are removed before anything loads, because .env.local points at
 * the PRODUCTION database (see the kv-local-shares-prod memory).
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import crypto from "node:crypto";

for (const name of ["KV_REST_API_URL", "KV_REST_API_TOKEN", "UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN"]) {
  delete process.env[name];
}
process.env.STRIPE_SECRET_KEY = "rk_test_unit";
process.env.STRIPE_PLUS_MONTHLY_PRICE_ID = "price_month";
process.env.STRIPE_PLUS_YEARLY_PRICE_ID = "price_year";
process.env.STRIPE_WEBHOOK_SECRET = "whsec_unit";

/** Subscriptions as the stubbed Stripe API currently holds them. */
const stripe: Record<string, Record<string, unknown>> = {};
const realFetch = globalThis.fetch;
globalThis.fetch = (async (input: string | URL | Request) => {
  const url = String(input instanceof Request ? input.url : input);
  const sub = url.match(/\/v1\/subscriptions\/([^/?]+)/)?.[1];
  if (sub && stripe[sub]) return new Response(JSON.stringify(stripe[sub]), { status: 200 });
  const price = url.match(/\/v1\/prices\/([^/?]+)/)?.[1];
  if (price === "price_month") return new Response(JSON.stringify({ unit_amount: 499, currency: "eur", active: true }));
  if (price === "price_year") return new Response(JSON.stringify({ unit_amount: 3999, currency: "eur", active: true }));
  if (url.startsWith("https://api.stripe.com")) {
    return new Response(JSON.stringify({ error: { message: "not stubbed" } }), { status: 404 });
  }
  return realFetch(input as RequestInfo);
}) as typeof fetch;

const sub = await import("../src/lib/subscription");
const stripeLib = await import("../src/lib/stripe");
const webhook = await import("../src/app/api/billing/webhook/route");

function signed(body: string): Request {
  const t = Math.floor(Date.now() / 1000);
  const v1 = crypto.createHmac("sha256", "whsec_unit").update(`${t}.${body}`).digest("hex");
  return new Request("https://wrtruemeta.com/api/billing/webhook", {
    method: "POST", body, headers: { "stripe-signature": `t=${t},v1=${v1}` },
  });
}

async function send(type: string, object: Record<string, unknown>) {
  const response = await webhook.POST(signed(JSON.stringify({ type, data: { object } })));
  return response.status;
}

function subscription(id: string, status: string, extra: Record<string, unknown> = {}) {
  return {
    id, status, customer: "cus_1", cancel_at_period_end: false,
    metadata: { user_sub: "google-user-1" },
    // API 2025-03-31: the period end lives on the item.
    items: { data: [{ price: { id: "price_month" }, current_period_end: 1_900_000_000 }] },
    ...extra,
  };
}

test("an unpaid checkout does not grant Plus", async () => {
  stripe.sub_unpaid = subscription("sub_unpaid", "incomplete", { metadata: {} });
  assert.equal(await send("checkout.session.completed", {
    subscription: "sub_unpaid", customer: "cus_unpaid", client_reference_id: "google-unpaid",
    payment_status: "unpaid", metadata: { user_sub: "google-unpaid" },
  }), 200);
  const record = await sub.getSubscription("google-unpaid");
  assert.equal(record?.status, "incomplete");
  assert.equal(sub.isProSubscription(record), false);
});

test("a paid checkout grants Plus and reads the item-level period end", async () => {
  stripe.sub_1 = subscription("sub_1", "active");
  assert.equal(await send("checkout.session.completed", {
    subscription: "sub_1", customer: "cus_1", client_reference_id: "google-user-1",
    metadata: { user_sub: "google-user-1" },
  }), 200);
  const record = await sub.getSubscription("google-user-1");
  assert.equal(sub.isProSubscription(record), true);
  assert.equal(record?.currentPeriodEnd, 1_900_000_000);
  assert.equal(record?.priceId, "price_month");
});

test("a late event cannot overwrite a newer status", async () => {
  // Stripe already holds the cancellation; a stale `updated` saying active
  // arrives afterwards. The stored status must be Stripe's current one.
  stripe.sub_1 = subscription("sub_1", "canceled");
  await send("customer.subscription.updated", subscription("sub_1", "active"));
  assert.equal((await sub.getSubscription("google-user-1"))?.status, "canceled");
});

test("an invoice on the new API shape finds its subscription", async () => {
  stripe.sub_1 = subscription("sub_1", "active");
  await send("invoice.paid", {
    customer: "cus_1",
    parent: { subscription_details: { subscription: "sub_1" } },
  });
  assert.equal((await sub.getSubscription("google-user-1"))?.status, "active");
  assert.equal(sub.invoiceSubscriptionId({ subscription: "sub_old" }), "sub_old");
});

test("a failed payment is stored as Stripe reports it", async () => {
  stripe.sub_1 = subscription("sub_1", "past_due");
  await send("invoice.payment_failed", { customer: "cus_1", subscription: "sub_1" });
  const record = await sub.getSubscription("google-user-1");
  assert.equal(record?.status, "past_due");
  assert.equal(sub.isProSubscription(record), false);
});

test("a forged signature is rejected", async () => {
  const body = JSON.stringify({ type: "customer.subscription.updated", data: { object: subscription("sub_1", "active") } });
  const forged = new Request("https://wrtruemeta.com/api/billing/webhook", {
    method: "POST", body, headers: { "stripe-signature": `t=${Math.floor(Date.now() / 1000)},v1=${"0".repeat(64)}` },
  });
  assert.equal((await webhook.POST(forged)).status, 400);
  assert.equal(stripeLib.verifyStripeWebhook(body, null), false);
});

test("prices come from Stripe, not the page", async () => {
  const prices = await sub.plusPrices();
  assert.deepEqual(prices, [
    { interval: "monthly", amount: 499, currency: "eur" },
    { interval: "yearly", amount: 3999, currency: "eur" },
  ]);
});
