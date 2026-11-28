import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getChampion, tierLabel } from "@/lib/data";
import { getMatchups, hasCounterPage } from "@/lib/counters";
import { CURRENT_PATCH } from "@/lib/patch";
import { Container, Card, ChampionAvatar } from "@/components/ui";
import { JsonLd, breadcrumbJsonLd } from "@/lib/structured-data";
import { LANE_LABEL, hasRunesPage, ladderRunes, ladderTopItems, lanePages, type Faq, type Lane } from "@/lib/champion-seo";
import { champName, fmtPct, hasLocale, itemName, languageAlternates, runeName, type Locale } from "@/lib/i18n";
import { dict } from "@/lib/i18n-dict";
import { FaqSection } from "@/components/champion-seo-parts";
import { LanguageSwitcher } from "@/components/i18n-parts";

/**
 * Translated champion page (lib/i18n.ts). A compact version of the English
 * page: tier, win rate, what top players build and run, matchups, lanes and
 * the FAQ, all from the same data. Rendered on first request and cached, so
 * six languages add nothing to the build.
 */
export const revalidate = 86400;
export function generateStaticParams() {
  return [];
}

type Props = PageProps<"/[lang]/champions/[slug]">;

export async function generateMetadata(props: Props): Promise<Metadata> {
  const { lang, slug } = await props.params;
  const champion = getChampion(slug);
  if (!hasLocale(lang) || !champion || champion.statsPending) return { title: "Not found" };
  const t = dict(lang);
  const name = champName(champion.name, lang);
  const title = { absolute: t.champTitle(name, CURRENT_PATCH ?? "") };
  const description = t.champDescription(name, t.tierName(tierLabel(champion.tier)), fmtPct(lang, champion.wr));
  return {
    title, description,
    alternates: { canonical: `/${lang}/champions/${slug}`, languages: languageAlternates(`/champions/${slug}`) },
    openGraph: { title: title.absolute, description, url: `https://wrtruemeta.com/${lang}/champions/${slug}` },
  };
}

