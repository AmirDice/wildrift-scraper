import type { Metadata } from "next";
import Link from "next/link";
import { site, getChampions, tierLabel, type Champion, regionBoard } from "@/lib/data";
import { BUILD_TOOLS_LIVE } from "@/lib/flags";
import { getCnChampions, getGlobalChampions } from "@/lib/cn";
import { risingPicks, overratedInEu } from "@/lib/gap";
import { climbingPicks, stomperPicks } from "@/lib/skew";
import { Container, TierChip, ChampionAvatar, SectionHeading, Card } from "@/components/ui";
import { HeroCarousel } from "@/components/hero-carousel";
import { HomeSearch } from "@/components/home-search";
import { InsightCard } from "@/components/insight-card";
import { MoversHighlight } from "@/components/movers-highlight";
import { BuildsGeneratedCount, BuildsGeneratedPill } from "@/components/builds-counter";
import { SeasonCard } from "@/components/season-card";
import { getChampionChangeRanking, getMostAdjustedChampions } from "@/lib/champion-change-ranking";
import { ITEM_CATALOG_COUNT } from "@/lib/advisor-catalog";

// The title and description come from the root layout; the home page only has
// to claim its own canonical so the root never competes with itself over
// "/" vs "/?ref=..." style variants.
export const metadata: Metadata = {
  alternates: { canonical: "/" },
};

