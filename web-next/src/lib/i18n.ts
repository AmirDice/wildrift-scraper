/**
 * Translated SEO pages (2026-11-28): /<lang>/ versions of the home page, tier
 * list, champion, lane, runes and counters pages, for Chinese, Turkish,
 * French, Polish, Korean and Spanish. English stays at the root URLs.
 *
 * Why only these pages: they are the ones people search for, and a whole-site
 * translation means moving every route under app/[lang] and every component's
 * copy into dictionaries. The nav and footer stay English for now.
 *
 * Names: champions, items, runes and spells come from Riot's Data Dragon in
 * each language (scripts/build_i18n_names.py); Chinese champion names from the
 * official Wild Rift China feed. Anything Wild Rift-only falls back to English.
 * All interface copy is hand-written in src/lib/i18n-dict.ts -- no runtime
 * translation, so a page costs nothing to serve.
 */
import names from "@/data/i18n_names.json";

export const LOCALES = ["zh", "vi", "tr", "fr", "pl", "ko", "es"] as const;
export type Locale = (typeof LOCALES)[number];

export const hasLocale = (value: string): value is Locale => (LOCALES as readonly string[]).includes(value);

/** BCP 47 codes for hreflang and the lang attribute. */
export const HREFLANG: Record<Locale, string> = {
  zh: "zh-Hans", vi: "vi", tr: "tr", fr: "fr", pl: "pl", ko: "ko", es: "es",
};

export const NATIVE_NAME: Record<Locale | "en", string> = {
  en: "English", zh: "简体中文", vi: "Tiếng Việt", tr: "Türkçe", fr: "Français", pl: "Polski", ko: "한국어", es: "Español",
};

type NameTable = Record<string, Partial<Record<Locale, string>>>;
const N = names as unknown as { champions: NameTable; items: NameTable; runes: NameTable; spells: NameTable };

export function champName(name: string, lang: Locale): string {
  return N.champions[name]?.[lang] ?? name;
}
export function itemName(name: string, lang: Locale): string {
  return N.items[name]?.[lang] ?? name;
}
export function runeName(name: string, lang: Locale): string {
  return N.runes[name]?.[lang] ?? name;
}
export function spellName(name: string, lang: Locale): string {
  return N.spells[name]?.[lang] ?? name;
}
/** Any entity: tries champion, item, rune, then spell names. */
export function entityName(name: string, lang: Locale): string {
  return N.champions[name]?.[lang] ?? N.items[name]?.[lang] ?? N.runes[name]?.[lang] ?? N.spells[name]?.[lang] ?? name;
}

/**
 * hreflang alternates for a path that exists in every language.
 * `path` is the English path ("/champions/ahri"); "/" for the home page.
 */
export function languageAlternates(path: string): Record<string, string> {
  const clean = path === "/" ? "" : path;
  const out: Record<string, string> = { en: path, "x-default": path };
  for (const l of LOCALES) out[HREFLANG[l]] = `/${l}${clean}`;
  return out;
}

export function localizedPath(lang: Locale | "en", path: string): string {
  if (lang === "en") return path;
  return `/${lang}${path === "/" ? "" : path}`;
}

/** A percentage written the way each language writes it. */
export function fmtPct(lang: Locale, n: number): string {
  const v = n.toFixed(1);
  switch (lang) {
    case "tr": return `%${v.replace(".", ",")}`;
    case "fr": return `${v.replace(".", ",")} %`;
    case "vi":
    case "pl":
    case "es": return `${v.replace(".", ",")}%`;
    default: return `${v}%`;
  }
}
