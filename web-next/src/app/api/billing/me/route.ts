import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { AUTH_CONFIGURED, SESSION_COOKIE, readSession } from "@/lib/session";
import { getSubscription, plusPrices, PLUS_PLAN, subscriptionSummary } from "@/lib/subscription";
import { stripeConfigured } from "@/lib/stripe";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const store = await cookies();
  const user = readSession(store.get(SESSION_COOKIE)?.value);
  const record = user ? await getSubscription(user.sub) : null;
  return NextResponse.json(
    {
      authConfigured: AUTH_CONFIGURED,
      billingConfigured: stripeConfigured(),
      plan: PLUS_PLAN,
      prices: await plusPrices(),
      subscription: subscriptionSummary(record),
    },
    { headers: { "Cache-Control": "private, no-store, max-age=0" } },
  );
}
