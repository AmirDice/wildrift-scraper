import type { Metadata } from "next";
import Link from "next/link";
import { getChampions, regionBoard } from "@/lib/data";
import { AdSlot } from "@/components/ad-slot";
import { Container, Card, SectionHeading } from "@/components/ui";
import { LadderPulseSection } from "@/components/ladder-pulse-section";
import { UsageTables } from "@/components/usage-tables";
import { MetaTabs } from "@/components/meta-tabs";
import { ChinaThisWeek } from "@/components/china-this-week";
import { chinaThisWeek } from "@/lib/china-meta";
import { SKIPPED_PATCH } from "@/lib/announcement";
import { DeepDiveSections } from "@/components/deep-dive";
import {
  tierDistribution, wrHistogram, wrVsGames, classMeta, roleMeta,
  roleTierMatrix, metaHeadline,
} from "@/lib/meta-stats";
import { climbingPicks, stomperPicks } from "@/lib/skew";
import { NextStep } from "@/components/next-step";
import { ConsistencySection } from "@/components/merged/consistency-section";
import { OneTrickSection } from "@/components/merged/one-trick-section";
import {
  MetaScatter, TierBars, RoleTierHeatmap, WrHistogram, ValueBars, SkewDumbbell,
  type SkewRow,
} from "@/components/meta-charts";

export const metadata: Metadata = {
  // "Overview", not "Report". A report is homework; an overview is
  // orientation. Same reasoning as the page order below: cards and tables
  // first, charts afterwards for whoever wants to keep reading.
  title: "Meta Overview | Wild Rift Win Rates, Builds & Trends",
  description:
    "The Wild Rift meta at a glance: what the top players on every champion build, the runes and items that win, tier distribution, and win rate by class and role.",
  alternates: { canonical: "/meta" },
};

