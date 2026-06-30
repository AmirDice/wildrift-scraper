import type { Metadata } from "next";
import { site, getChampions } from "@/lib/data";
import { Container } from "@/components/ui";
import { LeaderboardView, type SlimChampion } from "@/components/leaderboard-view";

export const metadata: Metadata = {
  title: "Wild Rift Leaderboards — Top 50 Players per Champion",
  description:
    "The top 50 EU players on every Wild Rift champion, with their win rate, games and mastery. Sortable by rank, win rate, games or mastery.",
  alternates: { canonical: "/leaderboard" },
};

export default function LeaderboardPage() {
  const slim: SlimChampion[] = getChampions().map((c) => ({
    name: c.name,
    slug: c.slug,
    icon: c.icon,
    splash: c.splash,
    role: c.role,
    class: c.class,
    tier: c.tier,
    wr: c.wr,
    isHard: c.isHard,
    bestPlayer: c.bestPlayer,
  }));

  return (
    <Container className="py-12">
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Leaderboards</h1>
      <p className="mt-2 max-w-2xl text-muted">
        The top 50 players on each champion, straight from the in-game leaderboard. Pick a
        champion and sort by win rate, games or mastery.
        {site.collectedOn && (
          <span className="text-faint"> Data collected {site.collectedOn}.</span>
        )}
      </p>
      <div className="mt-8">
        <LeaderboardView champions={slim} />
      </div>
    </Container>
  );
}
