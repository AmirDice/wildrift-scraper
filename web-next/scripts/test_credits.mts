/** Credit-pack tests: webhook grant, idempotency, spend order and refunds.
 *
 *    npx tsx --test scripts/test_credits.mts
 *
 * Same harness as test_billing.mts: KV variables removed before anything
 * loads (.env.local is the PRODUCTION database), Stripe a stubbed fetch.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import crypto from "node:crypto";

for (const name of ["KV_REST_API_URL", "KV_REST_API_TOKEN", "UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN"]) {
  delete process.env[name];
}
process.env.STRIPE_SECRET_KEY = "rk_test_unit";
process.env.STRIPE_WEBHOOK_SECRET = "whsec_unit";
process.env.STRIPE_CREDITS_STARTER_PRICE_ID = "price_starter";
process.env.IMPRESSUM_NAME = "Test Operator";
process.env.IMPRESSUM_STREET = "Teststr. 1";
process.env.IMPRESSUM_CITY = "10115 Berlin";
process.env.IMPRESSUM_EMAIL = "ops@example.com";

const realFetch = globalThis.fetch;
globalThis.fetch = (async (input: string | URL | Request) => {
  const url = String(input instanceof Request ? input.url : input);
  if (url.endsWith("/v1/prices/price_starter")) {
    return new Response(JSON.stringify({ unit_amount: 299, currency: "eur", active: true }));
  }
  if (url.startsWith("https://api.stripe.com")) {
    return new Response(JSON.stringify({ error: { message: "not stubbed" } }), { status: 404 });
  }
  return realFetch(input as RequestInfo);
}) as typeof fetch;

const credits = await import("../src/lib/credits");
const quota = await import("../src/lib/quota");
const webhook = await import("../src/app/api/billing/webhook/route");

function signed(body: string): Request {
  const t = Math.floor(Date.now() / 1000);
  const v1 = crypto.createHmac("sha256", "whsec_unit").update(`${t}.${body}`).digest("hex");
  return new Request("https://wrtruemeta.com/api/billing/webhook", {
    method: "POST", body, headers: { "stripe-signature": `t=${t},v1=${v1}` },
  });
}

const session = (id: string, paid = true, user = "google-credits-1") => ({
  id, object: "checkout.session", mode: "payment", payment_status: paid ? "paid" : "unpaid",
  client_reference_id: user,
  metadata: { kind: "credits", user_sub: user, pack: "starter", credits: "25" },
});

async function send(type: string, object: Record<string, unknown>) {
  return (await webhook.POST(signed(JSON.stringify({ type, data: { object } })))).status;
}

test("only the configured pack is on sale, at Stripe's price", async () => {
  assert.deepEqual(credits.availablePacks().map((p) => p.id), ["starter"]);
  const offers = await credits.packOffers();
  assert.equal(offers.length, 1);
  assert.equal(offers[0].price, "€2.99");
  assert.equal(offers[0].credits, 25);
});

test("a paid checkout grants the pack once, however often Stripe delivers it", async () => {
  assert.equal(await send("checkout.session.completed", session("cs_1")), 200);
  assert.equal(await send("checkout.session.completed", session("cs_1")), 200);
  assert.equal(await credits.getCredits("google-credits-1"), 25);
});

test("an unpaid checkout grants nothing until the async payment succeeds", async () => {
  const user = "google-credits-2";
  await send("checkout.session.completed", session("cs_2", false, user));
  assert.equal(await credits.getCredits(user), 0);
  await send("checkout.session.async_payment_succeeded", session("cs_2", true, user));
  assert.equal(await credits.getCredits(user), 25);
});

test("free daily generations are spent before credits, and a refund returns the credit", async () => {
  const user = { sub: "google-credits-3", email: "p@example.com", name: "P", picture: "", iat: 0 };
  await credits.grantCredits(user.sub, 2, "cs_3");
  for (let i = 0; i < 3; i += 1) {
    const r = await quota.consumeQuota(user, "1.2.3.4");
    assert.equal(r.ok, true);
    assert.equal(r.source, "daily");
  }
  assert.equal(await credits.getCredits(user.sub), 2);
  const paid = await quota.consumeQuota(user, "1.2.3.4");
  assert.equal(paid.source, "credit");
  assert.equal(paid.quota.credits, 1);
  const back = await quota.refundQuota(user, "1.2.3.4", false, undefined, "credit");
  assert.equal(back.credits, 2);
  await quota.consumeQuota(user, "1.2.3.4");
  await quota.consumeQuota(user, "1.2.3.4");
  const empty = await quota.consumeQuota(user, "1.2.3.4");
  assert.equal(empty.ok, false);
  assert.equal(await credits.getCredits(user.sub), 0);
});

test("two parallel generations cannot both spend the last credit", async () => {
  await credits.grantCredits("google-credits-4", 1, "cs_4");
  const [a, b] = await Promise.all([credits.spendCredit("google-credits-4"), credits.spendCredit("google-credits-4")]);
  assert.equal([a.ok, b.ok].filter(Boolean).length, 1);
  assert.equal(await credits.getCredits("google-credits-4"), 0);
});

test("a subscription event still reaches the Plus path", async () => {
  const status = await send("checkout.session.completed", {
    id: "cs_sub", mode: "subscription", subscription: "sub_x", metadata: { user_sub: "u" },
  });
  // The stub has no such subscription, so the Plus sync fails: 500 proves the
  // credits branch did not swallow the event.
  assert.equal(status, 500);
});