export default function HomePage() {
  const champions = getChampions();
  const naBoard = regionBoard("NA");
  const bySlug = new Map(champions.map((c) => [c.slug, c]));
  const byName = new Map(champions.map((c) => [c.name, c]));
  const ranked = champions.filter((c) => (c.nPlayers ?? 0) >= 20);

  const globalChamps = getGlobalChampions();
  const globalBySlug = new Map(globalChamps.map((c) => [c.slug, c]));
  // Global nPlayers is the SUM of both boards, so the old EU threshold of 20
  // doubles to keep the same bar: roughly a full board on each server.
  const globalRanked = globalChamps.filter((c) => (c.nPlayers ?? 0) >= 40);
  const globalWeakestFirst = [...globalRanked].sort((a, b) => a.wr - b.wr);
  const globalBest = globalChamps.slice(0, 5);
  const globalWorst = [...globalChamps].slice(-5).reverse();

  // Legendary is Tencent's separate CN solo queue. A small pick-rate floor
  // keeps tiny samples from dominating the homepage discovery cards.
  const legendary = getCnChampions("4").filter((c) => c.cnPickRate >= 0.5);
  const legendaryBest = legendary.slice(0, 5);
  const legendaryWorst = [...legendary].sort((a, b) => a.wr - b.wr).slice(0, 5);

  const rising = risingPicks(5);
  const overrated = overratedInEu(5);

  const climbing = climbingPicks(5);
  const stompers = stomperPicks(5);

  const featured = globalChamps[0];
  const topPick = globalChamps[0];
  const lowest = globalWeakestFirst[0];
  const topMetaClass = site.metaBreakdown[0];
  const strongestRole = Object.entries(site.roleStrength)
    .filter(([, s]) => !s.lowConfidence)
    .sort((a, b) => b[1].wr - a[1].wr)[0];

  const topMeta = globalChamps.slice(0, 6);
  const topMastery = site.topMastery.slice(0, 6);
  const highestWr = globalChamps.slice(0, 5);
  const lowestWr = globalWeakestFirst.slice(0, 5);
  const offMeta = site.offMetaSlugs.map((s) => globalBySlug.get(s)).filter(Boolean).slice(0, 5) as Champion[];

  // Sort before slicing. Without it this took the first five OTP-flagged
  // champions in whatever order the source list happened to be in, so the card
  // showed a ranking that did not match the OTP score printed beside each name
  // -- and did not match /otp-champions, which has always sorted.
  const bestOtp = globalChamps
    .filter((c) => c.isOtp && c.otpScore != null)
    .sort((left, right) => (right.otpScore ?? 0) - (left.otpScore ?? 0))
    .slice(0, 5);
  // EU only, deliberately: the blend nulls skillSpread and winrateStd because
  // pooling a spread needs the per-player rows, not two summary figures.
  const skillCeiling = [...ranked].filter((c) => c.skillSpread != null).sort((a, b) => (b.skillSpread ?? 0) - (a.skillSpread ?? 0)).slice(0, 5);
  const consistent = [...ranked].filter((c) => c.winrateStd != null).sort((a, b) => (a.winrateStd ?? 99) - (b.winrateStd ?? 99)).slice(0, 5);
  const longestUnchanged = getChampionChangeRanking(champions)
    .filter((entry) => entry.daysSinceBalanceChange != null)
    .slice(0, 5);
  const adjustments = getMostAdjustedChampions(champions);
  const mostAdjusted = adjustments.slice(0, 5);
  const leastAdjusted = [...adjustments].reverse().slice(0, 5);

  return (
    <div className="home-revamp no-plate">
      {/* Hero.
          WrTrueMeta is positioned as a build platform, not another stats site:
          the tier list is evidence for the builds, not the product. The primary
          call to action is therefore generating a build. While the build tools
          are still held back (BUILD_TOOLS_LIVE), the same promise stays on the
          page but the button points at what is actually open today. */}
      <section className="home-stage home-atlas relative overflow-hidden">
        {/* No hero scrim. A radial ellipse used to sit here to hold the
            headline's contrast against the art; the carousel now brings its
            own glass panel, which does the same job without dimming the
            painting behind it. Removed 2026-09-17. */}
        <Container className="relative py-9 sm:py-14">
          {/* The hero rotates through the features. It used to be one fixed
              pitch for the build generator, so the draft assistant, the counter
              builder and the overlay were invisible to anyone who did not
              scroll. */}
          <HeroCarousel />
          <div className="home-command-search mx-auto mt-4 max-w-6xl rounded-2xl border border-white/[0.07] bg-[#08101d]/70 px-3 py-3 backdrop-blur-xl sm:px-4">
            <HomeSearch champions={champions.map((c) => ({ name: c.name, slug: c.slug, icon: c.icon }))} />
          </div>
          <div className="home-status-strip mx-auto mt-4 flex max-w-6xl flex-wrap items-center gap-2 rounded-2xl border border-white/[0.07] bg-[#08101d]/55 px-4 py-3 backdrop-blur-xl">
            <BuildsGeneratedPill />
            {/* Both rosters are fully collected now, so these read "collected"
                with the date rather than "being collected" -- the pulse dot is
                gone with it, since nothing is in progress to signal. */}
            <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-400/30 bg-emerald-400/10 px-3 py-1 text-xs font-medium text-emerald-300">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              EU win rates · collected {site.collectedOn}
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-accent/30 bg-accent/10 px-3 py-1 text-xs font-medium text-accent">
              <span className="h-1.5 w-1.5 rounded-full bg-accent" />
              NA win rates · collected {naBoard.collectedOn}
            </span>
            {!BUILD_TOOLS_LIVE && (
              <span className="rounded-full border border-gold/30 bg-gold/10 px-3 py-1 text-xs font-medium text-gold">
                Build Studio · launching this month
              </span>
            )}
          </div>
          <p className="mx-auto mt-4 max-w-6xl text-left text-xs text-faint sm:text-sm">
            Every recommendation is grounded in {site.nChampions} champions and{" "}
            {(site.nPlayers + naBoard.nPlayers).toLocaleString()} player records
            across EU and NA.
          </p>

          {/* Scroll cue. The hero fills the first screen, so without this the
              page reads as if it ends here. Anchored to the section below so
              it works as a real control, not just decoration. */}
          <a href="#explore"
            aria-label="Scroll to see more"
            className="group mx-auto mt-7 flex w-fit flex-col items-center gap-1 text-faint transition hover:text-accent">
            <span className="text-[0.7rem] font-medium uppercase tracking-[0.2em]">More below</span>
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor"
              strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden
              className="motion-safe:animate-bounce">
              <path d="M12 5v14M6 13l6 6 6-6" />
            </svg>
          </a>
        </Container>
      </section>

      {/* Flagship slot right under the hero for the products we most want people
          to find. The build tools take it once they launch; until then it
          leads with the new Meta Report. */}
      <Container id="explore" className="scroll-mt-20 py-8 sm:py-10">
        <div className="home-bento-tools grid gap-4 md:grid-cols-[1.2fr_.8fr]">
          {BUILD_TOOLS_LIVE ? (
            <>
              <FlagshipTool
                href="/build?tab=counter"
                badge="v1"
                badgeClass="bg-gold/20 text-gold"
                secondBadge="new"
                secondBadgeClass="bg-emerald-400/20 text-emerald-300"
                title="Build vs Enemy Team"
                desc="Name your champion and the five you are up against, and get the items, runes and purchase order shaped to beat exactly those picks."
                cta="Build against their team"
                accent="text-emerald-300"
                ring="hover:border-emerald-400/40"
              />
              <FlagshipTool
                href="/build"
                badge="v1"
                badgeClass="bg-gold/20 text-gold"
                secondBadge="new"
                secondBadgeClass="bg-emerald-400/20 text-emerald-300"
                title="Build Studio"
                desc="Generate a build for your playstyle, or craft one in the Custom Build Lab with live item, rune and ability stats."
                cta="Open Build Studio"
                accent="text-accent"
                ring="hover:border-accent/40"
              />
            </>
          ) : (
            <>
              <FlagshipTool
                href="/meta"
                badge="new"
                badgeClass="bg-emerald-400/20 text-emerald-300"
                title="Meta Overview"
                desc="The whole meta in one place: tier splits, win rate by class and role, and an interactive win-rate-vs-popularity map of every champion."
                cta="Explore the charts"
                accent="text-emerald-300"
                ring="hover:border-emerald-400/40"
              />
              {/* Badge was "live", which read as a claim about the win rates
                  rather than the feature. It is the EU list, gathered in
                  batches, and there is a separate China one. */}
              <FlagshipTool
                href="/tier-list"
                badge="EU"
                badgeClass="bg-accent/20 text-accent"
                title="Tier List"
                desc="Every champion ranked by the real win rates of its best players, confidence-adjusted so hype and lucky streaks never make the cut."
                cta="View the tier list"
                accent="text-accent"
                ring="hover:border-accent/40"
              />
            </>
          )}
        </div>
      </Container>

      {/* Season and data coverage now read as one compact control deck instead
          of three unrelated rows of stat cards. */}
      <Container className="py-8">
        <div className="home-data-deck grid gap-4 lg:grid-cols-[.85fr_1.65fr]">
          <div className="min-w-0"><SeasonCard /></div>
          <div className="glass-card rounded-[1.6rem] p-5 sm:p-6">
            <SectionHeading title="Inside WrTrueMeta" subtitle="Live coverage, at a glance" />
            <div className={`grid grid-cols-2 gap-3 ${BUILD_TOOLS_LIVE ? "lg:grid-cols-4" : "lg:grid-cols-3"}`}>
              {BUILD_TOOLS_LIVE && (
                <StatCard
                  label="Builds generated"
                  value={<BuildsGeneratedCount />}
                  sub="updated hourly"
                  href="/build"
                  valueClass="text-accent"
                  spark="blue"
                />
              )}
              <StatCard label="Champions tracked" value={champions.length.toLocaleString()} sub="EU + NA profiles" href="/champions" spark="cyan" />
              <StatCard
                label="Players tracked"
                value={(site.nPlayers + naBoard.nPlayers).toLocaleString()}
                sub={`${site.nPlayers.toLocaleString()} EU · ${naBoard.nPlayers.toLocaleString()} NA`}
                href="/leaderboard"
                valueClass="text-gold"
                spark="gold"
              />
              <StatCard label="Items catalogued" value={ITEM_CATALOG_COUNT.toLocaleString()} sub="stats + passives" href="/items" spark="violet" />
            </div>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatCard label="Current meta" value={topMetaClass.class} sub={`${topMetaClass.wr.toFixed(1)}% avg win rate`} href="/meta#classes" spark="violet" />
          <StatCard label="Top pick" value={topPick.name} sub={`${topPick.wr.toFixed(1)}% win rate`} avatarSrc={topPick.icon} valueClass="text-accent" href={`/champions/${topPick.slug}`} spark="cyan" />
          {strongestRole && <StatCard label="Strongest role" value={strongestRole[0]} sub={`${strongestRole[1].wr.toFixed(1)}% top picks`} href="/meta#roles" spark="blue" />}
          {lowest && <StatCard label="Lowest win rate" value={lowest.name} sub={`${lowest.wr.toFixed(1)}% win rate`} avatarSrc={lowest.icon} valueClass="text-bad" href="/win-rates?view=lowest" spark="red" />}
        </div>
      </Container>

      {/* Biggest winners & losers this patch */}
      <Container className="py-2">
        <MoversHighlight />
      </Container>

      {/* Featured champion */}
      <Container className="py-8">
        <SectionHeading title="Meta spotlight" subtitle="The strongest pick, with the chasing pack beside it" href="/tier-list" linkLabel="Full tier list" />
        <div className="grid items-stretch gap-4 lg:grid-cols-[1.45fr_.75fr]">
          <FeaturedChampion c={featured} />
          <Card className="home-rank-card overflow-hidden p-3">
            <div className="px-2 pb-3 pt-1">
              <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-accent">Top meta</p>
              <p className="mt-1 text-sm text-muted">Global · Top-player signal</p>
            </div>
            <div className="space-y-1.5">
              {topMeta.slice(0, 5).map((c, i) => (
                <Link key={c.slug} href={`/champions/${c.slug}`} className="group flex items-center gap-3 rounded-xl border border-transparent px-2.5 py-2 transition hover:border-white/10 hover:bg-white/[0.04]">
                  <span className="w-4 text-center text-xs font-semibold text-faint">{String(i + 1).padStart(2, "0")}</span>
                  <ChampionAvatar champion={c} size={38} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold">{c.name}</p>
                    <p className="text-[0.68rem] text-muted">{c.role} · {c.class}</p>
                  </div>
                  <div className="text-right">
                    <TierChip tier={c.tier} />
                    <p className="mt-1 text-xs font-semibold text-accent">{c.wr.toFixed(1)}%</p>
                  </div>
                </Link>
              ))}
            </div>
          </Card>
        </div>
      </Container>

      <Container className="py-8">
        <SectionHeading title="Top of the leaderboard" subtitle="Highest champion mastery on the server" href="/leaderboard" linkLabel="All leaderboards" />
        <Card className="home-leader-grid grid overflow-hidden sm:grid-cols-2 lg:grid-cols-3">
          {topMastery.map((m, i) => (
            <Link key={`${m.player}-${i}`} href={`/leaderboard?champion=${encodeURIComponent(m.champion)}`} className="group flex items-center gap-3 border-b border-line px-4 py-4 transition hover:bg-white/[0.035] sm:border-r lg:[&:nth-child(3n)]:border-r-0">
              <span className="text-xl font-semibold text-faint">{String(i + 1).padStart(2, "0")}</span>
              <span className="h-11 w-11 shrink-0 overflow-hidden rounded-xl ring-1 ring-white/10">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={m.icon} alt="" width={44} height={44} loading="lazy" className="h-full w-full scale-[1.12] object-cover" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold">{m.player}</p>
                <p className="text-xs text-muted">{m.champion}</p>
              </div>
              <span className="text-xs font-semibold text-accent">{m.score != null ? m.score.toLocaleString() : "-"}</span>
            </Link>
          ))}
        </Card>
      </Container>

      {/* Meta charts */}
      <Container className="py-12">
        <SectionHeading title="Meta at a glance" subtitle="Win rate by class and role" href="/meta" linkLabel="Full meta overview" />
        <div className="grid gap-6 lg:grid-cols-2">
          <BarCard title="Meta by class" subtitle="Avg win rate of each class's top 5 picks" rows={site.metaBreakdown.map((m) => ({ label: m.class, wr: m.wr }))} />
          <BarCard
            title="Win rate by role"
            subtitle="Strength of each role's top meta picks"
            rows={Object.entries(site.roleStrength)
              .sort((a, b) => b[1].wr - a[1].wr)
              .map(([role, s]) => ({ label: role, wr: s.wr }))}
          />
        </div>
      </Container>

      {/* Win-rate insights */}
      <Container className="py-6">
        <SectionHeading title="Win rates" subtitle="Best, worst, and under-the-radar" />
        <div className="grid gap-4 md:grid-cols-3">
          <InsightCard href="/win-rates?view=highest" title="Highest win rate" items={highestWr.map((c) => ({ icon: c.icon, name: c.name, href: `/champions/${c.slug}`, metric: `${c.wr.toFixed(1)}%`, metricClass: "text-accent" }))} />
          <InsightCard href="/win-rates?view=lowest" title="Lowest win rate" items={lowestWr.map((c) => ({ icon: c.icon, name: c.name, href: `/champions/${c.slug}`, metric: `${c.wr.toFixed(1)}%`, metricClass: "text-bad" }))} />
          <InsightCard href="/win-rates?view=off-meta" title="Strong off-meta" subtitle="High WR, lower pick rate" items={offMeta.map((c) => ({ icon: c.icon, name: c.name, href: `/champions/${c.slug}`, metric: `${c.wr.toFixed(1)}%`, metricClass: "text-gold" }))} />
        </div>
      </Container>

      {/* The home page used to run fourteen sections deep, which buried the
          tools that actually differentiate the site. The cross-server data,
          CN/EU meta gap, skill-bracket splits, champion cuts and player
          oddities now live on the meta report, one click away. */}
      <Container className="py-12">
        <div className="glass relative overflow-hidden rounded-2xl px-6 py-8 text-center sm:px-10">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">
            There is a lot more
          </p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">
            The full meta overview
          </h2>
          <p className="mx-auto mt-2 max-w-xl text-muted">
            Cross-server win rates, the China-versus-Europe meta gap, skill-bracket
            splits, rune and item usage from real high-elo builds, and every champion
            cut we track. All of it on one page.
          </p>
          <div className="mt-5 flex flex-wrap items-center justify-center gap-3">
            <Link href="/meta"
              className="inline-flex items-center gap-2 rounded-lg bg-accent px-5 py-2.5 text-sm font-bold text-black transition hover:brightness-110">
              Open the meta overview <span aria-hidden>→</span>
            </Link>
            <Link href="/leaderboard"
              className="inline-flex items-center gap-2 rounded-lg border border-line px-5 py-2.5 text-sm font-semibold transition hover:border-accent/40 hover:text-accent">
              Browse the leaderboards
            </Link>
          </div>
        </div>
      </Container>

    </div>
  );
}

