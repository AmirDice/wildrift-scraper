import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getChampions } from "@/lib/data";
import { CURRENT_PATCH } from "@/lib/patch";
import { Container, Card, ChampionAvatar, TierChip } from "@/components/ui";
import { HREFLANG, champName, fmtPct, hasLocale, languageAlternates, type Locale } from "@/lib/i18n";
import { dict } from "@/lib/i18n-dict";
import { LanguageSwitcher } from "@/components/i18n-parts";

/** Translated home: what the site is, the strongest champions, every champion. */
export const revalidate = 86400;

type Props = PageProps<"/[lang]">;

export async function generateMetadata(props: Props): Promise<Metadata> {
  const { lang } = await props.params;
  if (!hasLocale(lang)) return { title: "Not found" };
  const t = dict(lang);
  return {
    title: { absolute: t.homeTitle }, description: t.homeDescription,
    alternates: { canonical: `/${lang}`, languages: languageAlternates("/") },
    openGraph: { title: t.homeTitle, description: t.homeDescription, url: `https://wrtruemeta.com/${lang}`, locale: HREFLANG[lang] },
  };
}

export default async function LocalizedHome(props: Props) {
  const { lang: rawLang } = await props.params;
  if (!hasLocale(rawLang)) notFound();
  const lang: Locale = rawLang;
  const t = dict(lang);
  const champions = getChampions().filter((c) => !c.statsPending);
  const top = [...champions].sort((a, b) => b.wr - a.wr).slice(0, 12);
  const all = [...champions].sort((a, b) => champName(a.name, lang).localeCompare(champName(b.name, lang), HREFLANG[lang]));
  return (
    <Container className="py-10 sm:py-14">
      <LanguageSwitcher path="/" current={lang} label={t.language} />
      <h1 className="mt-5 text-3xl font-bold tracking-tight sm:text-5xl">{t.homeH1}</h1>
      <p className="mt-3 max-w-2xl text-lg text-muted">{t.homeIntro}</p>
      <p className="mt-1 text-sm text-faint">Wild Rift · {t.patch(CURRENT_PATCH ?? "")}</p>

      <section className="mt-10">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-xl font-semibold">{t.topChampions}</h2>
          <Link href={`/${lang}/tier-list`} className="text-sm font-semibold text-accent">{t.fullTierList} &rarr;</Link>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {top.map((c) => (
            <Link key={c.slug} href={`/${lang}/champions/${c.slug}`} className="glass glass-hover flex flex-col items-center gap-2 rounded-xl p-3 text-center">
              <ChampionAvatar champion={c} size={52} showBadges={false} />
              <span className="w-full truncate text-sm font-medium">{champName(c.name, lang)}</span>
              <span className="flex items-center gap-1.5"><TierChip tier={c.tier} /><span className="text-xs font-semibold text-accent">{fmtPct(lang, c.wr)}</span></span>
            </Link>
          ))}
        </div>
      </section>

      <Card className="mt-10 p-5 sm:p-6">
        <h2 className="text-lg font-semibold">{t.allChampions}</h2>
        <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 text-sm">
          {all.map((c) => <li key={c.slug}><Link href={`/${lang}/champions/${c.slug}`} className="text-muted hover:text-accent">{champName(c.name, lang)}</Link></li>)}
        </ul>
      </Card>
    </Container>
  );
}
