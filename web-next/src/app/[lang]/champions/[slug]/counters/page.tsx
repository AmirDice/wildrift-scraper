import { T } from "@/components/t";
import { getT } from "@/lib/ui-i18n";
import { displayName } from "@/lib/i18n";
import type { Metadata } from "next";
import { isPageLang, lp } from "@/lib/i18n";
import { languageAlternates } from "@/lib/i18n";
import Link from "next/link";
import { notFound } from "next/navigation";
import itemsCatalogue from "@/data/items.json";
import { getChampion, getChampions } from "@/lib/data";
import { getMatchups, hasCounterPage, matchupsCapturedOn, type ResolvedMatchup } from "@/lib/counters";
import { roster, type RosterChampion } from "@/lib/threat";
import { CURRENT_PATCH } from "@/lib/patch";
import { BUILD_TOOLS_LIVE } from "@/lib/flags";
import { Container, Card, ChampionAvatar } from "@/components/ui";
import { ChampionPageLinks } from "@/components/champion-seo-parts";
import { championSubpages } from "@/lib/champion-seo";

/**
 * "How to counter <champion>": one page per champion for the counter query.
 *
 * Search Console showed champion pages picking up "<champion> counter wild
 * rift", where a section halfway down a build page has to compete with sites
 * whose whole page answers exactly that. This page answers it: every measured
 * counter, not the champion page's top five; who to avoid; and what to build
 * against the kit, from the kit's own traits.
 *
 * Everything is measured or derived, nothing written per champion: matchups
 * from China Legendary ranked (lib/counters.ts), the item advice from the
 * champion's damage type and mechanics (lib/threat.ts). A champion with too
 * few measured matchups gets no page, rather than a thin one Google would
 * treat as a near-copy of the champion page.
 */

const LANE: Record<string, string> = { baron: "Baron", jungle: "Jungle", mid: "Mid", dragon: "Dragon", support: "Support" };

export function generateStaticParams({ params }: { params: { lang: string } }) {
  // English is pre-built; the other languages render on first request.
  if (params.lang !== "en") return [];
  return getChampions().filter((c) => !c.statsPending && hasCounterPage(c.slug)).map((c) => ({ slug: c.slug }));
}
export const revalidate = 86400;

export async function generateMetadata(props: PageProps<"/[lang]/champions/[slug]/counters">): Promise<Metadata> {
  const { lang, slug } = await props.params;
  const champion = getChampion(slug);
  if (!champion) return { title: "Champion not found" };
  const { weak } = getMatchups(slug);
  const top = weak.slice(0, 3).map((m) => m.champion.name);
  const t = getT(lang);
  const name = displayName(champion.name, lang);
  const title = t("How to Counter {name} in Wild Rift (Patch {patch})", { name, patch: CURRENT_PATCH ?? "" });
  const description = t("The champions that beat {name} most often in Wild Rift ranked: {top}. Measured matchup win rates, who to avoid, and what to build against {name}.", { name, top: top.map((n) => displayName(n, lang)).join(", ") });
  return {
    title, description,
    alternates: { canonical: lp(lang, `/champions/${slug}/counters`), languages: languageAlternates(`/champions/${slug}/counters`) },
    openGraph: { title, description, url: `https://wrtruemeta.com/champions/${slug}/counters` },
  };
}

const ITEMS = new Map((itemsCatalogue as { slug: string; name: string; icon: string }[]).map((i) => [i.slug, i]));

interface Tip { title: string; body: string; items: string[] }

