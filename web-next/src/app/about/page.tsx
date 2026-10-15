import type { Metadata } from "next";
import Link from "next/link";
import { Container, Card } from "@/components/ui";
import { regionBoard } from "@/lib/data";
import { CURRENT_PATCH } from "@/lib/patch";

export const metadata: Metadata = {
  title: "About WrTrueMeta",
  description:
    "WrTrueMeta is an independent Wild Rift stats site built from the top players of every champion in EU, NA and China. Who runs it, where the data comes from and how it is kept current.",
  alternates: { canonical: "/about" },
};

/**
 * Who runs the site and where the numbers come from.
 *
 * Every figure here is read from the same data the pages use, so the page
 * cannot drift from the site it describes.
 */
export default function AboutPage() {
  const boards = (["EU", "NA", "CN"] as const).map((region) => ({ region, ...regionBoard(region) }));
  const players = boards.reduce((total, board) => total + (board.nPlayers || 0), 0);
  return (
    <Container className="py-12">
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">About WrTrueMeta</h1>
      <p className="mt-2 max-w-2xl text-muted">
        An independent Wild Rift stats site that measures what the best players of each champion
        actually do, instead of averaging every game played.
      </p>

      <div className="mt-8 flex max-w-3xl flex-col gap-5">
        <Card>
          <h2 className="text-lg font-semibold">Why it exists</h2>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            Most tier lists either average every ranked game, which mostly measures how easy a
            champion is for the average player, or they are one person&rsquo;s opinion. WrTrueMeta
            takes a third route: for every champion it collects the players at the top of that
            champion&rsquo;s regional leaderboard and measures how they are doing. That answers a
            different question, which is how strong a champion is in the hands of someone who has
            mastered it.
          </p>
        </Card>

        <Card>
          <h2 className="text-lg font-semibold">Where the data comes from</h2>
          <ul className="mt-2 flex flex-col gap-2 text-sm leading-relaxed text-muted">
            {boards.map((board) => (
              <li key={board.region}>
                <span className="font-medium text-text">{board.region === "CN" ? "China" : board.region} top players:</span>{" "}
                {board.nChampions} champions
                {board.nPlayers ? `, ${board.nPlayers.toLocaleString("en-US")} player records` : ""}
                {board.collectedOn ? `, collected ${board.collectedOn}` : ""}.
              </li>
            ))}
            <li>
              <span className="font-medium text-text">China&rsquo;s ranked brackets:</span>{" "}
              Tencent&rsquo;s
              published win, pick and ban rates for Diamond, Master, Challenger and Legendary, refreshed daily.
            </li>
            <li>
              <span className="font-medium text-text">Patches:</span>{" "}
              every ability, item and rune number
              is updated from Riot&rsquo;s patch notes, currently patch {CURRENT_PATCH}.
            </li>
          </ul>
          <p className="mt-3 text-sm leading-relaxed text-muted">
            That is {players.toLocaleString("en-US")} player records across the three regional boards. How
            they become win rates, tiers and best-player scores is set out in the{" "}
            <Link href="/methodology" className="font-medium text-accent hover:opacity-80">methodology</Link>.
          </p>
        </Card>

        <Card>
          <h2 className="text-lg font-semibold">Who runs it</h2>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            WrTrueMeta is built and maintained by one independent developer who plays Wild Rift. The
            collection pipeline, the statistics and the build tools are all written for this site.
            It is not affiliated with or endorsed by Riot Games or Tencent.
          </p>
        </Card>

        <Card>
          <h2 className="text-lg font-semibold">How it is kept current</h2>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            The leaderboards are collected again roughly twice a month, China&rsquo;s bracket data every
            day, and each patch is applied when Riot publishes the notes. Every change to the site is
            listed on the <Link href="/updates" className="font-medium text-accent hover:opacity-80">updates page</Link>,
            and what changed for each champion is on its own page.
          </p>
        </Card>

        <Card>
          <h2 className="text-lg font-semibold">Get in touch</h2>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            Spotted a wrong number, or have an idea? Use the{" "}
            <Link href="/contact" className="font-medium text-accent hover:opacity-80">contact form</Link>{" "}
            or join the Discord. Data corrections are the most useful message the site gets.
          </p>
        </Card>
      </div>
    </Container>
  );
}
