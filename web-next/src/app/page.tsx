import type { Metadata } from "next";
import Link from "next/link";
import { site, getChampions, tierLabel, type Champion, regionBoard } from "@/lib/data";
import { BUILD_TOOLS_LIVE } from "@/lib/flags";
import { getCnChampions, getGlobalChampions } from "@/lib/cn";
import { risingPicks, overratedInEu } from "@/lib/gap";
import { climbingPicks, stomperPicks } from "@/lib/skew";
import { Container, TierChip, ChampionAvatar, SectionHeading, Card } from "@/components/ui";
import { HomeSearch } from "@/components/home-search";
import { InsightCard } from "@/components/insight-card";
import { MoversHighlight } from "@/components/movers-highlight";
import { Roadmap } from "@/components/roadmap";
import { BuildsGeneratedCount, BuildsGeneratedPill } from "@/components/builds-counter";
import { getChampionChangeRanking, getMostAdjustedChampions } from "@/lib/champion-change-ranking";

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

  const featured = champions[0];
  const topPick = champions[0];
  const lowest = [...ranked].sort((a, b) => a.wr - b.wr)[0];
  const topMetaClass = site.metaBreakdown[0];
  const strongestRole = Object.entries(site.roleStrength)
    .filter(([, s]) => !s.lowConfidence)
    .sort((a, b) => b[1].wr - a[1].wr)[0];

  const topMeta = champions.slice(0, 6);
  const topMastery = site.topMastery.slice(0, 6);
  const highestWr = champions.slice(0, 5);
  const lowestWr = [...ranked].sort((a, b) => a.wr - b.wr).slice(0, 5);
  const offMeta = site.offMetaSlugs.map((s) => bySlug.get(s)).filter(Boolean).slice(0, 5) as Champion[];

  // Sort before slicing. Without it this took the first five OTP-flagged
  // champions in whatever order the source list happened to be in, so the card
  // showed a ranking that did not match the OTP score printed beside each name
  // -- and did not match /otp-champions, which has always sorted.
  const bestOtp = champions
    .filter((c) => c.isOtp && c.otpScore != null)
    .sort((left, right) => (right.otpScore ?? 0) - (left.otpScore ?? 0))
    .slice(0, 5);
  const skillCeiling = [...ranked].filter((c) => c.skillSpread != null).sort((a, b) => (b.skillSpread ?? 0) - (a.skillSpread ?? 0)).slice(0, 5);
  const consistent = [...ranked].filter((c) => c.winrateStd != null).sort((a, b) => (a.winrateStd ?? 99) - (b.winrateStd ?? 99)).slice(0, 5);
  const longestUnchanged = getChampionChangeRanking(champions)
    .filter((entry) => entry.daysSinceBalanceChange != null)
    .slice(0, 5);
  const adjustments = getMostAdjustedChampions(champions);
  const mostAdjusted = adjustments.slice(0, 5);
  const leastAdjusted = [...adjustments].reverse().slice(0, 5);

  return (
    <>
      {/* Hero.
          WrTrueMeta is positioned as a build platform, not another stats site:
          the tier list is evidence for the builds, not the product. The primary
          call to action is therefore generating a build. While the build tools
          are still held back (BUILD_TOOLS_LIVE), the same promise stays on the
          page but the button points at what is actually open today. */}
      <section className="relative overflow-hidden border-b border-line">
        {/* Reading scrim, hero only.
            The hero is the one block of text that sits directly on the
            background art rather than on a glass panel, and the art is now
            unblurred: over its bright regions the smallest line drops to about
            1.7:1, which is not readable. A soft ellipse behind the text fixes
            exactly that, and fades out well before the edges so the sharp art
            still frames the page. Darkening the global overlay instead would
            have dimmed the whole site to solve one paragraph. */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "radial-gradient(78% 96% at 50% 50%, rgba(7,10,18,0.66) 0%, rgba(7,10,18,0.55) 52%, rgba(7,10,18,0.3) 78%, transparent 96%)",
          }}
        />
        <Container className="relative py-20 text-center sm:py-28">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">
            Builds reasoned, not repeated
          </p>
          <h1 className="mx-auto mt-5 max-w-3xl text-4xl font-semibold leading-[1.1] tracking-tight sm:text-6xl">
            Build for <span className="text-accent">this game</span> - not every game.
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-muted">
            Stop copying the same build every match. Generate a personalized Wild Rift build for your
            champion, role, playstyle, and enemy team backed by current patch data and real
            top-player win rates.
          </p>
          <div className="mt-6 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-sm font-medium text-text">
            {/* "AI generated" alone invites the obvious dismissal -- that
                anyone could paste the champion into a chatbot and get this.
                The differentiator is that the model only ever sees OUR
                current-patch data and every build is rule-checked before anyone
                sees it. The claims say that. */}
            <Claim>AI-powered reasoning</Claim>
            <Claim>Rule-checked</Claim>
            <Claim>Explained item by item</Claim>
          </div>
          <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
            {BUILD_TOOLS_LIVE ? (
              <>
                <Link href="/build?tab=generate" className="rounded-xl bg-accent px-6 py-3 font-semibold text-[#07121f] transition hover:brightness-110">
                  Generate my build
                </Link>
                <Link href="/build?tab=counter" className="glass glass-hover rounded-xl px-6 py-3 font-semibold text-text">
                  Build vs enemy team
                </Link>
              </>
            ) : (
              <>
                <Link href="/tier-list" className="rounded-xl bg-accent px-6 py-3 font-semibold text-[#07121f] transition hover:brightness-110">
                  See what actually wins
                </Link>
                <Link href="/meta" className="glass glass-hover rounded-xl px-6 py-3 font-semibold text-text">
                  Read the meta overview
                </Link>
              </>
            )}
          </div>
          <HomeSearch champions={champions.map((c) => ({ name: c.name, slug: c.slug, icon: c.icon }))} />
          <div className="mt-7 flex flex-wrap items-center justify-center gap-2">
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
          <p className="mt-6 text-sm text-faint">
            Every recommendation is grounded in {site.nChampions} champions and{" "}
            {(site.nPlayers + naBoard.nPlayers).toLocaleString()} player records
            across EU and NA.
          </p>

          {/* Scroll cue. The hero fills the first screen, so without this the
              page reads as if it ends here. Anchored to the section below so
              it works as a real control, not just decoration. */}
          <a href="#explore"
            aria-label="Scroll to see more"
            className="group mx-auto mt-10 flex w-fit flex-col items-center gap-1 text-faint transition hover:text-accent">
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
      <Container id="explore" className="scroll-mt-20 py-10">
        <div className="grid gap-4 md:grid-cols-2">
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
                desc="Every champion ranked by the real win rates of its 50 best players, confidence-adjusted so hype and lucky streaks never make the cut."
                cta="View the tier list"
                accent="text-accent"
                ring="hover:border-accent/40"
              />
            </>
          )}
        </div>
      </Container>

      {/* Roadmap + countdown */}
      <Container className="py-6">
        <Roadmap />
      </Container>

      {/* Transparent coverage counters: these describe the current generated
          catalogue, plus one genuinely live figure (builds players have
          generated), which updates roughly hourly rather than on every view. */}
      <Container className="py-6">
        <SectionHeading title="Inside WrTrueMeta" subtitle="What the current site data and build catalogue cover" />
        <div className={`grid grid-cols-2 gap-3 ${BUILD_TOOLS_LIVE ? "lg:grid-cols-4" : "lg:grid-cols-3"}`}>
          {/* No invented placeholder on the count. This card was hidden while
              the tools were gated, so the old "171" fallback was never seen;
              now that it ships, a made-up figure would sit on screen under the
              label "by players" until the real one loads. */}
          {BUILD_TOOLS_LIVE && (
            <StatCard
              label="Builds generated"
              value={<BuildsGeneratedCount />}
              sub="by players, updated hourly"
              href="/build"
              valueClass="text-accent"
            />
          )}
          <StatCard label="Champions tracked" value={champions.length.toLocaleString()} sub="EU and NA performance profiles" href="/champions" />
          {/* The headline of the whole project: every one of these is a real
              player's record read off a leaderboard, not a modelled estimate. */}
          <StatCard
            label="Players tracked"
            value={(site.nPlayers + naBoard.nPlayers).toLocaleString()}
            sub={`${site.nPlayers.toLocaleString()} EU · ${naBoard.nPlayers.toLocaleString()} NA`}
            href="/leaderboard"
            valueClass="text-gold"
          />
          <StatCard label="Items catalogued" value="117" sub="stats, passives, and costs" href="/items" />
        </div>
      </Container>

      {/* Stat cards */}
      <Container className="py-12">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatCard label="Current meta" value={topMetaClass.class} sub={`${topMetaClass.wr.toFixed(1)}% avg win rate`} href="/meta#classes" />
          <StatCard label="Top pick" value={topPick.name} sub={`${topPick.wr.toFixed(1)}% win rate`} avatarSrc={topPick.icon} valueClass="text-accent" href={`/champions/${topPick.slug}`} />
          {strongestRole && <StatCard label="Strongest role" value={strongestRole[0]} sub={`${strongestRole[1].wr.toFixed(1)}% top picks`} href="/meta#roles" />}
          {lowest && <StatCard label="Lowest win rate" value={lowest.name} sub={`${lowest.wr.toFixed(1)}% win rate`} avatarSrc={lowest.icon} valueClass="text-bad" href="/win-rates?view=lowest" />}
        </div>
      </Container>

      {/* Biggest winners & losers this patch */}
      <Container className="py-2">
        <MoversHighlight />
      </Container>

      {/* Featured champion */}
      <Container className="py-6">
        <SectionHeading title="Featured champion" subtitle="The strongest pick in the meta right now" />
        <FeaturedChampion c={featured} />
      </Container>

      {/* Top meta + top of leaderboard (both lists) */}
      <Container className="py-6">
        <div className="grid items-start gap-6 lg:grid-cols-2">
          <div>
            <SectionHeading title="Top meta champions" href="/tier-list" linkLabel="Full tier list" />
            <Card className="divide-y divide-line overflow-hidden">
              {topMeta.map((c, i) => (
                <Link key={c.slug} href={`/champions/${c.slug}`} className="flex items-center gap-4 px-4 py-3 transition hover:bg-white/[0.03]">
                  <span className="w-5 text-center text-sm font-semibold text-faint">{i + 1}</span>
                  <ChampionAvatar champion={c} size={40} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{c.name}</p>
                    <p className="text-xs text-muted">{c.role} · {c.class}</p>
                  </div>
                  <TierChip tier={c.tier} />
                  <span className="w-16 text-right font-semibold text-accent">{c.wr.toFixed(1)}%</span>
                </Link>
              ))}
            </Card>
          </div>
          <div>
            <SectionHeading title="Top of the leaderboard" subtitle="Highest champion mastery on the server" href="/leaderboard" linkLabel="All leaderboards" />
            <Card className="divide-y divide-line overflow-hidden">
              {topMastery.map((m, i) => (
                <Link key={`${m.player}-${i}`} href={`/leaderboard?champion=${encodeURIComponent(m.champion)}`} className="flex items-center gap-4 px-4 py-3 transition hover:bg-white/[0.03]">
                  <span className="w-5 text-center text-sm font-semibold text-faint">{i + 1}</span>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <span className="h-9 w-9 shrink-0 overflow-hidden rounded-full ring-1 ring-white/10">
                    <img src={m.icon} alt="" width={36} height={36} loading="lazy" className="h-full w-full scale-[1.12] object-cover" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{m.player}</p>
                    <p className="text-xs text-muted">{m.champion}</p>
                  </div>
                  <span className="text-right text-sm font-semibold text-muted">
                    {m.score != null ? m.score.toLocaleString() : "-"}
                  </span>
                </Link>
              ))}
            </Card>
          </div>
        </div>
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

    </>
  );
}

