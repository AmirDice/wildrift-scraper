import type { Metadata } from "next";
import { getChampions, site } from "@/lib/data";
import { Container, SectionHeading } from "@/components/ui";
import { PlayerSearch, type ChampionRef } from "@/components/player-search";
import { NextStep } from "@/components/next-step";

// Singular /player, not /players: web-next/public/players/ already serves the
// per-champion JSON at that path, and a route sharing it would be a trap for
// whoever touches this next.
export const metadata: Metadata = {
  title: "Wild Rift Player Search | Find Any Top 50 Player and Their Champions",
  description:
    "Search any Wild Rift player on the EU top 50 boards by name or #tag. See their ranked tier, level, every champion they rank on, and their win rate and games on each.",
  alternates: { canonical: "/player" },
};

export default function PlayerSearchPage() {
  const champions: ChampionRef[] = getChampions().map((c) => ({
    slug: c.slug,
    name: c.name,
    icon: c.icon,
    splash: c.splash,
  }));

  return (
    <Container className="py-12">
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Player search</h1>
      <p className="mt-2 max-w-2xl text-muted">
        Find a player across every champion leaderboard. Search by name, with or without
        the #tag, and see their ranked tier, level and how they perform on each champion
        they rank on.
        {site.collectedOn && (
          <span className="text-faint"> Data collected {site.collectedOn}.</span>
        )}
      </p>

      <section className="mt-8">
        <SectionHeading
          title="Search the ladder"
          subtitle="Only players inside a champion's top 50 are collected, so this covers the top of the ladder rather than every account"
        />
        <PlayerSearch champions={champions} />
      </section>

      <NextStep steps={["leaderboard", "tierList"]} />
    </Container>
  );
}
