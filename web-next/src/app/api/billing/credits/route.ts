import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { AUTH_CONFIGURED, SESSION_COOKIE, readSession } from "@/lib/session";
import { creditsConfigured, getCredits, packById, packOffers } from "@/lib/credits";
import { getSubscription } from "@/lib/subscription";
import {
  SITE_URL,
  STRIPE_AUTOMATIC_TAX,
  stripeIntegrationIdentifier,
  stripeRequest,
} from "@/lib/stripe";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** GET: the packs on sale with Stripe's prices, and the caller's balance. */
export async function GET() {
  if (!creditsConfigured()) return NextResponse.json({ offers: [], credits: null });
  const store = await cookies();
  const user = readSession(store.get(SESSION_COOKIE)?.value);
  const [offers, credits] = await Promise.all([
    packOffers(),
    user ? getCredits(user.sub) : Promise.resolve(null),
  ]);
  return NextResponse.json({ offers, credits }, { headers: { "Cache-Control": "private, no-store" } });
}

/**
 * POST { pack, waiveWithdrawal }: a one-time Checkout session for one pack.
 *
 * Refused without the withdrawal waiver (see components/credit-packs.tsx):
 * credits are delivered on payment, and selling digital content for immediate
 * delivery without the buyer's prior express consent leaves the 14-day
 * withdrawal right open after they have used it. The consent time is kept on
 * the session and the payment as the record of it.
 */
export async function POST(request: Request) {
  if (!AUTH_CONFIGURED) return NextResponse.json({ error: "Sign-in is not configured." }, { status: 503 });
  if (!creditsConfigured()) return NextResponse.json({ error: "Credit packs are not on sale yet." }, { status: 503 });

  const store = await cookies();
  const user = readSession(store.get(SESSION_COOKIE)?.value);
  if (!user) return NextResponse.json({ error: "Sign in before buying credits." }, { status: 401 });

  let body: { pack?: unknown; waiveWithdrawal?: unknown } = {};
  try { body = await request.json() as typeof body; } catch { /* empty body is answered below */ }
  const pack = packById(body.pack);
  if (!pack) return NextResponse.json({ error: "Unknown credit pack." }, { status: 400 });
  if (body.waiveWithdrawal !== true) {
    return NextResponse.json(
      { error: "Please confirm that the credits are added straight away and that this ends your right of withdrawal." },
      { status: 400 },
    );
  }

  const consentAt = new Date().toISOString();
  const params = new URLSearchParams();
  params.set("mode", "payment");
  params.set("line_items[0][price]", pack.priceId);
  params.set("line_items[0][quantity]", "1");
  params.set("integration_identifier", stripeIntegrationIdentifier(`credits_${pack.id}`));
  params.set("success_url", `${SITE_URL}/account?credits=success`);
  params.set("cancel_url", `${SITE_URL}/account?credits=cancelled`);
  params.set("client_reference_id", user.sub);
  for (const [k, v] of Object.entries({
    kind: "credits", user_sub: user.sub, pack: pack.id, credits: String(pack.credits),
    withdrawal_waiver_at: consentAt,
  })) {
    params.set(`metadata[${k}]`, v);
    params.set(`payment_intent_data[metadata][${k}]`, v);
  }
  // A receipt for every purchase, which is also the confirmation of the
  // waiver on a durable medium the law asks for (the text below goes on it).
  params.set("invoice_creation[enabled]", "true");
  params.set("invoice_creation[invoice_data][footer]",
    "Digital content delivered immediately at the buyer's express request; the right of withdrawal expired on delivery.");
  params.set("custom_text[submit][message]",
    "Your credits are added as soon as payment succeeds. You agreed that this ends your right of withdrawal.");
  if (STRIPE_AUTOMATIC_TAX) params.set("automatic_tax[enabled]", "true");

  const existing = await getSubscription(user.sub);
  if (existing?.customerId) params.set("customer", existing.customerId);
  else {
    params.set("customer_creation", "always");
    if (user.email) params.set("customer_email", user.email);
  }

  try {
    const session = await stripeRequest<{ url?: string }>("checkout/sessions", params);
    if (!session.url) return NextResponse.json({ error: "Stripe did not return a checkout URL." }, { status: 502 });
    return NextResponse.json({ url: session.url });
  } catch (error) {
    console.error("Stripe credits checkout failed", error);
    return NextResponse.json({ error: "Could not start checkout. Please try again." }, { status: 502 });
  }
}
