import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getChampion } from "@/lib/data";
import { CURRENT_PATCH } from "@/lib/patch";
import { Container, Card, ChampionAvatar } from "@/components/ui";
import { laneFor, lanePages, usableRows, type Faq, type Lane } from "@/lib/champion-seo";
import { champName, entityName, fmtPct, hasLocale, languageAlternates, type Locale } from "@/lib/i18n";
import { dict } from "@/lib/i18n-dict";
import { FaqSection } from "@/components/champion-seo-parts";
import { LanguageSwitcher, LocalizedRows } from "@/components/i18n-parts";

/** Translated lane page; same data and gating as app/champions/[slug]/[lane]. */
export const revalidate = 86400;
export function generateStaticParams() {
  return [];
}

type Props = PageProps<"/[lang]/champions/[slug]/[lane]">;

export async function generateMetadata(props: Props): Promise<Metadata> {
  const { lang, slug, lane } = await props.params;
  const champion = getChampion(slug);
  if (!hasLocale(lang) || !champion || !laneFor(slug, lane)) return { title: "Not found" };
  const t = dict(lang);
  const name = champName(champion.name, lang);
  const laneName = t.lanes[lane as Lane];
  const title = { absolute: t.laneTitle(name, laneName, CURRENT_PATCH ?? "") };
  const description = t.laneDescription(name, laneName);
  return {
    title, description,
    alternates: { canonical: `/${lang}/champions/${slug}/${lane}`, languages: languageAlternates(`/champions/${slug}/${lane}`) },
    openGraph: { title: title.absolute, description, url: `https://wrtruemeta.com/${lang}/champions/${slug}/${lane}` },
  };
}

export default async function LocalizedLanePage(props: Props) {
  const { lang: rawLang, slug, lane } = await props.params;
  if (!hasLocale(rawLang)) notFound();
  const lang: Locale = rawLang;
  const champion = getChampion(slug);
  const data = laneFor(slug, lane);
  if (!champion || !data) notFound();
  const t = dict(lang);
  const name = champName(champion.name, lang);
  const laneName = t.lanes[lane as Lane];
  const items = usableRows(data.tabs.items, "items").slice(0, 6);
  const runes = usableRows(data.tabs.runes, "runes").slice(0, 4);
  const spells = usableRows(data.tabs.spells, "spells").slice(0, 3);
  const boots = usableRows(data.tabs.boots, "boots").slice(0, 3);
  const versus = usableRows(data.tabs.versus, "versus");
  const partners = data.versusKind === "partners";
  const good = [...versus].sort((a, b) => b.winRate - a.winRate).filter((r) => r.winRate >= 50).slice(0, 6);
  const bad = [...versus].sort((a, b) => a.winRate - b.winRate).filter((r) => r.winRate < 50).slice(0, 6);
  const others = lanePages(slug).filter((l) => l.lane !== lane);

  const faq: Faq = [];
  if (items[0]) faq.push({ q: t.faqLaneBuildQ(name, laneName), a: t.faqLaneBuildA(items[0].entities.map((e) => entityName(e.name, lang)).join(", "), fmtPct(lang, items[0].pickRate), fmtPct(lang, items[0].winRate)) });
  if (!partners && bad[0]) faq.push({ q: t.faqCounterQ(name), a: t.faqCounterA(bad.slice(0, 3).map((r) => `${entityName(r.entities[0]?.name ?? "", lang)} (${fmtPct(lang, r.winRate)})`).join(", ")) });

  const block = (title: string, rows: typeof items, note?: string) => rows.length > 0 && (
    <Card className="p-5 sm:p-6">
      <h2 className="text-lg font-semibold">{title}</h2>
      {note && <p className="mt-1 text-xs text-gold">{note}</p>}
      <LocalizedRows rows={rows} lang={lang} t={t} />
    </Card>
  );
  return (
    <Container className="py-10 sm:py-14">
      <LanguageSwitcher path={`/champions/${slug}/${lane}`} current={lang} label={t.language} />
      <nav className="mt-4 text-sm text-faint"><Link href={`/${lang}/champions/${slug}`} className="hover:text-text">&larr; {t.back(name)}</Link></nav>
      <div className="mt-4 flex items-center gap-4">
        <ChampionAvatar champion={champion} size={64} showBadges={false} />
        <div>
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">{t.laneH1(name, laneName)}</h1>
          <p className="mt-1 text-sm text-muted">Wild Rift · {t.patch(CURRENT_PATCH ?? "")} · {t.sourceChina}</p>
        </div>
      </div>
      <div className="mt-8 grid gap-5 lg:grid-cols-2">
        {block(t.itemCores, items)}
        {block(t.runePages, runes)}
        {block(t.spells, spells)}
        {block(t.boots, boots, data.tabs.boots.stale ? t.bootsStale : undefined)}
      </div>
      {(good.length > 0 || bad.length > 0) && (
        <section className="mt-10">
          <h2 className="text-xl font-semibold">{t.matchups}</h2>
          <div className="mt-4 grid gap-5 lg:grid-cols-2">
            {good.length > 0 && <Card className="p-5"><h3 className="text-sm font-semibold text-emerald-300">{partners ? t.partnersGood : t.winsAgainst(name)}</h3><LocalizedRows rows={good} lang={lang} t={t} /></Card>}
            {bad.length > 0 && <Card className="p-5"><h3 className="text-sm font-semibold text-rose-300">{partners ? t.partnersBad : t.losesTo(name)}</h3><LocalizedRows rows={bad} lang={lang} t={t} /></Card>}
          </div>
        </section>
      )}
      {others.length > 0 && (
        <p className="mt-8 text-sm text-muted">
          {t.alsoPlayed(name)}{" "}
          {others.map((l, i) => <span key={l.lane}>{i > 0 && ", "}<Link href={`/${lang}/champions/${slug}/${l.lane}`} className="font-semibold text-text hover:text-accent">{t.lanes[l.lane as Lane]}</Link></span>)}
        </p>
      )}
      <FaqSection faq={faq} title={t.questions(name)} />
      <p className="mt-10 text-sm"><Link href={`/champions/${slug}/${lane}`} className="text-accent hover:underline">{t.englishPage}</Link></p>
    </Container>
  );
}