/** Hero proof point: a check mark plus a two- or three-word claim. */
function FlagshipTool({
  href, badge, badgeClass, secondBadge, secondBadgeClass, title, desc, cta, accent, ring,
}: {
  href: string; badge: string; badgeClass: string; secondBadge?: string; secondBadgeClass?: string; title: string; desc: string; cta: string; accent: string; ring: string;
}) {
  return (
    <Link
      href={href}
      className={`group glass glass-hover flex flex-col rounded-2xl border border-line p-6 transition ${ring}`}
    >
      <div className="flex items-center gap-2">
        <h3 className="text-xl font-semibold">{title}</h3>
        <span className={`rounded px-1.5 py-0.5 text-[0.6rem] font-bold uppercase tracking-wide ${badgeClass}`}>{badge}</span>
        {secondBadge && (
          <span className={`rounded px-1.5 py-0.5 text-[0.6rem] font-bold uppercase tracking-wide ${secondBadgeClass}`}>{secondBadge}</span>
        )}
      </div>
      <p className="mt-2 flex-1 text-sm leading-relaxed text-muted">{desc}</p>
      <span className={`mt-4 inline-flex items-center gap-1 text-sm font-semibold ${accent}`}>
        {cta} <span className="transition-transform group-hover:translate-x-0.5">→</span>
      </span>
    </Link>
  );
}

