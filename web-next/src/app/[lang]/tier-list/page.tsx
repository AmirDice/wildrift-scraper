import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { TIER_ORDER, getChampions } from "@/lib/data";
import { CURRENT_PATCH } from "@/lib/patch";
import { Container, ChampionAvatar, TierChip } from "@/components/ui";
import { HREFLANG, champName, fmtPct, hasLocale, languageAlternates, type Locale } from "@/lib/i18n";
import { dict } from "@/lib/i18n-dict";
import { LanguageSwitcher } from "@/components/i18n-parts";

/** Translated tier list: every champion grouped by tier, from the EU/NA boards. */
export const revalidate = 86400;

type Props = PageProps<"/[lang]/tier-list">;

export async function generateMetadata(props: Props): Promise<Metadata> {
  const { lang } = await props.params;
  if (!hasLocale(lang)) return { title: "Not found" };
  const t = dict(lang);
  const title = { absolute: t.tierTitle(CURRENT_PATCH ?? "") };
  return {
    title, description: t.tierDescription,
    alternates: { canonical: `/${lang}/tier-list`, languages: languageAlternates("/tier-list") },
    openGraph: { title: title.absolute, description: t.tierDescription, url: `https://wrtruemeta.com/${lang}/tier-list`, locale: HREFLANG[lang] },
  };
}

export default async function LocalizedTierList(props: Props) {
  const { lang: rawLang } = await props.params;
  if (!hasLocale(rawLang)) notFound();
  const lang: Locale = rawLang;
  const t = dict(lang);
  const champions = getChampions().filter((c) => !c.statsPending);
  const groups = TIER_ORDER.map((tier) => ({
    tier, rows: champions.filter((c) => c.tier === tier).sort((a, b) => b.wr - a.wr),
  })).filter((g) => g.rows.length > 0);
  return (
    <Container className="py-10 sm:py-14">
      <LanguageSwitcher path="/tier-list" current={lang} label={t.language} />
      <h1 className="mt-5 text-3xl font-bold tracking-tight sm:text-4xl">{t.tierH1}</h1>
      <p className="mt-2 max-w-2xl text-muted">{t.tierIntro}</p>
      <p className="mt-1 text-sm text-faint">Wild Rift · {t.patch(CURRENT_PATCH ?? "")} · {t.sourceLadder}</p>
      <div className="mt-8 space-y-6">
        {groups.map((g) => (
          <section key={g.tier}>
            <h2 className="flex items-center gap-2 text-lg font-semibold"><TierChip tier={g.tier} /> <span className="text-sm text-muted">{g.rows.length}</span></h2>
            <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6">
              {g.rows.map((c) => (
                <Link key={c.slug} href={`/${lang}/champions/${c.slug}`} className="glass glass-hover flex items-center gap-2 rounded-xl p-2.5">
                  <ChampionAvatar champion={c} size={36} showBadges={false} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{champName(c.name, lang)}</span>
                    <span className="text-xs tabular-nums text-accent">{fmtPct(lang, c.wr)}</span>
                  </span>
                </Link>
              ))}
            </div>
          </section>
        ))}
      </div>
    </Container>
  );
}
