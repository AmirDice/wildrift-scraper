import { site, getChampions, type Champion } from "@/lib/data";
import { getCnChampions, getGlobalChampions } from "@/lib/cn";
import { risingPicks, overratedInEu } from "@/lib/gap";
import { climbingPicks, stomperPicks } from "@/lib/skew";
import { Container, SectionHeading } from "@/components/ui";
import { InsightCard } from "@/components/insight-card";
import { getChampionChangeRanking, getMostAdjustedChampions } from "@/lib/champion-change-ranking";

/**
 * The deeper sections that used to run down the home page: cross-server data, the
 * CN/EU meta gap, skill-bracket splits, champion cuts and player oddities.
 *
 * They were pushed off the home page because it had grown to fourteen
 * sections and buried the tools that actually differentiate the site. They
 * live here on the meta report, which is now the "everything" page, and the
 * home page links to it.
 */
export function DeepDiveSections() {
  const champions = getChampions();
  const byName = new Map(champions.map((c) => [c.name, c]));
  const ranked = champions.filter((c) => (c.nPlayers ?? 0) >= 20);

  const globalChamps = getGlobalChampions();
  const globalBest = globalChamps.slice(0, 5);
  const globalWorst = [...globalChamps].slice(-5).reverse();

  const legendary = getCnChampions("4").filter((c) => c.cnPickRate >= 0.5);
  const legendaryBest = legendary.slice(0, 5);
  const legendaryWorst = [...legendary].sort((a, b) => a.wr - b.wr).slice(0, 5);

  const rising = risingPicks(5);
  const overrated = overratedInEu(5);
  const climbing = climbingPicks(5);
  const stompers = stomperPicks(5);

  // Ranked by WIN RATE, not by OTP score. The two answer different questions
  // and this card asks the second one: the score says how concentrated a
  // champion's board is around specialists, which is a fact about the player
  // base, while a reader looking at "best OTP champions" is asking which one
  // is worth committing to. Sorting by the score put the most one-tricked
  // champion on top whether or not one-tricking it wins games.
  const bestOtp = champions
    .filter((c) => c.isOtp && Number.isFinite(c.wr))
    .sort((left, right) => right.wr - left.wr)
    .slice(0, 5);
  const skillCeiling = [...ranked].filter((c) => c.skillSpread != null)
    .sort((a, b) => (b.skillSpread ?? 0) - (a.skillSpread ?? 0)).slice(0, 5);
  const consistent = [...ranked].filter((c) => c.winrateStd != null)
    .sort((a, b) => (a.winrateStd ?? 99) - (b.winrateStd ?? 99)).slice(0, 5);
  const longestUnchanged = getChampionChangeRanking(champions)
    .filter((entry) => entry.daysSinceBalanceChange != null).slice(0, 5);
  const adjustments = getMostAdjustedChampions(champions);
  const mostAdjusted = adjustments.slice(0, 5);
  const leastAdjusted = [...adjustments].reverse().slice(0, 5);

  return (
    <>
      {/* China Legendary solo queue */}
      <Container className="py-6">
        <SectionHeading
          title="CN Legendary solo queue"
          subtitle="The best and worst performers in China's separate solo-queue dataset"
          href="/tier-list/china?bracket=4"
          linkLabel="Open CN Legendary tier list"
        />
        <div className="grid gap-4 md:grid-cols-2 [&>*]:min-w-0">
          <InsightCard
            title="Best solo-queue champions"
            subtitle="CN · Legendary · minimum 0.5% pick rate"
            href="/tier-list/china?bracket=4"
            items={legendaryBest.map((c) => ({
              icon: c.icon,
              name: c.name,
              sub: `${c.role} · ${c.cnPickRate.toFixed(1)}% pick`,
              href: `/champions/${c.slug}`,
              metric: `${c.wr.toFixed(1)}%`,
              metricClass: "text-emerald-300",
            }))}
          />
          <InsightCard
            title="Worst solo-queue champions"
            subtitle="CN · Legendary · minimum 0.5% pick rate"
            href="/tier-list/china?bracket=4"
            items={legendaryWorst.map((c) => ({
              icon: c.icon,
              name: c.name,
              sub: `${c.role} · ${c.cnPickRate.toFixed(1)}% pick`,
              href: `/champions/${c.slug}`,
              metric: `${c.wr.toFixed(1)}%`,
              metricClass: "text-rose-300",
            }))}
          />
        </div>
      </Container>

      {/* Across all servers */}
      <Container className="py-6">
        <SectionHeading
          title="Across all servers"
          subtitle="Combined EU + NA · who's genuinely strong on both western servers"
          href="/global"
          linkLabel="Cross-server comparison"
        />
        <div className="grid gap-4 md:grid-cols-2 [&>*]:min-w-0">
          <InsightCard
            title="Strongest globally"
            subtitle="Highest combined EU + NA win rate"
            href="/tier-list"
            items={globalBest.map((c) => ({
              icon: c.icon,
              name: c.name,
              sub: c.role,
              href: `/champions/${c.slug}`,
              metric: `${c.wr.toFixed(1)}%`,
              metricClass: "text-accent",
            }))}
          />
          <InsightCard
            title="Weakest globally"
            subtitle="Lowest combined EU + NA win rate"
            href="/tier-list"
            items={globalWorst.map((c) => ({
              icon: c.icon,
              name: c.name,
              sub: c.role,
              href: `/champions/${c.slug}`,
              metric: `${c.wr.toFixed(1)}%`,
              metricClass: "text-bad",
            }))}
          />
        </div>
      </Container>

      {/* The meta gap: CN top elo vs EU */}
      <Container className="py-6">
        <SectionHeading
          title="The meta gap"
          subtitle="Where China's Challenger sample disagrees with EU, often a patch ahead"
          href="/rising"
          linkLabel="Full meta gap"
        />
        <div className="grid gap-4 md:grid-cols-2 [&>*]:min-w-0">
          <InsightCard
            title="Rising in China"
            subtitle="Rated far higher in CN top elo · learn early"
            href="/rising"
            items={rising.map((g) => ({
              icon: g.champion.icon,
              name: g.champion.name,
              sub: `${g.champion.role} · CN ${g.cnWr.toFixed(1)}% vs EU ${g.euWr.toFixed(1)}%`,
              href: `/champions/${g.champion.slug}`,
              metric: `+${g.gap.toFixed(1)}`,
              metricClass: "text-emerald-300",
            }))}
          />
          <InsightCard
            title="Overrated in EU"
            subtitle="EU rates them above China's best players"
            href="/rising"
            items={overrated.map((g) => ({
              icon: g.champion.icon,
              name: g.champion.name,
              sub: `${g.champion.role} · EU ${g.euWr.toFixed(1)}% vs CN ${g.cnWr.toFixed(1)}%`,
              href: `/champions/${g.champion.slug}`,
              metric: `−${Math.abs(g.gap).toFixed(1)}`,
              metricClass: "text-rose-300",
            }))}
          />
        </div>
      </Container>

      {/* By rank: CN skill brackets */}
      <Container className="py-6">
        <SectionHeading
          title="By skill bracket"
          subtitle="How champions move from China's cumulative Diamond+ sample to Challenger"
          href="/ranks"
          linkLabel="Explore skill brackets"
        />
        <div className="grid gap-4 md:grid-cols-2 [&>*]:min-w-0">
          <InsightCard
            title="Scales with elo"
            subtitle="High-skill specialists · better the higher you climb"
            href="/ranks"
            items={climbing.map((s) => ({
              icon: s.champion.icon,
              name: s.champion.name,
              sub: `${s.champion.role} · ${s.low.toFixed(1)}% → ${s.high.toFixed(1)}%`,
              href: `/champions/${s.champion.slug}`,
              metric: `+${s.skew.toFixed(1)}`,
              metricClass: "text-emerald-300",
            }))}
          />
          <InsightCard
            title="Low-elo stompers"
            subtitle="Strong to climb with, fall off at the top"
            href="/ranks"
            items={stompers.map((s) => ({
              icon: s.champion.icon,
              name: s.champion.name,
              sub: `${s.champion.role} · ${s.low.toFixed(1)}% → ${s.high.toFixed(1)}%`,
              href: `/champions/${s.champion.slug}`,
              metric: `−${Math.abs(s.skew).toFixed(1)}`,
              metricClass: "text-rose-300",
            }))}
          />
        </div>
      </Container>

      {/* Champion insights */}
      <Container className="py-6">
        <SectionHeading title="Champion insights" subtitle="Cut the data a few different ways" />
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <InsightCard href="/otp-champions" title="Best OTP champions" items={bestOtp.map((c) => ({ icon: c.icon, name: c.name, href: `/champions/${c.slug}`, metric: `${c.wr.toFixed(1)}%`, metricClass: "text-gold" }))} />
          <InsightCard href="/consistency" title="Highest skill ceiling" items={skillCeiling.map((c) => ({ icon: c.icon, name: c.name, href: `/champions/${c.slug}`, metric: `+${(c.skillSpread ?? 0).toFixed(1)}`, metricClass: "text-accent" }))} />
          <InsightCard href="/consistency" title="Most consistent" items={consistent.map((c) => ({ icon: c.icon, name: c.name, href: `/champions/${c.slug}`, metric: `±${(c.winrateStd ?? 0).toFixed(1)}`, metricClass: "text-muted" }))} />
          <InsightCard
            href="/champion-changes"
            title="Longest unchanged"
            subtitle="Standard balance changes only"
            items={longestUnchanged.map((entry) => ({
              icon: entry.champion.icon,
              name: entry.champion.name,
              sub: entry.lastBalancePatch ? `Last changed in patch ${entry.lastBalancePatch}` : "No standard change recorded",
              href: `/champions/${entry.champion.slug}`,
              metric: `${entry.daysSinceBalanceChange!.toLocaleString()} days`,
              metricClass: "text-gold",
            }))}
          />
        </div>
      </Container>

      {/* The other end of the same data: who Riot cannot leave alone. */}
      <Container className="py-6">
        <SectionHeading
          title="Most adjusted champions"
          subtitle="Times each champion has appeared in the patch notes since we started tracking"
          href="/champion-changes"
          linkLabel="Full champion changes"
        />
        <div className="grid gap-4 md:grid-cols-2 [&>*]:min-w-0">
          <InsightCard
            title="Riot cannot leave them alone"
            subtitle="Most patch-note appearances, all kinds"
            href="/champion-changes"
            items={mostAdjusted.map((entry) => ({
              icon: entry.champion.icon,
              name: entry.champion.name,
              sub: `${entry.balanceChanges} standard balance ${entry.balanceChanges === 1 ? "change" : "changes"}${entry.lastBalancePatch ? ` · last in ${entry.lastBalancePatch}` : ""}`,
              href: `/champions/${entry.champion.slug}`,
              metric: `${entry.totalChanges}×`,
              metricClass: "text-bad",
            }))}
          />
          <InsightCard
            title="Barely touched"
            subtitle="Fewest patch-note appearances"
            href="/champion-changes"
            items={leastAdjusted.map((entry) => ({
              icon: entry.champion.icon,
              name: entry.champion.name,
              sub: entry.totalChanges === 0
                ? "Never changed, not once"
                : `${entry.balanceChanges} standard balance ${entry.balanceChanges === 1 ? "change" : "changes"}`,
              href: `/champions/${entry.champion.slug}`,
              metric: `${entry.totalChanges}×`,
              metricClass: "text-emerald-300",
            }))}
          />
        </div>
      </Container>

      {/* Players */}
      <Container className="py-12">
        <div className="grid gap-4 md:grid-cols-2 [&>*]:min-w-0">
          <InsightCard href="/leaderboard#multi-champion-mains" title="Multi-champion mains" subtitle="Top 50 on three or more champions" items={site.multiChampionMains.slice(0, 6).map((m) => ({ icon: m.firstChampionIcon ?? undefined, name: m.player, sub: `${m.nChampions} champs · best #${m.bestRank}`, href: byName.get(m.champions[0]) ? `/leaderboard?champion=${byName.get(m.champions[0])!.slug}` : undefined, metric: m.avgWr != null ? `${m.avgWr.toFixed(0)}%` : "-", metricClass: "text-muted" }))} />
          <InsightCard href="/leaderboard#funniest-names" title="Funniest names" subtitle="Spotted in the top 50, lightly cleaned" items={site.funnyNames.slice(0, 6).map((f) => ({ icon: f.icon, name: f.player, sub: f.champion, href: byName.get(f.champion) ? `/leaderboard?champion=${byName.get(f.champion)!.slug}` : undefined }))} />
        </div>
      </Container>
    </>
  );
}
