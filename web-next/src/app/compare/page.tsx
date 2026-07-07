import type { Metadata } from "next";
import { getChampions } from "@/lib/data";
import { getCnBySlug } from "@/lib/cn";
import countersData from "@/data/counters.json";
import { Container } from "@/components/ui";
import { ChampionCompare } from "@/components/champion-compare";

const COUNTERS = countersData as unknown as Record<string, { weak: string[]; strong: string[] }>;

export const metadata: Metadata = {
  title: "Compare Champions | Wild Rift Win Rates Side by Side",
  description:
    "Compare any two Wild Rift champions head-to-head: EU and CN win rates, pick/ban, ceiling and skill on a radar, plus their direct matchup.",
  alternates: { canonical: "/compare" },
};

export default function ComparePage() {
  const champions = getChampions();
  const cn: Record<string, { wr: number; pick: number; ban: number; tier: string }> = {};
  for (const c of champions) {
    const e = getCnBySlug(c.slug);
    if (e) cn[c.slug] = { wr: e.wr, pick: e.cnPickRate, ban: e.cnBanRate, tier: e.tier };
  }

  return (
    <Container className="py-12">
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Compare Champions</h1>
      <p className="mt-2 max-w-2xl text-muted">
        Pick two champions for a full head-to-head: win rates across servers, a stat radar, the
        direct matchup, and every number side by side.
      </p>
      <div className="mt-8">
        <ChampionCompare champions={champions} cn={cn} counters={COUNTERS} />
      </div>
    </Container>
  );
}
