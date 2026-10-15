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
import { stripeConfigured, stripeGet, verifyStripeWebhook, webhookConfigured } from "@/lib/stripe";

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
  if (!webhookConfigured() || !stripeConfigured()) {
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