function FeaturedChampion({ c }: { c: Champion }) {
  return (
    <Link href={`/champions/${c.slug}`} className="group relative block min-h-[390px] overflow-hidden rounded-[1.6rem] border border-line">
      <div className="absolute inset-0 bg-cover transition duration-500 group-hover:scale-[1.03]" style={{ backgroundImage: `url(${c.splash})`, backgroundPosition: "72% 24%" }} />
      <div className="absolute inset-0 bg-gradient-to-r from-[#07101d] via-[#07101d]/78 to-[#07101d]/10" />
      <div className="absolute inset-0 bg-gradient-to-t from-[#050a13]/95 via-transparent to-[#0a1422]/20" />
      <div className="relative flex min-h-[390px] flex-col justify-between gap-8 p-6 sm:p-8">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-accent">
            Featured · {tierLabel(c.tier)} tier
          </p>
          <h3 className="display-title mt-3 text-5xl leading-none sm:text-6xl">{c.name}</h3>
          <p className="mt-1 text-muted">
            {c.role} · {c.class} · <span className={c.isHard ? "text-bad" : ""}>{c.difficultyLabel}</span>
          </p>
        </div>
        <div className="max-w-3xl rounded-2xl border border-white/10 bg-[#060c17]/68 p-3 backdrop-blur-xl">
          <div className="grid grid-cols-3 gap-2">
            <div className="rounded-xl bg-white/[0.035] p-3"><Stat label="Win rate" value={`${c.wr.toFixed(1)}%`} className="text-accent" /></div>
            <div className="rounded-xl bg-white/[0.035] p-3"><Stat label="Ceiling" value={c.maxWr != null ? `${c.maxWr.toFixed(1)}%` : "-"} className="text-emerald-300" /></div>
            <div className="rounded-xl bg-white/[0.035] p-3"><Stat label="Median games" value={c.medianGames != null ? c.medianGames.toLocaleString() : "-"} /></div>
          </div>
          {c.bestPlayer && (
            <div className="mt-3 flex items-center justify-between border-t border-white/[0.08] px-2 pt-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted">Best player</p>
              <p className="text-sm font-semibold">
                {c.bestPlayer.player}
                {c.bestPlayer.confidence_wr != null && (
                  <span className="ml-2 text-sm font-normal text-muted">{c.bestPlayer.confidence_wr.toFixed(1)}% adj.</span>
                )}
              </p>
            </div>
          )}
        </div>
      </div>
    </Link>
  );
}

