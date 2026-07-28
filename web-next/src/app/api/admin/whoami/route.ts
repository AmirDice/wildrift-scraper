import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import {
  SESSION_COOKIE, readSession, isAdmin, adminEmails, adminEmailsConfigured,
} from "@/lib/session";

/**
 * Why the signed-in account is, or is not, exempt from the generation cap.
 *
 * `unlimited: false` looks identical whether the email mismatched, ADMIN_EMAILS
 * is empty, the variable never reached this deployment, or nobody is signed in
 * at all. That ambiguity cost a real debugging session: everything was
 * configured correctly-looking -- right project, deployed after the variable was
 * added, session carrying the email -- and there was still no way to see which
 * of them was actually false.
 *
 * Guarded by ADMIN_TOKEN rather than by ADMIN_EMAILS, which is the whole point:
 * a diagnostic gated on the thing being diagnosed can never explain a failure.
 *
 * It reports the configured addresses in full. That is a deliberate call: the
 * token holder is the owner, a typo is invisible under masking (in***ir and
 * in***mir read the same), and anyone with this token can already mint access
 * codes -- an email address is not the sensitive thing on this endpoint.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function authorised(request: Request): boolean {
  const expected = process.env.ADMIN_TOKEN ?? "";
  if (!expected) return false;
  const provided = new URL(request.url).searchParams.get("token")
    ?? request.headers.get("x-admin-token")
    ?? "";
  return provided === expected;
}

export async function GET(request: Request) {
  if (!authorised(request)) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }

  // Read from session.ts, not from process.env: this must report the list the
  // gate is actually comparing against.
  const isSet = adminEmailsConfigured();
  const configured = adminEmails();
  const store = await cookies();
  const user = readSession(store.get(SESSION_COOKIE)?.value);
  const sessionEmail = user?.email?.trim().toLowerCase() ?? null;
  const matched = isAdmin(user);

  // The specific reason, rather than leaving the caller to infer it.
  const reason = !isSet
    ? "ADMIN_EMAILS is not set on this deployment. Add it to the SITE project "
      + "(wildrift-scraper, not wrtruemeta-advisor) and redeploy -- Vercel applies "
      + "environment variables at deploy time."
    : configured.length === 0
      ? "ADMIN_EMAILS is set but parses to no addresses. Check for stray quotes: "
        + "the value should be bare, like a@x.com,b@y.com."
      : !user
        ? "Nobody is signed in on this browser, so there is no email to match."
        : !sessionEmail
          ? "The session carries no email. Sign out and in again to refresh it."
          : matched
            ? "Matched: this account is exempt from the daily cap."
            : `Signed in as ${sessionEmail}, which is not in ADMIN_EMAILS. Compare it `
              + "character for character with the configured list below -- a different "
              + "Google account and a typo look identical from the outside.";

  return NextResponse.json(
    {
      matched,
      reason,
      sessionEmail,
      signedIn: Boolean(user),
      configured,
      // Set but empty after parsing means quoting or separator trouble, which
      // the count alone would not distinguish from "not set".
      adminEmailsSet: isSet,
    },
    { headers: { "Cache-Control": "private, no-store, max-age=0" } },
  );
}
