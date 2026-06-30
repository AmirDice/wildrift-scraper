import Link from "next/link";
import { site, getChampions, type Champion } from "@/lib/data";
import { Container, TierChip, ChampionAvatar, SectionHeading, Card } from "@/components/ui";
import { HomeSearch } from "@/components/home-search";
import { SeasonCard } from "@/components/season-card";

export default function HomePage() {
  const champions = getChampions();
  const bySlug = new Map(champions.map((c) => [c.slug, c]));
  const ranked = champions.filter((c) => (c.nPlayers ?? 0) >= 20);

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

  const bestOtp = champions.filter((c) => c.isOtp).slice(0, 5);
  const skillCeiling = [...ranked].filter((c) => c.skillSpread != null).sort((a, b) => (b.skillSpread ?? 0) - (a.skillSpread ?? 0)).slice(0, 5);
  const consistent = [...ranked].filter((c) => c.winrateStd != null).sort((a, b) => (a.winrateStd ?? 99) - (b.winrateStd ?? 99)).slice(0, 5);

  return (
    <>
      {/* Hero */}
      <section className="relative overflow-hidden border-b border-line">
        <Container className="relative py-20 text-center sm:py-28">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">
            Real EU data · Top 50 players per champion{site.collectedOn ? ` · ${site.collectedOn}` : ""}
          </p>
          <h1 className="mx-auto mt-5 max-w-3xl text-4xl font-semibold leading-[1.1] tracking-tight sm:text-6xl">
            See what <span className="text-accent">actually wins</span>
            <br className="hidden sm:block" /> in Wild Rift.
          </h1>
          <p className="mx-auto mt-6 max-w-xl text-lg leading-relaxed text-muted">
            We rank every champion by the real win rates of its 50 best players —
            confidence-adjusted, so hype and lucky streaks never make the cut. Just who&rsquo;s
            genuinely carrying the patch.
          </p>
          <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
            <Link href="/tier-list" className="rounded-xl bg-accent px-6 py-3 font-semibold text-[#07121f] transition hover:brightness-110">
              View the tier list
            </Link>
            <Link href="/champions" className="glass glass-hover rounded-xl px-6 py-3 font-semibold text-text">
              Browse champions
            </Link>
          </div>
          <HomeSearch champions={champions.map((c) => ({ name: c.name, slug: c.slug, icon: c.icon }))} />
          <div className="mt-7 flex flex-wrap items-center justify-center gap-2">
            <span className="rounded-full border border-accent/30 bg-accent/10 px-3 py-1 text-xs font-medium text-accent">
              NA win rates — coming soon
            </span>
            <span className="rounded-full border border-gold/30 bg-gold/10 px-3 py-1 text-xs font-medium text-gold">
              Expanding to top 200 players next update
            </span>
          </div>
          <p className="mt-6 text-sm text-faint">
            {site.nChampions} champions · {site.nPlayers.toLocaleString()} player records tracked
          </p>
        </Container>
      </section>

      {/* Stat cards */}
      <Container className="py-12">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatCard label="Current meta" value={topMetaClass.class} sub={`${topMetaClass.wr.toFixed(1)}% avg win rate`} />
          <StatCard label="Top pick" value={topPick.name} sub={`${topPick.wr.toFixed(1)}% win rate`} avatarSrc={topPick.icon} valueClass="text-accent" href={`/champions/${topPick.slug}`} />
          {strongestRole && <StatCard label="Strongest role" value={strongestRole[0]} sub={`${strongestRole[1].wr.toFixed(1)}% top picks`} />}
          {lowest && <StatCard label="Lowest win rate" value={lowest.name} sub={`${lowest.wr.toFixed(1)}% win rate`} avatarSrc={lowest.icon} valueClass="text-bad" href={`/champions/${lowest.slug}`} />}
        </div>
      </Container>

      {/* Season countdown */}
      <Container className="py-6">
        <SeasonCard />
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
                  <img src={m.icon} alt="" width={36} height={36} loading="lazy" className="h-9 w-9 rounded-full ring-1 ring-white/10" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{m.player}</p>
                    <p className="text-xs text-muted">{m.champion}</p>
                  </div>
                  <span className="text-right text-sm font-semibold text-muted">
                    {m.score != null ? m.score.toLocaleString() : "—"}
                  </span>
                </Link>
              ))}
            </Card>
          </div>
        </div>
      </Container>

      {/* Meta charts */}
      <Container className="py-12">
        <div className="grid gap-6 lg:grid-cols-2">
          <BarCard title="Meta by class" subtitle="Avg win rate of each class's top 5 picks" rows={site.metaBreakdown.map((m) => ({ label: m.class, wr: m.wr }))} />
          <BarCard title="Win rate by difficulty" subtitle="Does mechanical difficulty actually pay off?" rows={site.winrateByDifficulty.map((d) => ({ label: d.difficulty, wr: d.wr }))} />
        </div>
      </Container>

      {/* Win-rate insights */}
      <Container className="py-6">
        <SectionHeading title="Win rates" subtitle="Best, worst, and under-the-radar" />
        <div className="grid gap-4 md:grid-cols-3">
          <InsightCard title="Highest win rate" items={highestWr.map((c) => ({ icon: c.icon, name: c.name, href: `/champions/${c.slug}`, metric: `${c.wr.toFixed(1)}%`, metricClass: "text-accent" }))} />
          <InsightCard title="Lowest win rate" items={lowestWr.map((c) => ({ icon: c.icon, name: c.name, href: `/champions/${c.slug}`, metric: `${c.wr.toFixed(1)}%`, metricClass: "text-bad" }))} />
          <InsightCard title="Strong off-meta" subtitle="High WR, lower pick rate" items={offMeta.map((c) => ({ icon: c.icon, name: c.name, href: `/champions/${c.slug}`, metric: `${c.wr.toFixed(1)}%`, metricClass: "text-gold" }))} />
        </div>
      </Container>

      {/* Champion insights */}
      <Container className="py-6">
        <SectionHeading title="Champion insights" subtitle="Cut the data a few different ways" />
        <div className="grid gap-4 md:grid-cols-3">
          <InsightCard title="Best OTP champions" items={bestOtp.map((c) => ({ icon: c.icon, name: c.name, href: `/champions/${c.slug}`, metric: `${c.wr.toFixed(1)}%`, metricClass: "text-gold" }))} />
          <InsightCard title="Highest skill ceiling" items={skillCeiling.map((c) => ({ icon: c.icon, name: c.name, href: `/champions/${c.slug}`, metric: `+${(c.skillSpread ?? 0).toFixed(1)}`, metricClass: "text-accent" }))} />
          <InsightCard title="Most consistent" items={consistent.map((c) => ({ icon: c.icon, name: c.name, href: `/champions/${c.slug}`, metric: `±${(c.winrateStd ?? 0).toFixed(1)}`, metricClass: "text-muted" }))} />
        </div>
      </Container>

      {/* Players */}
      <Container className="py-12">
        <div className="grid gap-4 md:grid-cols-2">
          <InsightCard title="Multi-champion mains" subtitle="Top 50 on three or more champions" items={site.multiChampionMains.slice(0, 6).map((m) => ({ icon: m.firstChampionIcon ?? undefined, name: m.player, sub: `${m.nChampions} champs · best #${m.bestRank}`, metric: m.avgWr != null ? `${m.avgWr.toFixed(0)}%` : "—", metricClass: "text-muted" }))} />
          <InsightCard title="Funniest names" subtitle="Spotted in the top 50, lightly cleaned" items={site.funnyNames.slice(0, 6).map((f) => ({ icon: f.icon, name: f.player }))} />
        </div>
      </Container>
    </>
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
            Featured · {c.tier} tier
          </p>
          <h3 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">{c.name}</h3>
          <p className="mt-1 text-muted">
            {c.role} · {c.class} · <span className={c.isHard ? "text-bad" : ""}>{c.difficultyLabel}</span>
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-x-8 gap-y-4">
          <Stat label="Win rate" value={`${c.wr.toFixed(1)}%`} className="text-accent" />
          <Stat label="Ceiling" value={c.maxWr != null ? `${c.maxWr.toFixed(1)}%` : "—"} className="text-gold" />
          <Stat label="Median games" value={c.medianGames != null ? c.medianGames.toLocaleString() : "—"} />
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

