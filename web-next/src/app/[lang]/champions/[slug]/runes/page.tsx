import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getChampion } from "@/lib/data";
import { CURRENT_PATCH } from "@/lib/patch";
import { Container, Card, ChampionAvatar } from "@/components/ui";
import { getChampionLoadouts } from "@/lib/cn-loadouts";
import { LANE_LABEL, hasRunesPage, ladderRunes, runeInfo, usableRows, type Faq, type Lane } from "@/lib/champion-seo";
import { champName, hasLocale, languageAlternates, runeName, type Locale } from "@/lib/i18n";
import { dict } from "@/lib/i18n-dict";
import { FaqSection } from "@/components/champion-seo-parts";
import { LanguageSwitcher, LocalizedRows } from "@/components/i18n-parts";

/** Translated runes page; same data and gating as app/champions/[slug]/runes. */
export const revalidate = 86400;
export function generateStaticParams() {
  return [];
}

type Props = PageProps<"/[lang]/champions/[slug]/runes">;

export async function generateMetadata(props: Props): Promise<Metadata> {
  const { lang, slug } = await props.params;
  const champion = getChampion(slug);
  if (!hasLocale(lang) || !champion || !hasRunesPage(champion)) return { title: "Not found" };
  const t = dict(lang);
  const name = champName(champion.name, lang);
  const title = { absolute: t.runesTitle(name, CURRENT_PATCH ?? "") };
  const description = t.runesDescription(name);
  return {
    title, description,
    alternates: { canonical: `/${lang}/champions/${slug}/runes`, languages: languageAlternates(`/champions/${slug}/runes`) },
    openGraph: { title: title.absolute, description, url: `https://wrtruemeta.com/${lang}/champions/${slug}/runes` },
  };
}

export default async function LocalizedRunesPage(props: Props) {
  const { lang: rawLang, slug } = await props.params;
  if (!hasLocale(rawLang)) notFound();
  const lang: Locale = rawLang;
  const champion = getChampion(slug);
  if (!champion || !hasRunesPage(champion)) notFound();
  const t = dict(lang);
  const name = champName(champion.name, lang);
  const ladder = ladderRunes(champion.name);
  const keystones = ladder.keystones.slice(0, 3);
  const minors = ladder.minors.slice(0, 8);
  const lanes = getChampionLoadouts(slug)
    .map((l) => ({ lane: l.lane as Lane, rows: usableRows(l.tabs.runes, "runes").slice(0, 4) }))
    .filter((l) => l.rows.length > 0 && LANE_LABEL[l.lane]);

  const faq: Faq = [];
  if (keystones[0] && ladder.players) faq.push({ q: t.faqRunesQ(name), a: t.faqRunesA(runeName(keystones[0].name, lang), keystones[0].count, ladder.players) });

  return (
    <Container className="py-10 sm:py-14">
      <LanguageSwitcher path={`/champions/${slug}/runes`} current={lang} label={t.language} />
      <nav className="mt-4 text-sm text-faint"><Link href={`/${lang}/champions/${slug}`} className="hover:text-text">&larr; {t.back(name)}</Link></nav>
      <div className="mt-4 flex items-center gap-4">
        <ChampionAvatar champion={champion} size={64} showBadges={false} />
        <div>
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">{t.runesH1(name)}</h1>
          <p className="mt-1 text-sm text-muted">Wild Rift · {t.patch(CURRENT_PATCH ?? "")}</p>
        </div>
      </div>
      {keystones.length > 0 && (
        <section className="mt-8">
          <h2 className="text-xl font-semibold">{t.whatTopPlayersRun(name)}</h2>
          <p className="mt-1 text-sm text-muted">{t.sourceLadder}</p>
          <div className="mt-4 grid gap-4 md:grid-cols-3">
            {keystones.map((k) => {
              const info = runeInfo(k.name);
              return (
                <Card key={k.name} className="flex items-center gap-3 p-5">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  {info?.icon && <img src={info.icon} alt="" width={40} height={40} className="rounded-full ring-1 ring-white/10" />}
                  <div>
                    <h3 className="text-base font-semibold text-text">{runeName(k.name, lang)}</h3>
                    <p className="text-xs text-muted">{t.ofPlayers(k.count, ladder.players)}</p>
                  </div>
                </Card>
              );
            })}
          </div>
          {minors.length > 0 && (
            <Card className="mt-4 p-5">
              <h3 className="text-sm font-semibold text-text">{t.minorRunes}</h3>
              <ul className="mt-3 flex flex-wrap gap-2">
                {minors.map((m) => <li key={m.name} className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-xs text-muted"><span className="text-text">{runeName(m.name, lang)}</span> · {m.count}</li>)}
              </ul>
            </Card>
          )}
        </section>
      )}
      {lanes.length > 0 && (
        <section className="mt-10">
          <h2 className="text-xl font-semibold">{t.runePagesByLane}</h2>
          <p className="mt-1 text-sm text-muted">{t.sourceChina}</p>
          <div className="mt-4 grid gap-5 lg:grid-cols-2">
            {lanes.map((l) => (
              <Card key={l.lane} className="p-5">
                <h3 className="text-sm font-semibold"><Link href={`/${lang}/champions/${slug}/${l.lane}`} className="hover:text-accent">{t.lanes[l.lane]}</Link></h3>
                <LocalizedRows rows={l.rows} lang={lang} t={t} />
              </Card>
            ))}
          </div>
        </section>
      )}
      <FaqSection faq={faq} title={t.questions(name)} />
      <p className="mt-10 text-sm"><Link href={`/champions/${slug}/runes`} className="text-accent hover:underline">{t.englishPage}</Link></p>
    </Container>
  );
}