/** What to build and how to play against a kit, from its traits. */
function tipsFor(name: string, kit: RosterChampion | undefined): Tip[] {
  if (!kit) return [];
  const tips: Tip[] = [];
  const mech = new Set(kit.mechanics ?? []);
  if (kit.primaryDamage === "physical") {
    tips.push({ title: "Stack armor", body: `${name} deals mostly physical damage, so armor is the stat that blunts it. Plated Steelcaps are the boots for it.`, items: ["plated-steelcaps", "randuins-omen", "frozen-heart"] });
  } else if (kit.primaryDamage === "magic") {
    tips.push({ title: "Stack magic resist", body: `${name} deals mostly magic damage, so magic resist is the stat that blunts it.`, items: ["mercurys-treads", "force-of-nature", "banshees-veil"] });
  }
  if (mech.has("heal")) {
    tips.push({ title: "Buy anti-heal early", body: `${name} heals in fights. Grievous Wounds cuts that healing, and it is worth buying as an early component rather than a last item.`, items: ["thornmail", "mortal-reminder", "morellonomicon", "chempunk-chainsword"] });
  }
  if (mech.has("shield")) {
    tips.push({ title: "Cut through shields", body: `${name} relies on shields. Shield-reduction items take a bite out of every one of them.`, items: ["serpents-fang"] });
  }
  if ((kit.ccDepth ?? 0) >= 2) {
    tips.push({ title: "Prepare for crowd control", body: `${name} has ${kit.ccDepth} abilities with hard crowd control. Tenacity shortens it and a cleanse removes it, so a single stun stops deciding the fight.`, items: ["mercurys-treads", "quicksilver-sash", "mercurial-scimitar"] });
  }
  if (mech.has("dash")) {
    tips.push({ title: "Hold your crowd control for after the dash", body: `${name} has a dash. Using a stun or root before it is spent lets ${name} walk straight out of it; wait for the dash, then lock them down.`, items: [] });
  }
  if (kit.trueDamage) {
    tips.push({ title: "Mind the true damage", body: `Part of ${name}'s damage is true damage, which ignores armor and magic resist. Resistances still cut the rest; add some health, and avoid long extended trades where the true damage piles up.`, items: [] });
  }
  return tips;
}

const pct = (n: number) => `${n.toFixed(1)}%`;

