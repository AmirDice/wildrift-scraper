import { notFound } from "next/navigation";
import { HREFLANG, LOCALES, isPageLang } from "@/lib/i18n";
import { uiTable } from "@/lib/ui-i18n";
import { I18nProvider } from "@/components/i18n-provider";

/**
 * One page tree for every language (2026-11-28). The home page, tier list,
 * champion index and champion/lane/runes/counters pages live under /[lang];
 * English is served at the unprefixed URLs by src/proxy.ts rewriting them to
 * /en/..., so every language renders the exact same components.
 *
 * The root layout's <html lang="en"> cannot change per route without moving
 * every page under this segment, so the content carries its own lang here.
 */
export function generateStaticParams() {
  return ["en", ...LOCALES].map((lang) => ({ lang }));
}

export default async function LangLayout(props: LayoutProps<"/[lang]">) {
  const { lang } = await props.params;
  if (!isPageLang(lang)) notFound();
  return (
    <div lang={lang === "en" ? "en" : HREFLANG[lang]}>
      <I18nProvider lang={lang} table={uiTable(lang)}>{props.children}</I18nProvider>
    </div>
  );
}
