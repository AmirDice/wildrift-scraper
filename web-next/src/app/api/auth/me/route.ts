import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { AUTH_CONFIGURED, SESSION_COOKIE, readSession } from "@/lib/session";
import { clientIp, peekQuota } from "@/lib/quota";
import { ACCESS_COOKIE, readAccessCookie } from "@/lib/access";

/**
 * GET -- who is signed in, and how many build generations are left today.
 * The build tools poll this once on mount so they can show the remaining
 * count and the "sign in for 10 more" prompt without a generation attempt.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const store = await cookies();
  const user = readSession(store.get(SESSION_COOKIE)?.value);
  const access = readAccessCookie(store.get(ACCESS_COOKIE)?.value);
  const quota = await peekQuota(user, clientIp(request), access?.unlimited ?? false);

  return NextResponse.json(
    {
      authConfigured: AUTH_CONFIGURED,
      user: user ? { name: user.name, email: user.email, picture: user.picture } : null,
      quota,
      // Drives early access to the gated build tools in client components,
      // which cannot read the cookie themselves.
      access: access
        ? { code: access.code, label: access.label, beta: access.beta, unlimited: access.unlimited }
        : null,
    },
    {
      // Never cacheable, and said out loud rather than relied on: this response
      // identifies a person. A shared cache holding it would serve one player's
      // name and remaining quota to the next visitor.
      headers: { "Cache-Control": "private, no-store, max-age=0" },
    },
  );
}
