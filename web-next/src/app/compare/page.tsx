import type { Metadata } from "next";
import { getChampions } from "@/lib/data";
import { getCnBySlug } from "@/lib/cn";
import { Container } from "@/components/ui";
import { ChampionCompare } from "@/components/champion-compare";

export const metadata: Metadata = {
  title: "Compare Champions — Wild Rift Win Rates Side by Side",
  description:
    "Compare any two Wild Rift champions head-to-head: EU and CN win rates, tier, pick/ban, ceiling, difficulty and best player, side by side.",
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
        Pick two champions to see their stats head-to-head — win rates across servers, tier, pick and
        ban rates, ceiling and more. The stronger value in each row is highlighted.
      </p>
      <div className="mt-8">
        <ChampionCompare champions={champions} cn={cn} />
      </div>
    </Container>
  );
}