function Stat({ label, value, className = "" }: { label: string; value: string; className?: string }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-muted">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${className}`}>{value}</p>
    </div>
  );
}

function StatCard({ label, value, sub, avatarSrc, valueClass = "", href, spark = "blue" }: { label: string; value: React.ReactNode; sub: string; avatarSrc?: string; valueClass?: string; href?: string; spark?: "blue" | "cyan" | "gold" | "violet" | "red" }) {
  const inner = (
    <Card className={`home-signal-card home-signal-${spark} flex h-full min-h-[8.75rem] flex-col justify-between p-5 glass-hover`}>
      <div className="flex items-center justify-between gap-3">
        <p className="text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-muted">{label}</p>
        <MiniSpark tone={spark} />
      </div>
      <div className="mt-3 flex items-center gap-2.5">
        {avatarSrc && (
          // eslint-disable-next-line @next/next/no-img-element
          <span className="h-8 w-8 shrink-0 overflow-hidden rounded-full ring-1 ring-white/10">
            <img src={avatarSrc} alt="" width={32} height={32} loading="lazy" className="h-full w-full scale-[1.12] object-cover" />
          </span>
        )}
        <span className={`truncate text-xl font-semibold ${valueClass}`}>{value}</span>
      </div>
      <p className="mt-1 text-sm text-muted">{sub}</p>
    </Card>
  );
  return href ? <Link href={href}>{inner}</Link> : inner;
}