export default async function LocalizedChampionPage(props: Props) {
  const { lang: rawLang, slug } = await props.params;
  if (!hasLocale(rawLang)) notFound();
  const lang: Locale = rawLang;
  const champion = getChampion(slug);
  if (!champion || champion.statsPending) notFound();
  const t = dict(lang);
  const name = champName(champion.name, lang);
  const tier = t.tierName(tierLabel(champion.tier));
  const items = ladderTopItems(champion.name).slice(0, 6);
  const runes = ladderRunes(champion.name);
  const { strong, weak } = getMatchups(slug);
  const lanes = lanePages(slug);

  const faq: Faq = [];
  if (items.length >= 3) faq.push({ q: t.faqBuildQ(name), a: t.faqBuildA(name, items.slice(0, 5).map((i) => itemName(i, lang)).join(", ")) });
  if (weak.length) faq.push({ q: t.faqCounterQ(name), a: t.faqCounterA(weak.slice(0, 3).map((m) => `${champName(m.champion.name, lang)} (${fmtPct(lang, m.winRate)})`).join(", ")) });
  if (runes.keystones[0] && runes.players) faq.push({ q: t.faqRunesQ(name), a: t.faqRunesA(runeName(runes.keystones[0].name, lang), runes.keystones[0].count, runes.players) });
  faq.push({ q: t.faqGoodQ(name), a: t.faqGoodA(name, tier, fmtPct(lang, champion.wr)) });

  const sub = (path: string) => `/${lang}/champions/${slug}${path}`;
  return (
    <Container className="py-10 sm:py-14">
      <JsonLd data={breadcrumbJsonLd([{ name, path: `/${lang}/champions/${slug}` }])} />
      <LanguageSwitcher path={`/champions/${slug}`} current={lang} label={t.language} />
      <div className="mt-5 flex items-center gap-4">
        <ChampionAvatar champion={champion} size={72} showBadges={false} />
        <div>
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">{t.champH1(name)}</h1>
          <p className="mt-1 text-sm text-muted">Wild Rift · {t.patch(CURRENT_PATCH ?? "")}</p>
        </div>
      </div>

      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Card className="p-4"><p className="text-[0.65rem] uppercase tracking-wide text-faint">{t.tier}</p><p className="mt-1 text-xl font-bold">{tier}</p></Card>
        <Card className="p-4"><p className="text-[0.65rem] uppercase tracking-wide text-faint">{t.winRate}</p><p className="mt-1 text-xl font-bold">{fmtPct(lang, champion.wr)}</p></Card>
        <Card className="p-4"><p className="text-[0.65rem] uppercase tracking-wide text-faint">{t.role}</p><p className="mt-1 text-xl font-bold">{(champion.roles ?? [champion.role]).join(" / ")}</p></Card>
      </div>
      <p className="mt-2 text-xs text-faint">{t.sourceLadder}</p>

      {items.length > 0 && (
        <Card className="mt-6 p-5 sm:p-6">
          <h2 className="text-lg font-semibold">{t.topItems}</h2>
          <p className="mt-1 text-sm text-muted">{t.topItemsDesc(name)}</p>
          <ol className="mt-3 flex flex-wrap gap-2">
            {items.map((i, n) => <li key={i} className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-sm"><span className="text-faint">{n + 1}.</span> {itemName(i, lang)}</li>)}
          </ol>
        </Card>
      )}

      {runes.keystones.length > 0 && (
        <Card className="mt-4 p-5 sm:p-6">
          <h2 className="text-lg font-semibold">{t.runesHeading}</h2>
          <p className="mt-2 text-sm text-muted">
            {runes.keystones.slice(0, 2).map((k) => `${runeName(k.name, lang)} (${t.ofPlayers(k.count, runes.players)})`).join(" · ")}
          </p>
          {hasRunesPage(champion) && <Link href={sub("/runes")} className="mt-3 inline-block text-sm font-semibold text-accent">{t.runesH1(name)} &rarr;</Link>}
        </Card>
      )}

      {(strong.length > 0 || weak.length > 0) && (
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          {[{ title: t.strongAgainst(name), rows: strong, tone: "text-emerald-300" }, { title: t.weakAgainst(name), rows: weak, tone: "text-rose-300" }].map((block) => block.rows.length > 0 && (
            <Card key={block.title} className="p-5">
              <h2 className={`text-sm font-semibold ${block.tone}`}>{block.title}</h2>
              <ul className="mt-3 space-y-1.5">
                {block.rows.slice(0, 5).map((m) => (
                  <li key={m.champion.slug} className="flex justify-between text-sm">
                    <Link href={`/${lang}/champions/${m.champion.slug}`} className="hover:text-accent">{champName(m.champion.name, lang)}</Link>
                    <span className="tabular-nums text-muted">{fmtPct(lang, m.winRate)}</span>
                  </li>
                ))}
              </ul>
            </Card>
          ))}
        </div>
      )}
      {hasCounterPage(slug) && <Link href={sub("/counters")} className="mt-3 inline-block text-sm font-semibold text-accent">{t.countersH1(name)} &rarr;</Link>}

      {lanes.length > 0 && (
        <Card className="mt-6 p-5">
          <h2 className="text-lg font-semibold">{t.lanesHeading}</h2>
          <div className="mt-3 flex flex-wrap gap-2">
            {lanes.map((l) => (
              <Link key={l.lane} href={sub(`/${l.lane}`)} className="rounded-full border border-white/12 px-3 py-1 text-sm font-semibold text-muted hover:text-text">
                {t.laneH1(name, t.lanes[l.lane as Lane] ?? LANE_LABEL[l.lane as Lane])}
              </Link>
            ))}
          </div>
        </Card>
      )}

      <FaqSection faq={faq} title={t.questions(name)} />
      <p className="mt-10 text-sm"><Link href={`/champions/${slug}`} className="text-accent hover:underline">{t.englishPage}</Link></p>
    </Container>
  );
}
