import { T } from "@/components/t";
import { entityName, hasLocale } from "@/lib/i18n";
import { getT } from "@/lib/ui-i18n";
import { displayName } from "@/lib/i18n";
import type { Metadata } from "next";
import { isPageLang, lp } from "@/lib/i18n";
import { languageAlternates } from "@/lib/i18n";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getChampion, getChampions } from "@/lib/data";
import { CURRENT_PATCH } from "@/lib/patch";
import { Container, Card, ChampionAvatar } from "@/components/ui";
import { JsonLd, breadcrumbJsonLd } from "@/lib/structured-data";
import { getChampionLoadouts } from "@/lib/cn-loadouts";
import { LANE_LABEL, championSubpages, hasRunesPage, ladderRunes, runeInfo, usableRows, type Faq, type Lane } from "@/lib/champion-seo";
import { ChampionPageLinks, FaqSection, LoadoutRows } from "@/components/champion-seo-parts";

/**
 * "<champion> runes wild rift": the runes the champion's top EU/NA players
 * run (counts out of the players measured) and the official China Legendary
 * rune pages per lane (win and pick rates), with each keystone's own text.
 * Exists only for champions with measured rune data (lib/champion-seo.ts).
 */

export function generateStaticParams({ params }: { params: { lang: string } }) {
  // English is pre-built; the other languages render on first request.
  if (params.lang !== "en") return [];
  return getChampions().filter((c) => !c.statsPending && hasRunesPage(c)).map((c) => ({ slug: c.slug }));
}
export const revalidate = 86400;

type Props = PageProps<"/[lang]/champions/[slug]/runes">;

export async function generateMetadata(props: Props): Promise<Metadata> {
  const { lang, slug } = await props.params;
  const champion = getChampion(slug);
  if (!champion) return { title: "Not found" };
  const top = ladderRunes(champion.name).keystones[0];
  const t = getT(lang);
  const name = displayName(champion.name, lang);
  const title = t("{name} Runes in Wild Rift (Patch {patch}): Best Keystone and Rune Pages", { name, patch: CURRENT_PATCH ?? "" });
  const description = t("The runes top {name} players run in Wild Rift, plus the most-played rune pages per lane with win and pick rates.", { name });
  return {
    title, description,
    alternates: { canonical: lp(lang, `/champions/${slug}/runes`), languages: languageAlternates(`/champions/${slug}/runes`) },
    openGraph: { title, description, url: `https://wrtruemeta.com/champions/${slug}/runes` },
  };
}