function MiniSpark({ tone }: { tone: "blue" | "cyan" | "gold" | "violet" | "red" }) {
  return (
    <svg viewBox="0 0 76 24" className={`mini-spark mini-spark-${tone} h-6 w-[4.75rem]`} aria-hidden>
      <path d="M2 20 C10 18 12 12 20 14 S32 20 39 11 S51 14 58 7 S68 7 74 3" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function BarCard({ title, subtitle, rows }: { title: string; subtitle?: string; rows: { label: string; wr: number }[] }) {
  const max = Math.max(...rows.map((r) => r.wr));
  const min = Math.min(...rows.map((r) => r.wr));
  const span = max - min || 1;
  return (
    <Card className="home-chart-card overflow-hidden p-5 sm:p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[0.65rem] font-semibold uppercase tracking-[0.16em] text-accent">Live meta signal</p>
          <h2 className="mt-1 text-lg font-semibold">{title}</h2>
          {subtitle && <p className="mt-0.5 text-sm text-muted">{subtitle}</p>}
        </div>
        <div className="rounded-xl border border-accent/20 bg-accent/10 px-3 py-2 text-right">
          <p className="text-[0.58rem] font-semibold uppercase tracking-[0.14em] text-muted">Peak</p>
          <p className="text-lg font-semibold text-accent">{max.toFixed(1)}%</p>
        </div>
      </div>
      <div className="home-chart-grid mt-6 flex flex-col gap-3.5">
        {rows.map((r) => {
          const lead = r.wr === max;
          const pct = ((r.wr - min) / span) * 100;
          return (
            <div key={r.label} className="flex items-center gap-3">
              <span className="w-20 shrink-0 text-sm font-medium">{r.label}</span>
              <div className="home-chart-track relative h-2.5 flex-1 overflow-visible rounded-full bg-white/[0.055]">
                <div className={`h-full rounded-full ${lead ? "home-chart-lead" : "home-chart-rest"}`} style={{ width: `${Math.max(8, pct)}%` }} />
                <span className={`absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-[#0a1220] ${lead ? "bg-accent shadow-[0_0_14px_rgba(114,167,255,.75)]" : "bg-[#7f91aa]"}`} style={{ left: `${Math.max(8, pct)}%` }} />
              </div>
              <span className={`w-14 text-right text-sm font-semibold ${lead ? "text-accent" : "text-muted"}`}>{r.wr.toFixed(1)}%</span>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
