import type { Metadata } from "next";
import { site, getChampions } from "@/lib/data";
import { Container, SectionHeading } from "@/components/ui";
import { LeaderboardView, type SlimChampion } from "@/components/leaderboard-view";
import items from "@/data/items.json";
import runeIcons from "@/data/rune_icons.json";
import spells from "@/data/spells.json";

// This is the page the site genuinely ranks for: "wild rift leaderboard" sits
// around position 6-8 and "wild rift leaderboard eu" around 3, where the head
// terms (tier list, meta) are stuck in the forties. The singular "Leaderboard"
// and the explicit EU qualifier both match how people actually search for it.
export const metadata: Metadata = {
  title: "Wild Rift Leaderboard | Top 50 EU Players on Every Champion",
  description:
    "The Wild Rift leaderboard for every champion: the top 50 ranked EU players on each one, with win rate, games played and mastery. Sort by rank, win rate, games or mastery.",
  alternates: { canonical: "/leaderboard" },
  openGraph: {
    title: "Wild Rift Leaderboard | Top 50 EU Players on Every Champion",
    description:
      "The top 50 ranked EU players on every Wild Rift champion, with win rate, games and mastery.",
    url: "https://wrtruemeta.com/leaderboard",
  },
};

export default function LeaderboardPage() {
  const champions = getChampions();
  // slug -> icon path, for the per-player build columns; slim on purpose so
  // the client bundle carries paths, not the whole item catalog
  const itemIcons: Record<string, string> = {};
  for (const it of items as { slug: string; icon?: string }[]) {
    if (it.icon) itemIcons[it.slug] = it.icon;
  }
  const slim: SlimChampion[] = champions.map((c) => ({
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
      <section id="players" className="mt-8 scroll-mt-24">
        <SectionHeading title="Champion player leaderboard" subtitle="Choose a champion and inspect its full top-50 player table, with builds, ranked tiers and per-queue stats where freshly captured" />
        <LeaderboardView
          champions={slim}
          itemIcons={itemIcons}
          runeIcons={runeIcons as Record<string, string>}
          spellIcons={Object.fromEntries(
            (spells as { name: string; icon: string }[]).map((s) => [s.name, s.icon])
          )}
        />
      </section>
    </Container>
  );
}
