import { notFound } from "next/navigation";
import { HREFLANG, LOCALES, hasLocale } from "@/lib/i18n";

/**
 * Translated pages live under /<lang>/ (lib/i18n.ts). Only the six locales
 * are valid; any other first path segment that reaches this layout is a 404.
 *
 * The root layout's <html lang="en"> cannot change per route without moving
 * every page under this segment, so the content carries its own lang here.
 * Search engines read hreflang and the text itself; this keeps screen readers
 * and translation prompts correct.
 */
export function generateStaticParams() {
  return LOCALES.map((lang) => ({ lang }));
}

export default async function LangLayout(props: LayoutProps<"/[lang]">) {
  const { lang } = await props.params;
  if (!hasLocale(lang)) notFound();
  return <div lang={HREFLANG[lang]}>{props.children}</div>;
}
