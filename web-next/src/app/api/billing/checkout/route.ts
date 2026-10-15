import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { AUTH_CONFIGURED, SESSION_COOKIE, readSession } from "@/lib/session";
import { getSubscription, isProSubscription } from "@/lib/subscription";
import {
  SITE_URL,
  STRIPE_PLUS_MONTHLY_PRICE_ID,
  STRIPE_PLUS_YEARLY_PRICE_ID,
  stripeConfigured,
  stripeIntegrationIdentifier,
  stripeRequest,
} from "@/lib/stripe";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  if (!AUTH_CONFIGURED) return NextResponse.json({ error: "Sign-in is not configured." }, { status: 503 });
  if (!stripeConfigured()) return NextResponse.json({ error: "Subscriptions are not configured yet." }, { status: 503 });

  const store = await cookies();
  const user = readSession(store.get(SESSION_COOKIE)?.value);
  if (!user) return NextResponse.json({ error: "Sign in before starting a subscription." }, { status: 401 });

  const current = await getSubscription(user.sub);
  if (isProSubscription(current)) {
    return NextResponse.json({ error: "Your Plus subscription is already active." }, { status: 409 });
  }

  let interval: "monthly" | "yearly" = "monthly";
  try {
    const body = await request.json() as { interval?: unknown };
    if (body.interval === "yearly") interval = "yearly";
  } catch {
    // Empty POST bodies are valid and default to the monthly price.
  }
  const priceId = interval === "yearly"
    ? STRIPE_PLUS_YEARLY_PRICE_ID
    : STRIPE_PLUS_MONTHLY_PRICE_ID;
  if (!priceId) {
    return NextResponse.json({ error: `The ${interval} Plus price is not configured yet.` }, { status: 503 });
  }

  const params = new URLSearchParams();
  params.set("mode", "subscription");
  params.set("line_items[0][price]", priceId);
  params.set("line_items[0][quantity]", "1");
  params.set("integration_identifier", stripeIntegrationIdentifier(`plus_${interval}`));
  params.set("success_url", `${SITE_URL}/account?billing=success`);
  params.set("cancel_url", `${SITE_URL}/account?billing=cancelled`);
  params.set("client_reference_id", user.sub);
  params.set("metadata[user_sub]", user.sub);
  params.set("subscription_data[metadata][user_sub]", user.sub);
  if (current?.customerId) params.set("customer", current.customerId);
  else if (user.email) params.set("customer_email", user.email);

  try {
    const session = await stripeRequest<{ url?: string }>("checkout/sessions", params);
    if (!session.url) return NextResponse.json({ error: "Stripe did not return a checkout URL." }, { status: 502 });
    return NextResponse.json({ url: session.url });
  } catch (error) {
    console.error("Stripe checkout session failed", error);
    return NextResponse.json({ error: "Could not start checkout. Please try again." }, { status: 502 });
  }
}
