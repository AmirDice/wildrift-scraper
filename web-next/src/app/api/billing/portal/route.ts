import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { AUTH_CONFIGURED, SESSION_COOKIE, readSession } from "@/lib/session";
import { getSubscription } from "@/lib/subscription";
import { SITE_URL, stripeConfigured, stripeRequest } from "@/lib/stripe";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST() {
  if (!AUTH_CONFIGURED) return NextResponse.json({ error: "Sign-in is not configured." }, { status: 503 });
  if (!stripeConfigured()) return NextResponse.json({ error: "Subscriptions are not configured yet." }, { status: 503 });
  const store = await cookies();
  const user = readSession(store.get(SESSION_COOKIE)?.value);
  if (!user) return NextResponse.json({ error: "Sign in before managing billing." }, { status: 401 });
  const current = await getSubscription(user.sub);
  if (!current?.customerId) return NextResponse.json({ error: "No Stripe customer was found for this account." }, { status: 404 });

  const params = new URLSearchParams({ customer: current.customerId, return_url: `${SITE_URL}/account` });
  try {
    const session = await stripeRequest<{ url?: string }>("billing_portal/sessions", params);
    if (!session.url) return NextResponse.json({ error: "Stripe did not return a portal URL." }, { status: 502 });
    return NextResponse.json({ url: session.url });
  } catch (error) {
    console.error("Stripe portal session failed", error);
    return NextResponse.json({ error: "Could not open billing management. Please try again." }, { status: 502 });
  }
}
