import { NextResponse } from "next/server";
import {
  getSubscription,
  invoiceSubscriptionId,
  makeSubscriptionRecord,
  projectStripeSubscription,
  saveSubscription,
  stripeId,
  userSubForCustomer,
  userSubForStripeSubscription,
} from "@/lib/subscription";
import { stripeGet, stripeKeyConfigured, verifyStripeWebhook, webhookConfigured } from "@/lib/stripe";
import { CREDIT_PACKS, grantCredits } from "@/lib/credits";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type StripeObject = Record<string, unknown>;

/**
 * Store the subscription AS STRIPE HOLDS IT NOW, never as the event says.
 *
 * The first version projected each event's payload, which had three faults:
 * a checkout that completed unpaid (a pending bank debit) was stored as
 * "trialing", which grants Plus; an `updated` arriving after a newer event
 * overwrote the newer status; and invoices were forced to "active" even for a
 * subscription that had since been cancelled. Reading the subscription itself
 * makes every event idempotent and order-independent: whichever arrives last,
 * the stored status is Stripe's current one.
 */
async function syncSubscription(subscriptionId: string, userSubHint: string | null) {
  const subscription = await stripeGet<StripeObject>(
    `subscriptions/${encodeURIComponent(subscriptionId)}`);
  const fields = projectStripeSubscription(subscription);
  const userSub = userSubHint
    ?? fields.userSub
    ?? await userSubForStripeSubscription(fields.subscriptionId)
    ?? await userSubForCustomer(fields.customerId);
  if (!userSub) {
    console.warn(`Stripe subscription ${subscriptionId} has no WrTrueMeta account attached`);
    return;
  }
  const previous = await getSubscription(userSub);
  await saveSubscription(makeSubscriptionRecord({
    userSub,
    customerId: fields.customerId,
    subscriptionId: fields.subscriptionId,
    priceId: fields.priceId,
    status: fields.status,
    currentPeriodEnd: fields.currentPeriodEnd,
    cancelAtPeriodEnd: fields.cancelAtPeriodEnd,
    previous,
  }));
}

/**
 * A paid credit-pack checkout: add the pack to the buyer's balance, once.
 *
 * Returns true when the event was a credits checkout (handled, whatever the
 * outcome), so the subscription path never sees it. Only a session Stripe
 * reports as PAID grants anything; a delayed bank payment completes unpaid
 * and is granted later by checkout.session.async_payment_succeeded. The
 * pack size comes from the code's own pack list by id, falling back to the
 * session metadata only for a pack that has since been retired.
 */
async function handleCredits(type: string, object: StripeObject): Promise<boolean> {
  const metadata = (object.metadata ?? {}) as StripeObject;
  if (object.mode !== "payment" || metadata.kind !== "credits") return false;
  if (type !== "checkout.session.completed" && type !== "checkout.session.async_payment_succeeded") return true;
  if (object.payment_status !== "paid") return true;
  const sessionId = typeof object.id === "string" ? object.id : "";
  const userSub = typeof metadata.user_sub === "string" ? metadata.user_sub
    : typeof object.client_reference_id === "string" ? object.client_reference_id : "";
  const known = CREDIT_PACKS.find((p) => p.id === metadata.pack)?.credits;
  const credits = known ?? Number(metadata.credits);
  if (!sessionId || !userSub || !Number.isInteger(credits) || credits <= 0) {
    console.warn(`Credits checkout ${sessionId || "(no id)"} is missing its account or pack`);
    return true;
  }
  const balance = await grantCredits(userSub, credits, sessionId);
  if (balance != null) console.log(`Credited ${credits} generations to ${userSub} (balance ${balance})`);
  return true;
}

/** Which subscription an event is about, and whose account it belongs to. */
function eventTarget(type: string, object: StripeObject): { subscriptionId: string | null; userSub: string | null } {
  const metadata = object.metadata as StripeObject | undefined;
  const metaUser = typeof metadata?.user_sub === "string" ? metadata.user_sub : null;
  if (type === "checkout.session.completed" || type === "checkout.session.async_payment_succeeded"
      || type === "checkout.session.async_payment_failed") {
    const reference = typeof object.client_reference_id === "string" ? object.client_reference_id : null;
    return { subscriptionId: stripeId(object.subscription), userSub: metaUser ?? reference };
  }
  if (type.startsWith("customer.subscription.")) {
    return { subscriptionId: stripeId(object.id), userSub: metaUser };
  }
  if (type === "invoice.paid" || type === "invoice.payment_failed") {
    return { subscriptionId: invoiceSubscriptionId(object), userSub: null };
  }
  return { subscriptionId: null, userSub: null };
}

export async function POST(request: Request) {
  if (!webhookConfigured() || !stripeKeyConfigured()) {
    return NextResponse.json({ error: "Webhook is not configured." }, { status: 503 });
  }
  const rawBody = await request.text();
  if (!verifyStripeWebhook(rawBody, request.headers.get("stripe-signature"))) {
    return NextResponse.json({ error: "Invalid Stripe signature." }, { status: 400 });
  }

  let event: { type?: string; data?: { object?: StripeObject } };
  try { event = JSON.parse(rawBody) as typeof event; }
  catch { return NextResponse.json({ error: "Invalid webhook JSON." }, { status: 400 }); }
  const object = event.data?.object;
  if (!object || !event.type) return NextResponse.json({ received: true });

  try {
    if (await handleCredits(event.type, object)) return NextResponse.json({ received: true });
  } catch (error) {
    console.error("Stripe credits grant failed", error);
    return NextResponse.json({ error: "Credits grant failed." }, { status: 500 });
  }

  const { subscriptionId, userSub } = eventTarget(event.type, object);
  if (!subscriptionId) return NextResponse.json({ received: true });
  try {
    await syncSubscription(subscriptionId, userSub);
  } catch (error) {
    // A 500 makes Stripe retry the event, which is what we want for a
    // transient Stripe or KV failure.
    console.error("Stripe webhook sync failed", error);
    return NextResponse.json({ error: "Webhook sync failed." }, { status: 500 });
  }
  return NextResponse.json({ received: true });
}
