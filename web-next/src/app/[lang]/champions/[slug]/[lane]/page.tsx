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
import { LANE_LABEL, championSubpages, laneFor, lanePages, usableRows, type Faq, type Lane } from "@/lib/champion-seo";
import { ChampionPageLinks, FaqSection, LoadoutRows } from "@/components/champion-seo-parts";

/**
 * "<champion> <lane> build": one page per champion and lane with its own
 * measured China Legendary data (item cores, rune pages, boots, spells and
 * lane matchups). See lib/champion-seo.ts for why these exist and the rule
 * that a lane only gets a page when it has its own measured rows.
 *
 * Static segments win over this dynamic one, so /champions/<slug>/counters
 * and /runes keep their own pages.
 */

export function generateStaticParams({ params }: { params: { lang: string } }) {
  // English is pre-built; the other languages render on first request.
  if (params.lang !== "en") return [];
  return getChampions()
    .filter((c) => !c.statsPending)
    .flatMap((c) => lanePages(c.slug).map((l) => ({ slug: c.slug, lane: l.lane })));
}
export const revalidate = 86400;

type Props = PageProps<"/[lang]/champions/[slug]/[lane]">;

export async function generateMetadata(props: Props): Promise<Metadata> {
  const { lang, slug, lane } = await props.params;
  const champion = getChampion(slug);
  const data = laneFor(slug, lane);
  if (!champion || !data) return { title: "Not found" };
  const label = LANE_LABEL[lane as Lane];
  const core = usableRows(data.tabs.items, "items")[0];
  const t = getT(lang);
  const name = displayName(champion.name, lang);
  const title = t("{name} {lane} Build in Wild Rift (Patch {patch}): Items, Runes and Matchups", { name, lane: t(label), patch: CURRENT_PATCH ?? "" });
  const description = t("{name} {lane} in Wild Rift: the most-played item cores, rune pages, spells and lane matchups, with win and pick rates from China Legendary ranked.", { name, lane: t(label) });
  return {
    title, description,
    alternates: { canonical: lp(lang, `/champions/${slug}/${lane}`), languages: languageAlternates(`/champions/${slug}/${lane}`) },
    openGraph: { title, description, url: `https://wrtruemeta.com/champions/${slug}/${lane}` },
  };
}

