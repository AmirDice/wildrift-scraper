import type { Metadata } from "next";
import Link from "next/link";
import { Container, Card } from "@/components/ui";
import { CURRENT_PATCH } from "@/lib/patch";

/**
 * Landing page for "op.gg wild rift" / "u.gg wild rift" / "wildrift op.gg"
 * searches (owner request, 2026-11-28).
 *
 * Nominative use only: OP.GG and U.GG are named because that is what people
 * type, never implied to be affiliated, and nothing here claims what those
 * sites do or do not cover for Wild Rift -- that could not be verified and
 * can change. The page says what WrTrueMeta does and where each thing
 * someone would look for on a PC stats site lives here.
 */

const TITLE = "OP.GG and U.GG for Wild Rift: Stats, Builds, Tier List and Player Search";
const DESCRIPTION =
  "Know OP.GG or U.GG from League of Legends? WrTrueMeta does that job for Wild Rift (WildRift): "
  + "a tier list from the top players of every champion, builds, counters, leaderboards and player search.";

export const metadata: Metadata = {
  title: TITLE,
  description: DESCRIPTION,
  alternates: { canonical: "/wild-rift-op-gg-u-gg" },
  openGraph: { title: TITLE, description: DESCRIPTION, url: "/wild-rift-op-gg-u-gg" },
};

const MAP: { want: string; where: string; href: string; detail: string }[] = [
  {
    want: "Tier list",
    where: "Wild Rift Tier List",
    href: "/tier-list",
    detail: "Every champion ranked by how its top 30 players in EU and NA are actually doing, with China's official rates on their own tab.",
  },
  {
    want: "Champion builds and runes",
    where: "Champion pages and Build Studio",
    href: "/champions",
    detail: "What the best players of each champion build, plus Build Studio for a build generated for your playstyle and matchup.",
  },
  {
    want: "Counters and matchups",
    where: "Build vs Enemy Team",
    href: "/build?tab=counter",
    detail: "Enter the enemy team and get the build that answers those five picks.",
  },
  {
    want: "Summoner lookup",
    where: "Player Search",
    href: "/player",
    detail: "Find a player and every champion they rank on, across the servers we collect.",
  },
  {
    want: "Leaderboards",
    where: "Player Leaderboards",
    href: "/leaderboard",
    detail: "The top players on every champion, with their win rates and builds.",
  },
  {
    want: "Patch changes",
    where: "Balance Report and Patch Movers",
    href: "/changes-report",
    detail: "Every buff and nerf per patch, and which champions moved most since.",
  },
];

const FAQ: { q: string; a: string }[] = [
  {
    q: "Is there an OP.GG or U.GG for Wild Rift?",
    a: "WrTrueMeta is built for Wild Rift and covers what League of Legends players use OP.GG and U.GG for: a tier list, champion builds and runes, counters, leaderboards and player search.",
  },
  {
    q: "How is the WrTrueMeta tier list different?",
    a: "Instead of averaging every ranked game, it measures the top players of each champion on the EU and NA leaderboards, so it shows how strong a champion is in the hands of someone who has mastered it.",
  },
  {
    q: "Is WrTrueMeta affiliated with OP.GG, U.GG or Riot Games?",
    a: "No. WrTrueMeta is independent. OP.GG and U.GG are trademarks of their owners and are named here only so people looking for them can find a Wild Rift stats site. WrTrueMeta is not endorsed by Riot Games.",
  },
  {
    q: "Is it Wild Rift or WildRift?",
    a: "Both spellings mean League of Legends: Wild Rift, Riot's mobile version of League. Search either one and you are looking for the same game.",
  },
];

export default function OpGgUggPage() {
  const faqLd = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: FAQ.map(({ q, a }) => ({
      "@type": "Question",
      name: q,
      acceptedAnswer: { "@type": "Answer", text: a },
    })),
  };
  return (
    <Container className="py-12">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(faqLd) }}
      />
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">
        Wild Rift stats{CURRENT_PATCH ? ` · Patch ${CURRENT_PATCH}` : ""}
      </p>
      <h1 className="mt-3 max-w-3xl text-3xl font-semibold tracking-tight sm:text-4xl">
        Looking for OP.GG or U.GG for Wild Rift?
      </h1>
      <p className="mt-3 max-w-2xl leading-relaxed text-muted">
        If you know OP.GG or U.GG from League of Legends on PC, WrTrueMeta does that job for Wild
        Rift (also written WildRift): champion stats, builds, counters, leaderboards and player
        search, built from the players at the top of every champion&rsquo;s leaderboard.
      </p>

      <section className="mt-10">
        <h2 className="text-lg font-semibold">What you would look for, and where it is here</h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          {MAP.map((row) => (
            <Card key={row.href} className="p-5">
              <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-faint">{row.want}</p>
              <Link href={row.href} className="mt-1 inline-block text-base font-semibold text-text hover:text-accent">
                {row.where}
              </Link>
              <p className="mt-1.5 text-sm leading-relaxed text-muted">{row.detail}</p>
            </Card>
          ))}
        </div>
      </section>

      <section className="mt-12 max-w-3xl">
        <h2 className="text-lg font-semibold">Questions</h2>
        <div className="mt-4 flex flex-col gap-4">
          {FAQ.map(({ q, a }) => (
            <Card key={q} className="p-5">
              <h3 className="text-sm font-semibold text-text">{q}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-muted">{a}</p>
            </Card>
          ))}
        </div>
      </section>
    </Container>
  );
}
