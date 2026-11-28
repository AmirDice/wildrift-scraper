import { NextResponse, type NextRequest } from "next/server";
import { LANG_COOKIE, isSiteLanguage, parseAcceptLanguage, resolveLanguage } from "@/lib/preferred-language";

/**
 * Languages for the shared page tree (app/[lang]).
 *
 * 1. English lives at the unprefixed URLs: /, /tier-list, /champions,
 *    /champions/<slug>[/<sub>] are REWRITTEN to /en/... so app/[lang]
 *    renders them. /en/... itself redirects to the unprefixed URL, so there
 *    is exactly one English URL per page.
 * 2. Language auto-detection (owner request): a visitor on an English page is
 *    sent to their language -- saved choice (`wtm_lang`), else browser
 *    languages, else Vercel's country (lib/preferred-language.ts).
 *    - Crawlers are never redirected; hreflang tells them which is which.
 *    - ?setlang=<code> saves an explicit choice; choosing English stops it.
 *    - 307, so the English URL stays the canonical English page.
 */
const BOT = /bot|crawl|spider|slurp|bingpreview|facebookexternalhit|embedly|quora link|whatsapp|telegram|discord|lighthouse|headless|preview/i;

/** English paths served from app/[lang] (the shared tree). */
function isTreePath(path: string): boolean {
  return path === "/" || path === "/tier-list" || path === "/champions" || /^\/champions\/[^/]+(\/[^/]+)?$/.test(path);
}

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

  const path = url.pathname;
  // One English URL per page: /en/... -> /...
  if (path === "/en" || path.startsWith("/en/")) {
    const target = url.clone();
    target.pathname = path === "/en" ? "/" : path.slice(3);
    return NextResponse.redirect(target, 308);
  }
  if (!isTreePath(path)) return NextResponse.next();

  const rewriteToEnglish = () => {
    const target = url.clone();
    target.pathname = path === "/" ? "/en" : `/en${path}`;
    return NextResponse.rewrite(target);
  };
  if (request.method !== "GET" || BOT.test(request.headers.get("user-agent") ?? "")) return rewriteToEnglish();

  const lang = resolveLanguage({
    cookie: request.cookies.get(LANG_COOKIE)?.value ?? null,
    languages: parseAcceptLanguage(request.headers.get("accept-language")),
    country: request.headers.get("x-vercel-ip-country"),
  });
  if (lang === "en") return rewriteToEnglish();
  const target = url.clone();
  target.pathname = path === "/" ? `/${lang}` : `/${lang}${path}`;
  return NextResponse.redirect(target, 307);
}

export const config = {
  matcher: [
    "/", "/tier-list", "/champions", "/champions/:slug", "/champions/:slug/:sub",
    "/en", "/en/:path*",
    // A language choice (?setlang=) is honoured on any page.
    { source: "/:path*", has: [{ type: "query", key: "setlang" }] },
  ],
};