export default async function RunesPage(props: Props) {
  const { lang, slug } = await props.params;
  if (!isPageLang(lang)) notFound();
  const champion = getChampion(slug);
  if (!champion || !hasRunesPage(champion)) notFound();
  const ladder = ladderRunes(champion.name);
  const lanes = getChampionLoadouts(slug)
    .map((l) => ({ lane: l.lane as Lane, rows: usableRows(l.tabs.runes, "runes").slice(0, 4) }))
    .filter((l) => l.rows.length > 0 && LANE_LABEL[l.lane]);
  const keystones = ladder.keystones.slice(0, 3);
  const minors = ladder.minors.slice(0, 8);

  const t = getT(lang);
  const name = displayName(champion.name, lang);
  const ent = (n: string) => (hasLocale(lang) ? entityName(n, lang) : n);
  const faq: Faq = [];
  if (keystones[0] && ladder.players) faq.push({
    q: t("What is the best keystone for {name}?", { name }),
    a: keystones[1]
      ? t("{keystone}: {count} of the {players} top {name} players measured in EU and NA run it, and {count2} run {keystone2}.", { keystone: ent(keystones[0].name), count: keystones[0].count, players: ladder.players, name, count2: keystones[1].count, keystone2: ent(keystones[1].name) })
      : t("{keystone}: {count} of the {players} top {name} players measured in EU and NA run it.", { keystone: ent(keystones[0].name), count: keystones[0].count, players: ladder.players, name }),
  });
  if (minors.length >= 3) faq.push({
    q: t("What minor runes do top {name} players take?", { name }),
    a: t("{list}, counted across the top players measured.", { list: minors.slice(0, 4).map((m) => `${ent(m.name)} (${m.count})`).join(", ") }),
  });
  if (lanes[0]) faq.push({
    q: t("What rune page is most played on {name}?", { name }),
    a: t("In {lane}, {page} ({pick}% pick, {win}% win) in China Legendary ranked.", { lane: t(LANE_LABEL[lanes[0].lane]), page: lanes[0].rows[0].entities.map((e) => ent(e.name)).join(", "), pick: lanes[0].rows[0].pickRate.toFixed(1), win: lanes[0].rows[0].winRate.toFixed(1) }),
  });

  return (
    <Container className="py-10 sm:py-14">
      <JsonLd data={breadcrumbJsonLd([
        { name: "Champions", path: "/champions" },
        { name: champion.name, path: `/champions/${slug}` },
        { name: "Runes", path: `/champions/${slug}/runes` },
      ])} />
      <nav className="text-sm text-faint"><Link href={lp(lang, `/champions/${slug}`)} className="hover:text-text"><T>{"&larr;"}</T> {champion.name}</Link></nav>
      <div className="mt-4 flex items-center gap-4">
        <ChampionAvatar champion={champion} size={64} showBadges={false} />
        <div>
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl"><T vars={{ name: displayName(champion.name, lang) }}>{"{name} runes"}</T></h1>
          <p className="mt-1 text-sm text-muted"><T>{"Wild Rift"}</T>{CURRENT_PATCH ? ` patch ${CURRENT_PATCH}` : ""} <T>{"· top EU and NA players, and China Legendary ranked"}</T></p>
        </div>
      </div>
      <div className="-mx-4 sm:-mx-6"><ChampionPageLinks slug={slug} name={champion.name} links={championSubpages(champion)} current={`/champions/${slug}/runes`} lang={lang} /></div>

      {keystones.length > 0 && (
        <section className="mt-8">
          <h2 className="text-xl font-semibold"><T vars={{ name: displayName(champion.name, lang) }}>{"What top {name} players run"}</T></h2>
          <p className="mt-1 text-sm text-muted"><T vars={{ name: displayName(champion.name, lang), n: ladder.players }}>{"Counted across the {n} best {name} players on the EU and NA leaderboards."}</T></p>
          <div className="mt-4 grid gap-4 md:grid-cols-3">
            {keystones.map((k) => {
              const info = runeInfo(k.name);
              return (
                <Card key={k.name} className="p-5">
                  <div className="flex items-center gap-3">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    {info?.icon && <img src={info.icon} alt="" width={40} height={40} className="rounded-full ring-1 ring-white/10" />}
                    <div>
                      <h3 className="text-base font-semibold text-text">{k.name}</h3>
                      <p className="text-xs text-muted"><T vars={{ count: k.count, n: ladder.players }}>{"{count} of {n} players"}</T></p>
                    </div>
                  </div>
                  {info?.description && <p className="mt-3 text-xs leading-relaxed text-muted">{info.description}</p>}
                </Card>
              );
            })}
          </div>
          {minors.length > 0 && (
            <Card className="mt-4 p-5">
              <h3 className="text-sm font-semibold text-text"><T>{"Minor runes"}</T></h3>
              <ul className="mt-3 flex flex-wrap gap-2">
                {minors.map((m) => (
                  <li key={m.name} className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-xs text-muted">
                    <span className="text-text">{m.name}</span> · {m.count}
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </section>
      )}

      {lanes.length > 0 && (
        <section className="mt-10">
          <h2 className="text-xl font-semibold"><T>{"Most-played rune pages by lane"}</T></h2>
          <p className="mt-1 text-sm text-muted"><T>{"China Legendary ranked, with each page’s win rate and how often it is picked."}</T></p>
          <div className="mt-4 grid gap-5 lg:grid-cols-2">
            {lanes.map((l) => (
              <Card key={l.lane} className="p-5">
                <h3 className="text-sm font-semibold text-text">
                  <Link href={lp(lang, `/champions/${slug}/${l.lane}`)} className="hover:text-accent">{LANE_LABEL[l.lane]}</Link>
                </h3>
                <LoadoutRows rows={l.rows} />
              </Card>
            ))}
          </div>
        </section>
      )}

      <FaqSection faq={faq} title={t("{name} rune questions", { name })} />
    </Container>
  );
}
