import type { Metadata } from "next";
import Link from "next/link";
import { site } from "@/lib/data";
import { Container, Card, SectionHeading } from "@/components/ui";
import {
  tierDistribution, wrHistogram, wrVsGames, classMeta, roleMeta,
  roleTierMatrix, difficultyMeta, metaHeadline,
} from "@/lib/meta-stats";
import {
  MetaScatter, TierBars, ClassRadar, RoleTierHeatmap, WrHistogram, ValueBars, DifficultyBars,
} from "@/components/meta-charts";

export const metadata: Metadata = {
  title: "Meta Report | Wild Rift Win Rate Charts & Visualizations",
  description:
    "The Wild Rift meta at a glance: tier distribution, win rate by class and role, a win-rate-vs-popularity map of every champion, and how the ladder splits across tiers.",
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
  const diff = difficultyMeta();

  return (
    <Container className="py-12">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">
        Meta Report{site.collectedOn ? ` · ${site.collectedOn}` : ""}
      </p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">The meta, visualized</h1>
      <p className="mt-2 max-w-2xl text-muted">
        Every chart below is built from the same real EU data as the tier list: the top 50 players
        on each of {h.nChampions} champions, confidence-adjusted so hype never skews the picture.
      </p>

      {/* headline strip */}
      <div className="mt-8 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Head label="Champions ranked" value={`${h.ranked}`} sub={`of ${h.nChampions} tracked`} />
        <Head label="Meta-defining" value={`${h.metaDefining}`} sub="in GOD or S tier" accent="text-accent" />
        <Head label="Strongest class" value={h.topClass.class} sub={`${h.topClass.wr.toFixed(1)}% top-5 WR`} accent="text-gold" />
        <Head label="Strongest role" value={h.topRole.role} sub={`${h.topRole.wr.toFixed(1)}% top picks`} />
      </div>

      {/* centerpiece scatter */}
      <div className="mt-10">
        <SectionHeading title="Win rate vs popularity" subtitle="Every ranked champion, mapped by how much it wins against how much it is played. Top-left is a hidden gem, top-right is a proven meta pillar." />
        <Card className="p-5 sm:p-6">
          <MetaScatter points={scatter} />
        </Card>
      </div>

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

      {/* class radar + role bars */}
      <div className="mt-10 grid gap-6 lg:grid-cols-2">
        <div>
          <SectionHeading title="Win rate by class" subtitle="Average of each class's top 5 picks" />
          <Card className="flex items-center justify-center p-5 sm:p-6"><ClassRadar rows={classes} /></Card>
        </div>
        <div>
          <SectionHeading title="Win rate by role" subtitle="Strength of each role's meta picks" href="/ranks" linkLabel="Win rate by rank" />
          <Card className="p-5 sm:p-6">
            <ValueBars rows={roles.map((r) => ({ label: r.role, value: r.wr }))} />
            <div className="mt-6 border-t border-line/60 pt-5">
              <p className="mb-3 text-sm font-medium text-muted">Does difficulty pay off? Win rate by champion difficulty</p>
              <DifficultyBars rows={diff} />
            </div>
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
