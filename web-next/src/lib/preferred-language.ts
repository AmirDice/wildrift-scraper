/**
 * The visitor's language, shared by the proxy (server) and Build Studio
 * (client). Order: an explicit choice saved in the `wtm_lang` cookie, then
 * the browser's language list, then the country Vercel sees the visitor in.
 * English when nothing matches.
 *
 * Browser language comes before country on purpose: an English-speaking
 * visitor in France wants English, and the browser setting says so; the
 * country only decides for a visitor whose browser names no language we have.
 */
export const SUPPORTED = ["en", "zh", "vi", "tr", "fr", "pl", "ko", "es"] as const;
export type SiteLanguage = (typeof SUPPORTED)[number];
export const LANG_COOKIE = "wtm_lang";
/** Native names, kept here (not lib/i18n.ts) so client bundles do not pull in
 *  the localized-names table. */
export const LANGUAGE_LABEL: Record<SiteLanguage, string> = {
  en: "English", zh: "简体中文", vi: "Tiếng Việt", tr: "Türkçe", fr: "Français", pl: "Polski", ko: "한국어", es: "Español",
};

const COUNTRY_LANGUAGE: Record<string, SiteLanguage> = {
  CN: "zh", SG: "zh",  // not TW/HK/MO: they read Traditional; ours is Simplified
  KR: "ko",
  VN: "vi",
  TR: "tr",
  FR: "fr", BE: "fr", LU: "fr", MC: "fr",
  PL: "pl",
  ES: "es", MX: "es", AR: "es", CO: "es", CL: "es", PE: "es", VE: "es", EC: "es",
  GT: "es", CU: "es", BO: "es", DO: "es", HN: "es", PY: "es", SV: "es", NI: "es",
  CR: "es", PA: "es", UY: "es",
};

export const isSiteLanguage = (v: unknown): v is SiteLanguage =>
  typeof v === "string" && (SUPPORTED as readonly string[]).includes(v);

/** First supported language in an Accept-Language header or navigator list. */
export function fromLanguageList(list: readonly string[]): SiteLanguage | null {
  for (const raw of list) {
    const base = raw.trim().toLowerCase().split(/[-_;]/)[0];
    if (isSiteLanguage(base)) return base;
  }
  return null;
}

export function parseAcceptLanguage(header: string | null): string[] {
  if (!header) return [];
  return header
    .split(",")
    .map((part) => {
      const [tag, q] = part.trim().split(";q=");
      return { tag, q: q ? Number(q) : 1 };
    })
    .filter((x) => x.tag && x.q > 0)
    .sort((a, b) => b.q - a.q)
    .map((x) => x.tag);
}

export function resolveLanguage(opts: { cookie?: string | null; languages?: readonly string[]; country?: string | null }): SiteLanguage {
  if (isSiteLanguage(opts.cookie)) return opts.cookie;
  const fromList = fromLanguageList(opts.languages ?? []);
  if (fromList) return fromList;
  if (opts.languages && opts.languages.length > 0) {
    // The browser named languages and none is ours: English, not the country.
    return "en";
  }
  return (opts.country && COUNTRY_LANGUAGE[opts.country.toUpperCase()]) || "en";
}

/** Client side: the language Build Studio should ask for. */
export function clientLanguage(): SiteLanguage {
  if (typeof document === "undefined") return "en";
  const cookie = document.cookie.split("; ").find((c) => c.startsWith(`${LANG_COOKIE}=`))?.split("=")[1] ?? null;
  return resolveLanguage({ cookie, languages: typeof navigator !== "undefined" ? navigator.languages : [] });
}

export function saveLanguage(lang: SiteLanguage) {
  if (typeof document === "undefined") return;
  document.cookie = `${LANG_COOKIE}=${lang}; path=/; max-age=${60 * 60 * 24 * 365}; samesite=lax`;
}