export default async function CountersPage(props: PageProps<"/[lang]/champions/[slug]/counters">) {
  const { lang, slug } = await props.params;
  if (!isPageLang(lang)) notFound();
  const champion = getChampion(slug);
  if (!champion || !hasCounterPage(slug)) notFound();
  const { strong, weak } = getMatchups(slug);
  const kit = roster()[champion.name] as RosterChampion | undefined;
  const tips = tipsFor(champion.name, kit);
  const captured = matchupsCapturedOn(slug);
  const capturedLabel = captured && /^\d{8}$/.test(captured) ? `${captured.slice(6)}.${captured.slice(4, 6)}.${captured.slice(0, 4)}` : captured;
  const best = weak[0];

  return (
    <Container className="py-10 sm:py-14">
      <nav className="text-sm text-faint"><Link href={lp(lang, `/champions/${slug}`)} className="hover:text-text"><T>{"&larr;"}</T> {champion.name}</Link></nav>
      <div className="mt-4 flex items-center gap-4">
        <ChampionAvatar champion={champion} size={64} showBadges={false} />
        <div>
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl"><T vars={{ name: displayName(champion.name, lang) }}>{"How to counter {name}"}</T></h1>
          <p className="mt-1 text-sm text-muted"><T>{"Wild Rift"}</T>{CURRENT_PATCH ? ` patch ${CURRENT_PATCH}` : ""} <T>{"· measured in China Legendary ranked"}</T></p>
        </div>
      </div>
      <div className="-mx-4 sm:-mx-6"><ChampionPageLinks slug={slug} name={champion.name} links={championSubpages(champion)} current={`/champions/${slug}/counters`} lang={lang} /></div>

      <Card className="mt-6 p-5 sm:p-6">
        <p className="max-w-3xl text-sm leading-relaxed text-muted">
          {best ? <><span className="font-semibold text-text">{best.champion.name}</span> <T>{"is the strongest counter:"}</T> {champion.name} <T>{"wins only"}</T> <span className="font-semibold text-rose-300">{pct(best.winRate)}</span> <T>{"of those games."}</T> </> : null}
          {weak.length} <T>{"champions beat"}</T> {champion.name} <T>{"more often than not, and"}</T> {champion.name} <T>{"beats"}</T> {strong.length}<T>{". Each figure is"}</T> {champion.name}<T>{"’s own win rate in the matchup, so lower is better for you, counted only where the matchup makes up at least 1% of"}</T> {champion.name}<T>{"’s games."}</T>
        </p>
      </Card>

      <section className="mt-8">
        <h2 className="text-xl font-semibold"><T vars={{ name: displayName(champion.name, lang) }}>{"Best counters to {name}"}</T></h2>
        <p className="mt-1 text-sm text-muted"><T vars={{ name: displayName(champion.name, lang) }}>{"Pick one of these into {name}. The number is {name}’s win rate against them."}</T></p>
        <MatchupGrid rows={weak} self={champion.name} tone="good" buildLinks />
      </section>

      {tips.length > 0 && (
        <section className="mt-10">
          <h2 className="text-xl font-semibold"><T vars={{ name: displayName(champion.name, lang) }}>{"What to build against {name}"}</T></h2>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {tips.map((tip) => (
              <Card key={tip.title} className="p-5">
                <h3 className="text-sm font-semibold text-text">{tip.title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-muted">{tip.body}</p>
                {tip.items.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {tip.items.map((s) => ITEMS.get(s)).filter((i): i is NonNullable<typeof i> => Boolean(i)).map((item) => (
                      <span key={item.slug} className="flex items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.04] px-2 py-1.5 text-xs text-muted">
                        {/* eslint-disable-next-line @next/next/no-img-element -- catalogue icon */}
                        <img src={item.icon} alt="" width={22} height={22} className="h-[22px] w-[22px] rounded" loading="lazy" />
                        {item.name}
                      </span>
                    ))}
                  </div>
                )}
              </Card>
            ))}
          </div>
        </section>
      )}

      {strong.length > 0 && (
        <section className="mt-10">
          <h2 className="text-xl font-semibold"><T vars={{ name: displayName(champion.name, lang) }}>{"Avoid picking these into {name}"}</T></h2>
          <p className="mt-1 text-sm text-muted"><T vars={{ name: displayName(champion.name, lang) }}>{"{name} beats these more often than not."}</T></p>
          <MatchupGrid rows={strong} self={champion.name} tone="bad" />
        </section>
      )}

      <p className="mt-8 text-xs leading-relaxed text-faint">
        <T>{"Matchups from China’s Legendary ranked queue"}</T>{capturedLabel ? `, captured ${capturedLabel}` : ""}<T>{". Item advice follows"}</T> {champion.name}<T>{"’s damage type and abilities."}</T>{" "}
        <Link href={lp(lang, `/champions/${slug}`)} className="underline underline-offset-2 hover:text-text"><T vars={{ name: displayName(champion.name, lang) }}>{"{name}’s build and win rate"}</T></Link>
        {BUILD_TOOLS_LIVE ? <> · <Link href="/build?tab=counter" className="underline underline-offset-2 hover:text-text"><T>{"Counter Builder"}</T></Link></> : null}
      </p>
    </Container>
  );
}

function MatchupGrid({ rows, self, tone, buildLinks = false }: { rows: ResolvedMatchup[]; self: string; tone: "good" | "bad"; buildLinks?: boolean }) {
  return (
    <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
      {rows.map(({ champion, winRate, pickRate, lane }) => (
        <div key={champion.slug} className="glass flex items-center gap-3 rounded-xl border border-white/[0.08] px-3 py-2.5">
          <Link href={`/champions/${champion.slug}`}><ChampionAvatar champion={champion} size={40} showBadges={false} /></Link>
          <div className="min-w-0 flex-1">
            <Link href={`/champions/${champion.slug}`} className="block truncate text-sm font-semibold text-text hover:text-accent">{champion.name}</Link>
            <p className="text-[0.7rem] text-faint">{LANE[lane] ?? lane} · {pct(pickRate)} <T>{"of"}</T> {self}<T>{"’s games"}</T></p>
            {buildLinks && BUILD_TOOLS_LIVE && (
              <Link href={`/build?champion=${encodeURIComponent(champion.name)}&tab=counter`} className="text-[0.7rem] font-semibold text-accent hover:text-text"><T>{"Build"}</T> {champion.name} <T>{"for this →"}</T></Link>
            )}
          </div>
          <span className={`shrink-0 text-sm font-semibold tabular-nums ${tone === "good" ? "text-emerald-300" : "text-rose-300"}`}>{pct(winRate)}</span>
        </div>
      ))}
    </div>
  );
}
