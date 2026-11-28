import { NextResponse, type NextRequest } from "next/server";
import { LANG_COOKIE, isSiteLanguage, parseAcceptLanguage, resolveLanguage } from "@/lib/preferred-language";

/**
 * Language auto-detection (2026-11-28, owner request).
 *
 * A visitor landing on an English page that exists in their language is sent
 * to that version: home, tier list and champion pages. The language is their
 * saved choice (`wtm_lang` cookie), else their browser's language list, else
 * the country Vercel sees them in (lib/preferred-language.ts).
 *
 * Rules that keep this from hurting anyone:
 *  - Crawlers are never redirected. Google crawls without a language and must
 *    see every version at its own URL; hreflang tells it which is which.
 *  - An explicit choice wins forever: the language switcher links carry
 *    ?setlang=<code>, which saves the cookie here and strips the parameter.
 *    Choosing English stops the redirects.
 *  - Only pages that always exist in every language are matched, so a
 *    redirect can never land on a 404. Lane, runes and counters pages are
 *    reached through links from the translated champion page.
 *  - 307 (temporary): the English URL stays the canonical English page.
 */
const BOT = /bot|crawl|spider|slurp|bingpreview|facebookexternalhit|embedly|quora link|whatsapp|telegram|discord|lighthouse|headless|preview/i;

export function proxy(request: NextRequest) {
  const url = request.nextUrl;
  const setlang = url.searchParams.get("setlang");
  if (setlang !== null) {
    url.searchParams.delete("setlang");
    const res = NextResponse.redirect(url, 307);
    if (isSiteLanguage(setlang)) {
      res.cookies.set(LANG_COOKIE, setlang, { path: "/", maxAge: 60 * 60 * 24 * 365, sameSite: "lax" });
    }
    return res;
  }
  if (request.method !== "GET") return NextResponse.next();
  if (BOT.test(request.headers.get("user-agent") ?? "")) return NextResponse.next();

  const lang = resolveLanguage({
    cookie: request.cookies.get(LANG_COOKIE)?.value ?? null,
    languages: parseAcceptLanguage(request.headers.get("accept-language")),
    country: request.headers.get("x-vercel-ip-country"),
  });
  if (lang === "en") return NextResponse.next();
  const target = url.clone();
  target.pathname = url.pathname === "/" ? `/${lang}` : `/${lang}${url.pathname}`;
  return NextResponse.redirect(target, 307);
}

export const config = {
  // Only English pages that exist in every language. /champions/<slug> but
  // not deeper: a champion's lane/runes/counters pages exist only where they
  // have data.
  matcher: [
    "/", "/tier-list", "/champions", "/champions/:slug",
    // A language choice (?setlang=) is honoured on any page.
    { source: "/:path*", has: [{ type: "query", key: "setlang" }] },
  ],
};