export default function MetaPage() {
  const h = metaHeadline();
  const tiers = tierDistribution();
  const hist = wrHistogram(1);
  const scatter = wrVsGames();
  const classes = classMeta();
  const roles = roleMeta();
  const heat = roleTierMatrix();

  const toRow = (s: ReturnType<typeof climbingPicks>[number]): SkewRow => ({
    slug: s.champion.slug, name: s.champion.name, icon: s.champion.icon,
    role: s.champion.role, low: s.low, high: s.high, skew: s.skew,
  });
  const climbers = climbingPicks(7).map(toRow);
  const fallers = stomperPicks(7).map(toRow);

  return (
    <Container className="py-12">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">
        Meta Overview · Global
      </p>

      <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">The meta at a glance</h1>
      <p className="mt-2 max-w-2xl text-muted">
        {`What wins, what gets built and who is rising, from the top-player boards of EU, NA and China across ${h.nChampions} champions.`}
      </p>
      <p className="mt-2 max-w-3xl text-xs text-faint">
        Board captures: {(["EU", "NA", "CN"] as const).map((server) => `${server} ${regionBoard(server).collectedOn ?? "date unavailable"}`).join(" · ")}.
        {" "}Global figures weight each server equally; they are top-player estimates, not every ranked match.
      </p>

      <MetaTabs panels={[
        {
          key: "overview",
          label: "Overview",
          blurb: "The headline numbers, and what the freshly collected boards agree on.",
          content: (
            <>
              <div className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
                <Head label="Champions ranked" value={`${h.ranked}`} sub={`of ${h.nChampions} tracked`} />
                <Head label="Meta-defining" value={`${h.metaDefining}`} sub="in GOD or S tier" accent="text-accent" />
                <Head label="Strongest class" value={h.topClass.class} sub={`${h.topClass.wr.toFixed(1)}% top-5 WR`} accent="text-gold" />
                <Head label="Strongest role" value={h.topRole.role} sub={`${h.topRole.wr.toFixed(1)}% top picks`} />
              </div>
              <LadderPulseSection championIcons={Object.fromEntries(getChampions().map((c) => [c.slug, c.icon]))} />
            </>
          ),
        },
        {
          key: "builds",
          label: "Builds",
          blurb: "Every rune and item the top boards equip, and what China's Legendary players are building this week.",
          anchors: ["china-this-week"],
          content: (
            <>
              <UsageTables />
              <ChinaThisWeek data={chinaThisWeek(SKIPPED_PATCH)} />
            </>
          ),
        },
        {
          key: "champions",
          label: "Champions",
          short: "Picks",
          blurb: "Who is strong everywhere, who China rates ahead of EU, who scales with elo, and the patch-note regulars.",
          content: <div className="-mx-4 sm:-mx-6"><DeepDiveSections /></div>,
        },
        {
          key: "specialists",
          label: "Specialists",
          short: "OTPs",
          blurb: "Champions worth one-tricking, and the ones whose top players win most consistently.",
          anchors: ["one-trick", "consistency"],
          content: (
            <>
              <OneTrickSection />
              <ConsistencySection />
            </>
          ),
        },
        {
          key: "charts",
          label: "Charts",
          blurb: "The same meta, visualised: win rate against popularity, elo scaling, tiers, classes and roles.",
          anchors: ["classes", "roles"],
          content: (
            <>
      {/* centerpiece scatter */}
      <div className="mt-10">
        <SectionHeading title="Win rate vs popularity" subtitle="Every ranked champion, mapped by how much it wins against how much it is played. Top-left is a hidden gem, top-right is a proven meta pillar." />
        <Card className="p-5 sm:p-6">
          <MetaScatter points={scatter} />
        </Card>
      </div>

      {/* elo-skew dumbbell */}
      {(climbers.length > 0 || fallers.length > 0) && (
        <div className="mt-10">
          <SectionHeading
            title="Who scales with elo"
            subtitle="Win rate at Diamond+ vs the Challenger bracket (CN ranked data). A long line means the champion plays very differently at the top."
            href="/regions#brackets"
            linkLabel="Every champion by rank"
          />
          <Card className="p-5 sm:p-6">
            <SkewDumbbell climbers={climbers} fallers={fallers} />
          </Card>
        </div>
      )}

      {/* tier distribution + histogram */}
      <div className="mt-10 grid gap-6 lg:grid-cols-2">
        <div>
          <SectionHeading title="Tier distribution" subtitle="How the roster splits across tiers" href="/tier-list" linkLabel="Full tier list" />
          <Card className="p-5 sm:p-6"><TierBars rows={tiers} /></Card>
        </div>
        <div>
          <SectionHeading title="Win rate distribution" subtitle="Champion win rates, 50%-centred" />
          <Card className="p-5 sm:p-6"><WrHistogram bins={hist} /></Card>
        </div>
      </div>

      {/* class bars + role bars */}
      <div className="mt-10 grid gap-6 lg:grid-cols-2">
        <div id="classes" className="scroll-mt-24">
          <SectionHeading title="Win rate by class" subtitle="Average of each class's top 5 picks" />
          <Card className="p-5 sm:p-6">
            <ValueBars rows={classes.map((c) => ({ label: c.class, value: c.wr }))} />
            <p className="mt-5 border-t border-line/60 pt-4 text-xs text-faint">
              Champion difficulty barely moves the needle: every difficulty bucket sits within
              about one point of 50%, so play what you enjoy.
            </p>
          </Card>
        </div>
        <div id="roles" className="scroll-mt-24">
          <SectionHeading title="Win rate by role" subtitle="Strength of each role's meta picks" href="/regions#brackets" linkLabel="Skill-bracket trends" />
          <Card className="p-5 sm:p-6">
            <ValueBars rows={roles.map((r) => ({ label: r.role, value: r.wr }))} />
          </Card>
        </div>
      </div>

      {/* heatmap */}
      <div className="mt-10">
        <SectionHeading title="Where each role's power sits" subtitle="Champion count by role and tier. Darker means more champions land in that tier." />
        <Card className="p-5 sm:p-6"><RoleTierHeatmap rows={heat} /></Card>
      </div>


            </>
          ),
        },
      ]} />

      <AdSlot placement="inline" bare className="mt-10" />
      <p className="mt-10 text-sm text-faint">
        Want the raw ordering instead of the charts?{" "}
        <Link href="/tier-list" className="text-accent hover:underline">See the full tier list</Link>
        {" "}or{" "}
        <Link href="/champions" className="text-accent hover:underline">browse every champion</Link>.
      </p>
      <NextStep steps={["build", "counter"]} />

    </Container>
  );
}

function Head({ label, value, sub, accent = "" }: { label: string; value: string; sub: string; accent?: string }) {
  return (
    <Card className="p-5">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted">{label}</p>
      <p className={`mt-2 truncate text-2xl font-semibold ${accent}`}>{value}</p>
      <p className="mt-0.5 text-sm text-muted">{sub}</p>
    </Card>
  );
}