export default async function LanePage(props: Props) {
  const { lang, slug, lane } = await props.params;
  if (!isPageLang(lang)) notFound();
  const champion = getChampion(slug);
  const data = laneFor(slug, lane);
  if (!champion || !data) notFound();
  const label = LANE_LABEL[lane as Lane];
  const items = usableRows(data.tabs.items, "items").slice(0, 6);
  const runes = usableRows(data.tabs.runes, "runes").slice(0, 4);
  const spells = usableRows(data.tabs.spells, "spells").slice(0, 3);
  const boots = usableRows(data.tabs.boots, "boots").slice(0, 3);
  const versus = usableRows(data.tabs.versus, "versus");
  const isPartners = data.versusKind === "partners";
  const good = [...versus].sort((a, b) => b.winRate - a.winRate).filter((r) => r.winRate >= 50).slice(0, 6);
  const bad = [...versus].sort((a, b) => a.winRate - b.winRate).filter((r) => r.winRate < 50).slice(0, 6);
  const captured = data.capturedAt?.slice(0, 10);

  const t = getT(lang);
  const name = displayName(champion.name, lang);
  const laneName = t(label);
  const ent = (n: string) => (hasLocale(lang) ? entityName(n, lang) : n);
  const faq: Faq = [];
  if (items[0]) faq.push({
    q: t("What is the best {name} {lane} build?", { name, lane: laneName }),
    a: t("The most-played {name} {lane} core in China Legendary ranked is {core} ({pick}% of games, {win}% win rate).", { name, lane: laneName, core: items[0].entities.map((e) => ent(e.name)).join(", "), pick: items[0].pickRate.toFixed(1), win: items[0].winRate.toFixed(1) }),
  });
  if (runes[0]) faq.push({
    q: t("What runes does {name} take in the {lane}?", { name, lane: laneName }),
    a: t("The most-played page is {page} ({pick}% pick, {win}% win).", { page: runes[0].entities.map((e) => ent(e.name)).join(", "), pick: runes[0].pickRate.toFixed(1), win: runes[0].winRate.toFixed(1) }),
  });
  if (!isPartners && bad[0]) faq.push({
    q: t("Who counters {name} {lane}?", { name, lane: laneName }),
    a: bad.slice(0, 3).map((r) => t("{champ} ({name} wins {wr}%)", { champ: ent(r.entities[0]?.name ?? ""), name, wr: r.winRate.toFixed(1) })).join(", ") + ".",
  });

  const otherLanes = lanePages(slug).filter((l) => l.lane !== lane);
  return (
    <Container className="py-10 sm:py-14">
      <JsonLd data={breadcrumbJsonLd([
        { name: "Champions", path: "/champions" },
        { name: champion.name, path: `/champions/${slug}` },
        { name: label, path: `/champions/${slug}/${lane}` },
      ])} />
      <nav className="text-sm text-faint"><Link href={lp(lang, `/champions/${slug}`)} className="hover:text-text"><T>{"&larr;"}</T> {champion.name}</Link></nav>
      <div className="mt-4 flex items-center gap-4">
        <ChampionAvatar champion={champion} size={64} showBadges={false} />
        <div>
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl"><T vars={{ name: displayName(champion.name, lang), lane: label }}>{"{name} {lane} build"}</T></h1>
          <p className="mt-1 text-sm text-muted">
            <T>{"Wild Rift"}</T>{CURRENT_PATCH ? ` patch ${CURRENT_PATCH}` : ""} <T>{"· China Legendary ranked"}</T>{captured ? ` · captured ${captured}` : ""}
          </p>
        </div>
      </div>
      <div className="-mx-4 sm:-mx-6"><ChampionPageLinks slug={slug} name={champion.name} links={championSubpages(champion)} current={`/champions/${slug}/${lane}`} lang={lang} /></div>

      <div className="mt-8 grid gap-5 lg:grid-cols-2">
        {items.length > 0 && (
          <Card className="p-5 sm:p-6">
            <h2 className="text-lg font-semibold"><T>{"Item cores"}</T></h2>
            <p className="mt-1 text-sm text-muted"><T vars={{ name: displayName(champion.name, lang), lane: label }}>{"The three-item cores {name} {lane} players finish most, by how often they are built."}</T></p>
            <LoadoutRows rows={items} />
          </Card>
        )}
        {runes.length > 0 && (
          <Card className="p-5 sm:p-6">
            <h2 className="text-lg font-semibold"><T>{"Rune pages"}</T></h2>
            <p className="mt-1 text-sm text-muted"><T>{"Keystone and minor runes, most-played first."}</T></p>
            <LoadoutRows rows={runes} />
          </Card>
        )}
        {spells.length > 0 && (
          <Card className="p-5 sm:p-6">
            <h2 className="text-lg font-semibold"><T>{"Summoner spells"}</T></h2>
            <LoadoutRows rows={spells} />
          </Card>
        )}
        {boots.length > 0 && (
          <Card className="p-5 sm:p-6">
            <h2 className="text-lg font-semibold"><T>{"Boots"}</T></h2>
            {data.tabs.boots.stale && <p className="mt-1 text-xs text-gold"><T>{"Older data: China’s app stopped updating its boots page in July 2026."}</T></p>}
            <LoadoutRows rows={boots} />
          </Card>
        )}
      </div>

      {(good.length > 0 || bad.length > 0) && (
        <section className="mt-10">
          <h2 className="text-xl font-semibold">{isPartners ? `Best partners for ${champion.name}` : `${champion.name} ${label.toLowerCase()} matchups`}</h2>
          <p className="mt-1 text-sm text-muted">{champion.name}<T>{"’s win rate"}</T> {isPartners ? <><T>{"alongside"}</T></> : <><T>{"against"}</T></>} <T>{"each champion, where it makes up at least 1% of games."}</T></p>
          <div className="mt-4 grid gap-5 lg:grid-cols-2">
            {good.length > 0 && <Card className="p-5"><h3 className="text-sm font-semibold text-emerald-300">{isPartners ? <><T>{"Works well with"}</T></> : `${champion.name} wins against`}</h3><LoadoutRows rows={good} /></Card>}
            {bad.length > 0 && <Card className="p-5"><h3 className="text-sm font-semibold text-rose-300">{isPartners ? <><T>{"Struggles with"}</T></> : `${champion.name} loses to`}</h3><LoadoutRows rows={bad} /></Card>}
          </div>
        </section>
      )}

      {otherLanes.length > 0 && (
        <p className="mt-8 text-sm text-muted">
          <T vars={{ name: displayName(champion.name, lang) }}>{"{name} is also played in"}</T>{" "}
          {otherLanes.map((l, i) => (
            <span key={l.lane}>{i > 0 && ", "}<Link href={lp(lang, `/champions/${slug}/${l.lane}`)} className="font-semibold text-text hover:text-accent">{LANE_LABEL[l.lane as Lane]}</Link></span>
          ))}.
        </p>
      )}

      <FaqSection faq={faq} title={t("{name} {lane} questions", { name, lane: laneName })} />
    </Container>
  );
}
