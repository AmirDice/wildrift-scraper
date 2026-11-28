import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getChampion } from "@/lib/data";
import { getMatchups, hasCounterPage } from "@/lib/counters";
import { CURRENT_PATCH } from "@/lib/patch";
import { Container, ChampionAvatar } from "@/components/ui";
import type { Faq } from "@/lib/champion-seo";
import { champName, fmtPct, hasLocale, languageAlternates, type Locale } from "@/lib/i18n";
import { dict } from "@/lib/i18n-dict";
import { FaqSection } from "@/components/champion-seo-parts";
import { LanguageSwitcher } from "@/components/i18n-parts";

/** Translated counters page; same data and gating as app/champions/[slug]/counters. */
export const revalidate = 86400;
export function generateStaticParams() {
  return [];
}

type Props = PageProps<"/[lang]/champions/[slug]/counters">;

export async function generateMetadata(props: Props): Promise<Metadata> {
  const { lang, slug } = await props.params;
  const champion = getChampion(slug);
  if (!hasLocale(lang) || !champion || !hasCounterPage(slug)) return { title: "Not found" };
  const t = dict(lang);
  const name = champName(champion.name, lang);
  const title = { absolute: t.countersTitle(name, CURRENT_PATCH ?? "") };
  const description = t.countersDescription(name);
  return {
    title, description,
    alternates: { canonical: `/${lang}/champions/${slug}/counters`, languages: languageAlternates(`/champions/${slug}/counters`) },
    openGraph: { title: title.absolute, description, url: `https://wrtruemeta.com/${lang}/champions/${slug}/counters` },
  };
}

export default async function LocalizedCountersPage(props: Props) {
  const { lang: rawLang, slug } = await props.params;
  if (!hasLocale(rawLang)) notFound();
  const lang: Locale = rawLang;
  const champion = getChampion(slug);
  if (!champion || !hasCounterPage(slug)) notFound();
  const t = dict(lang);
  const name = champName(champion.name, lang);
  const { strong, weak } = getMatchups(slug);
  const faq: Faq = weak.length ? [{
    q: t.faqCounterHowQ(name),
    a: t.faqCounterHowA(weak.slice(0, 3).map((m) => `${champName(m.champion.name, lang)} (${fmtPct(lang, m.winRate)})`).join(", ")),
  }] : [];

  const grid = (rows: typeof weak, tone: string) => (
    <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
      {rows.map((m) => (
        <Link key={m.champion.slug} href={`/${lang}/champions/${m.champion.slug}`} className="glass glass-hover flex items-center gap-3 rounded-xl p-3">
          <ChampionAvatar champion={m.champion} size={40} showBadges={false} />
          <span className="min-w-0 flex-1 truncate text-sm font-medium">{champName(m.champion.name, lang)}</span>
          <span className={`text-sm font-semibold tabular-nums ${tone}`}>{fmtPct(lang, m.winRate)}</span>
        </Link>
      ))}
    </div>
  );
  return (
    <Container className="py-10 sm:py-14">
      <LanguageSwitcher path={`/champions/${slug}/counters`} current={lang} label={t.language} />
      <nav className="mt-4 text-sm text-faint"><Link href={`/${lang}/champions/${slug}`} className="hover:text-text">&larr; {t.back(name)}</Link></nav>
      <div className="mt-4 flex items-center gap-4">
        <ChampionAvatar champion={champion} size={64} showBadges={false} />
        <div>
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">{t.countersH1(name)}</h1>
          <p className="mt-1 text-sm text-muted">Wild Rift · {t.patch(CURRENT_PATCH ?? "")} · {t.sourceChina}</p>
        </div>
      </div>
      {weak.length > 0 && (
        <section className="mt-8">
          <h2 className="text-xl font-semibold">{t.bestCounters(name)}</h2>
          <p className="mt-1 text-sm text-muted">{t.bestCountersDesc(name)}</p>
          {grid(weak, "text-rose-300")}
        </section>
      )}
      {strong.length > 0 && (
        <section className="mt-10">
          <h2 className="text-xl font-semibold">{t.beats(name)}</h2>
          {grid(strong, "text-emerald-300")}
        </section>
      )}
      <FaqSection faq={faq} title={t.questions(name)} />
      <p className="mt-10 text-sm"><Link href={`/champions/${slug}/counters`} className="text-accent hover:underline">{t.englishPage}</Link></p>
    </Container>
  );
}
