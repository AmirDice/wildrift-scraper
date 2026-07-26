import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import {
  AUTH_CONFIGURED,
  SESSION_COOKIE,
  SESSION_MAX_AGE,
  signSession,
  verifyGoogleIdToken,
} from "@/lib/session";
import { trackEvent } from "@/lib/stats";
import { ACCESS_COOKIE, countSignIn, readAccessCookie } from "@/lib/access";

/**
 * POST { credential } -- the ID token from Google Identity Services.
 * Verifies it against Google's JWKS and exchanges it for our own session
 * cookie. The Google token itself is never stored.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  if (!AUTH_CONFIGURED) {
    return NextResponse.json({ error: "sign-in is not configured" }, { status: 503 });
  }

  let credential: unknown;
  try {
    ({ credential } = (await request.json()) as { credential?: unknown });
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }
  if (typeof credential !== "string" || credential.length < 20) {
    return NextResponse.json({ error: "missing credential" }, { status: 400 });
  }

  const profile = await verifyGoogleIdToken(credential);
  if (!profile) {
    return NextResponse.json({ error: "could not verify that Google sign-in" }, { status: 401 });
  }

  const store = await cookies();
  store.set(SESSION_COOKIE, signSession(profile), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: SESSION_MAX_AGE,
  });

  void trackEvent("signed_in");

  // Attribute the sign-in to whatever invite or referral link brought them.
  // Clicks measure reach and activations measure arrival, but a sponsor is
  // paying for people who actually signed up, and that is this number.
  const grant = readAccessCookie(store.get(ACCESS_COOKIE)?.value);
  if (grant) void countSignIn(grant.code);

  return NextResponse.json({
    user: { name: profile.name, email: profile.email, picture: profile.picture },
    referredBy: grant ? grant.code : null,
  });
}