function StatCard({ label, value, sub, avatarSrc, valueClass = "", href }: { label: string; value: string; sub: string; avatarSrc?: string; valueClass?: string; href?: string }) {
  const inner = (
    <Card className="flex h-full flex-col justify-between p-5 glass-hover">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted">{label}</p>
      <div className="mt-3 flex items-center gap-2.5">
        {avatarSrc && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={avatarSrc} alt="" width={32} height={32} loading="lazy" className="h-8 w-8 rounded-full ring-1 ring-white/10" />
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

type InsightItem = { icon?: string; name: string; sub?: string; metric?: string; metricClass?: string; href?: string };

function InsightCard({ title, subtitle, items }: { title: string; subtitle?: string; items: InsightItem[] }) {
  return (
    <Card className="p-5">
      <h3 className="font-semibold">{title}</h3>
      {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
      <div className="mt-3 flex flex-col">
        {items.map((it, i) => {
          const row = (
            <div className="flex items-center gap-3 py-2">
              {it.icon ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={it.icon} alt="" width={28} height={28} loading="lazy" className="h-7 w-7 rounded-full ring-1 ring-white/10" />
              ) : (
                <span className="h-7 w-7 shrink-0 rounded-full bg-white/[0.06]" />
              )}
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{it.name}</p>
                {it.sub && <p className="truncate text-xs text-muted">{it.sub}</p>}
              </div>
              {it.metric && <span className={`text-sm font-semibold ${it.metricClass ?? "text-text"}`}>{it.metric}</span>}
            </div>
          );
          return (
            <div key={i} className={i > 0 ? "border-t border-line/60" : ""}>
              {it.href ? <Link href={it.href} className="block transition hover:opacity-80">{row}</Link> : row}
            </div>
          );
        })}
      </div>
    </Card>
  );
}
