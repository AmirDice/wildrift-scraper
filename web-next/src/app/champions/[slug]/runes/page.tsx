import type { Metadata } from "next";
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

export function generateStaticParams() {
  return getChampions().filter((c) => !c.statsPending && hasRunesPage(c)).map((c) => ({ slug: c.slug }));
}
export const dynamicParams = false;

type Props = PageProps<"/champions/[slug]/runes">;

export async function generateMetadata(props: Props): Promise<Metadata> {
  const { slug } = await props.params;
  const champion = getChampion(slug);
  if (!champion) return { title: "Not found" };
  const top = ladderRunes(champion.name).keystones[0];
  const title = `${champion.name} Runes in Wild Rift${CURRENT_PATCH ? ` (Patch ${CURRENT_PATCH})` : ""}: Best Keystone and Rune Pages`;
  const description = `The runes top ${champion.name} players run in Wild Rift${top ? `, led by ${top.name}` : ""}, plus the most-played rune pages per lane with win and pick rates.`;
  return {
    title, description,
    alternates: { canonical: `/champions/${slug}/runes` },
    openGraph: { title, description, url: `https://wrtruemeta.com/champions/${slug}/runes` },
  };
}

export default async function RunesPage(props: Props) {
  const { slug } = await props.params;
  const champion = getChampion(slug);
  if (!champion || !hasRunesPage(champion)) notFound();
  const ladder = ladderRunes(champion.name);
  const lanes = getChampionLoadouts(slug)
    .map((l) => ({ lane: l.lane as Lane, rows: usableRows(l.tabs.runes, "runes").slice(0, 4) }))
    .filter((l) => l.rows.length > 0 && LANE_LABEL[l.lane]);
  const keystones = ladder.keystones.slice(0, 3);
  const minors = ladder.minors.slice(0, 8);

  const faq: Faq = [];
  if (keystones[0] && ladder.players) faq.push({
    q: `What is the best keystone for ${champion.name}?`,
    a: `${keystones[0].name}: ${keystones[0].count} of the ${ladder.players} top ${champion.name} players measured in EU and NA run it${keystones[1] ? `, and ${keystones[1].count} run ${keystones[1].name}` : ""}.`,
  });
  if (minors.length >= 3) faq.push({
    q: `What minor runes do top ${champion.name} players take?`,
    a: `${minors.slice(0, 4).map((m) => `${m.name} (${m.count})`).join(", ")}, counted across the top players measured.`,
  });
  if (lanes[0]) faq.push({
    q: `What rune page is most played on ${champion.name}?`,
    a: `In ${LANE_LABEL[lanes[0].lane]}, ${lanes[0].rows[0].entities.map((e) => e.name).join(", ")} (${lanes[0].rows[0].pickRate.toFixed(1)}% pick, ${lanes[0].rows[0].winRate.toFixed(1)}% win) in China Legendary ranked.`,
  });

  return (
    <Container className="py-10 sm:py-14">
      <JsonLd data={breadcrumbJsonLd([
        { name: "Champions", path: "/champions" },
        { name: champion.name, path: `/champions/${slug}` },
        { name: "Runes", path: `/champions/${slug}/runes` },
      ])} />
      <nav className="text-sm text-faint"><Link href={`/champions/${slug}`} className="hover:text-text">&larr; {champion.name}</Link></nav>
      <div className="mt-4 flex items-center gap-4">
        <ChampionAvatar champion={champion} size={64} showBadges={false} />
        <div>
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">{champion.name} runes</h1>
          <p className="mt-1 text-sm text-muted">Wild Rift{CURRENT_PATCH ? ` patch ${CURRENT_PATCH}` : ""} · top EU and NA players, and China Legendary ranked</p>
        </div>
      </div>
      <ChampionPageLinks slug={slug} name={champion.name} links={championSubpages(champion).filter((l) => !l.href.endsWith("/runes"))} />

      {keystones.length > 0 && (
        <section className="mt-8">
          <h2 className="text-xl font-semibold">What top {champion.name} players run</h2>
          <p className="mt-1 text-sm text-muted">Counted across the {ladder.players} best {champion.name} players on the EU and NA leaderboards.</p>
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
                      <p className="text-xs text-muted">{k.count} of {ladder.players} players</p>
                    </div>
                  </div>
                  {info?.description && <p className="mt-3 text-xs leading-relaxed text-muted">{info.description}</p>}
                </Card>
              );
            })}
          </div>
          {minors.length > 0 && (
            <Card className="mt-4 p-5">
              <h3 className="text-sm font-semibold text-text">Minor runes</h3>
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
          <h2 className="text-xl font-semibold">Most-played rune pages by lane</h2>
          <p className="mt-1 text-sm text-muted">China Legendary ranked, with each page&rsquo;s win rate and how often it is picked.</p>
          <div className="mt-4 grid gap-5 lg:grid-cols-2">
            {lanes.map((l) => (
              <Card key={l.lane} className="p-5">
                <h3 className="text-sm font-semibold text-text">
                  <Link href={`/champions/${slug}/${l.lane}`} className="hover:text-accent">{LANE_LABEL[l.lane]}</Link>
                </h3>
                <LoadoutRows rows={l.rows} />
              </Card>
            ))}
          </div>
        </section>
      )}

      <FaqSection faq={faq} title={`${champion.name} rune questions`} />
    </Container>
  );
}
