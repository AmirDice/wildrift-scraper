import type { Metadata } from "next";
import Link from "next/link";
import { site, getChampions } from "@/lib/data";
import { Container, Card, SectionHeading } from "@/components/ui";
import { LadderPulseSection } from "@/components/ladder-pulse-section";
import { UsageTables } from "@/components/usage-tables";
import { DeepDiveSections } from "@/components/deep-dive";
import {
  tierDistribution, wrHistogram, wrVsGames, classMeta, roleMeta,
  roleTierMatrix, metaHeadline,
} from "@/lib/meta-stats";
import { climbingPicks, stomperPicks } from "@/lib/skew";
import { NextStep } from "@/components/next-step";
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
    "The Wild Rift meta at a glance: what the top 50 players on every champion build, the runes and items that win, tier distribution, and win rate by class and role.",
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
        Meta Overview{site.collectedOn ? ` · ${site.collectedOn}` : ""}
      </p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">The meta at a glance</h1>
      <p className="mt-2 max-w-2xl text-muted">
        Everything below is built from the same real EU data as the tier list: the top 50 players
        on each of {h.nChampions} champions, confidence-adjusted so hype never skews the picture.
      </p>

      {/* headline strip */}
      <div className="mt-8 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Head label="Champions ranked" value={`${h.ranked}`} sub={`of ${h.nChampions} tracked`} />
        <Head label="Meta-defining" value={`${h.metaDefining}`} sub="in GOD or S tier" accent="text-accent" />
        <Head label="Strongest class" value={h.topClass.class} sub={`${h.topClass.wr.toFixed(1)}% top-5 WR`} accent="text-gold" />
        <Head label="Strongest role" value={h.topRole.role} sub={`${h.topRole.wr.toFixed(1)}% top picks`} />
      </div>

      {/* the freshly scraped boards: builds, queues and match-history evidence */}
      <LadderPulseSection championIcons={Object.fromEntries(getChampions().map((c) => [c.slug, c.icon]))} />

      {/* rune and item usage, ordered, with the win rate behind each choice */}
      <UsageTables />

      {/* everything that used to run down the home page */}
      <DeepDiveSections />

      {/* The charts live BELOW the cards and tables on purpose: most visitors
          want "what do I play and what do I build", and a scatter plot as the
          opening image reads like an exam. The chart-minded scroll; everyone
          else has already been served. */}
      <div className="mt-12 border-t border-line/60 pt-8">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">For the chart-minded</p>
        <h2 className="mt-2 text-2xl font-semibold tracking-tight">The same meta, visualized</h2>
      </div>
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
            href="/ranks"
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
          <SectionHeading title="Win rate by role" subtitle="Strength of each role's meta picks" href="/ranks" linkLabel="Skill-bracket trends" />
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
