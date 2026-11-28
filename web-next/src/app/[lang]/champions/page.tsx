import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getChampions } from "@/lib/data";
import { Container, ChampionAvatar, TierChip } from "@/components/ui";
import { HREFLANG, champName, fmtPct, hasLocale, languageAlternates, type Locale } from "@/lib/i18n";
import { dict } from "@/lib/i18n-dict";
import { LanguageSwitcher } from "@/components/i18n-parts";

/** Translated champion index, the target of the nav's Champions link. */
export const revalidate = 86400;

type Props = PageProps<"/[lang]/champions">;

export async function generateMetadata(props: Props): Promise<Metadata> {
  const { lang } = await props.params;
  if (!hasLocale(lang)) return { title: "Not found" };
  const t = dict(lang);
  const title = `${t.allChampions} · Wild Rift`;
  return {
    title, description: t.homeDescription,
    alternates: { canonical: `/${lang}/champions`, languages: languageAlternates("/champions") },
  };
}

export default async function LocalizedChampions(props: Props) {
  const { lang: rawLang } = await props.params;
  if (!hasLocale(rawLang)) notFound();
  const lang: Locale = rawLang;
  const t = dict(lang);
  const all = getChampions().filter((c) => !c.statsPending)
    .sort((a, b) => champName(a.name, lang).localeCompare(champName(b.name, lang), HREFLANG[lang]));
  return (
    <Container className="py-10 sm:py-14">
      <LanguageSwitcher path="/champions" current={lang} label={t.language} />
      <h1 className="mt-5 text-3xl font-bold tracking-tight sm:text-4xl">{t.allChampions}</h1>
      <div className="mt-6 grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6">
        {all.map((c) => (
          <Link key={c.slug} href={`/${lang}/champions/${c.slug}`} className="glass glass-hover flex items-center gap-2 rounded-xl p-2.5">
            <ChampionAvatar champion={c} size={36} showBadges={false} />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium">{champName(c.name, lang)}</span>
              <span className="flex items-center gap-1"><TierChip tier={c.tier} /><span className="text-xs tabular-nums text-accent">{fmtPct(lang, c.wr)}</span></span>
            </span>
          </Link>
        ))}
      </div>
    </Container>
  );
}
