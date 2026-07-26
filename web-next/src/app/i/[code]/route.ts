import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import {
  ACCESS_COOKIE,
  ACCESS_MAX_AGE,
  countActivation,
  countClick,
  getCode,
  grantFrom,
  redeemable,
  signAccessCookie,
} from "@/lib/access";

/**
 * GET /i/CODE -- the invite and referral link.
 *
 * Short path on purpose: this gets pasted into Discord, video descriptions and
 * DMs. It records the visit, drops the signed grant cookie, and forwards to
 * wherever the code is actually for -- a beta invite lands on the build tools,
 * a plain referral lands on the home page.
 *
 * A dead or exhausted code still redirects rather than showing an error page:
 * someone arriving from a creator's video should land on the site either way,
 * just without the grant.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request, context: RouteContext<"/i/[code]">) {
  const { code } = await context.params;
  const normalized = code.toUpperCase().slice(0, 24);
  const origin = new URL(request.url).origin;

  const record = await getCode(normalized);
  // Count the click even when the code is dead: a creator's traffic is still
  // their traffic, and a link that stopped working is worth being able to see.
  if (record) void countClick(record.code);

  const check = await redeemable(record);
  if (!record || !check.ok) {
    return NextResponse.redirect(new URL("/?invite=invalid", origin), { status: 307 });
  }

  const store = await cookies();
  store.set(ACCESS_COOKIE, signAccessCookie(grantFrom(record)), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: ACCESS_MAX_AGE,
  });
  void countActivation(record.code);

  const destination = record.grantsBeta ? "/build" : "/";
  return NextResponse.redirect(new URL(`${destination}?invite=${record.code}`, origin), { status: 307 });
}