/** Hero proof point: a check mark plus a two- or three-word claim. */
function Claim({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6"
        strokeLinecap="round" strokeLinejoin="round" aria-hidden className="text-accent">
        <path d="m5 13 4 4L19 7" />
      </svg>
      {children}
    </span>
  );
}

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
    <Link href={`/champions/${c.slug}`} className="group relative block min-h-[260px] overflow-hidden rounded-2xl border border-line">
      <div className="absolute inset-0 bg-cover transition duration-500 group-hover:scale-[1.03]" style={{ backgroundImage: `url(${c.splash})`, backgroundPosition: "72% 24%" }} />
      <div className="absolute inset-0 bg-gradient-to-r from-bg via-bg/85 to-bg/30" />
      <div className="absolute inset-0 bg-gradient-to-t from-bg/95 to-transparent" />
      <div className="relative flex h-full flex-col justify-between gap-6 p-6 sm:p-8">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-accent">
            Featured · {tierLabel(c.tier)} tier
          </p>
          <h3 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">{c.name}</h3>
          <p className="mt-1 text-muted">
            {c.role} · {c.class} · <span className={c.isHard ? "text-bad" : ""}>{c.difficultyLabel}</span>
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-x-8 gap-y-4">
          <Stat label="Win rate" value={`${c.wr.toFixed(1)}%`} className="text-accent" />
          <Stat label="Ceiling" value={c.maxWr != null ? `${c.maxWr.toFixed(1)}%` : "-"} className="text-gold" />
          <Stat label="Median games" value={c.medianGames != null ? c.medianGames.toLocaleString() : "-"} />
          {c.bestPlayer && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-muted">Best player</p>
              <p className="mt-1 text-lg font-semibold">
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

function StatCard({ label, value, sub, avatarSrc, valueClass = "", href }: { label: string; value: React.ReactNode; sub: string; avatarSrc?: string; valueClass?: string; href?: string }) {
  const inner = (
    <Card className="flex h-full flex-col justify-between p-5 glass-hover">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted">{label}</p>
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

function BarCard({ title, subtitle, rows }: { title: string; subtitle?: string; rows: { label: string; wr: number }[] }) {
  const max = Math.max(...rows.map((r) => r.wr));
  const min = Math.min(...rows.map((r) => r.wr));
  const span = max - min || 1;
  return (
    <Card className="p-5">
      <h2 className="text-lg font-semibold">{title}</h2>
      {subtitle && <p className="mb-4 mt-0.5 text-sm text-muted">{subtitle}</p>}
      <div className="mt-2 flex flex-col gap-3">
        {rows.map((r) => {
          const lead = r.wr === max;
          const pct = ((r.wr - min) / span) * 100;
          return (
            <div key={r.label} className="flex items-center gap-3">
              <span className="w-20 shrink-0 text-sm font-medium">{r.label}</span>
              <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
                <div className="h-full rounded-full" style={{ width: `${Math.max(6, pct)}%`, background: lead ? "var(--color-accent)" : "rgba(255,255,255,0.28)" }} />
              </div>
              <span className={`w-14 text-right text-sm font-semibold ${lead ? "text-accent" : "text-muted"}`}>{r.wr.toFixed(1)}%</span>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
