import type { Metadata } from "next";
import Link from "next/link";
import { site, getChampions, regionBoard } from "@/lib/data";
import { getCnChampions, cnRoles, CN_META, cnChampionsWithoutData } from "@/lib/cn";
import rosterData from "@/data/roster.json";
import { Container } from "@/components/ui";
import { ChampionsExplorer } from "@/components/champions-explorer";
import { NewChampions } from "@/components/new-champions";
import { NextStep } from "@/components/next-step";

export const metadata: Metadata = {
  title: "Wild Rift Champions | Stats & Win Rates",
  description:
    "Every Wild Rift champion ranked by real EU top-50 player win rates. Search and filter by role, then open a champion for full stats and its best player.",
  alternates: { canonical: "/champions" },
};

export default function ChampionsPage() {
  const champions = getChampions();
  // Named per region so the explorer can say WHICH champions have no numbers,
  // rather than just listing fewer than the game has.
  const roster = Object.keys(rosterData);
  const euNames = new Set(champions.map((c) => c.name));
  const absent = {
    CN: cnChampionsWithoutData(),
    EU: roster.filter((name) => !euNames.has(name)).sort((a, b) => a.localeCompare(b)),
  };
  return (
    <Container className="py-12">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Champions</h1>
        <Link
          href="/compare"
          className="glass glass-hover inline-flex items-center gap-1.5 rounded-xl px-4 py-2 text-sm font-semibold text-text"
        >
          Want to compare champions? Click here <span aria-hidden>→</span>
        </Link>
      </div>
      <div className="mt-8">
        <ChampionsExplorer
          champions={champions}
          roles={site.roles}
          cnChampions={getCnChampions()}
          naChampions={regionBoard("NA").champions}
          naRoles={regionBoard("NA").roles}
          naUpdated={regionBoard("NA").collectedOn}
          cnRoles={cnRoles()}
          cnMeta={CN_META}
          euUpdated={site.collectedOn}
          absent={absent}
          rosterSize={roster.length}
        />
      </div>
      {/* Champions who are live in the game but have no ranked sample yet.
          They cannot be placed in the explorer above without inventing a win
          rate, so they get their own section with the kit we do have. */}
      <div className="mt-14">
        <NewChampions />
      </div>
      <NextStep steps={["build", "tierList"]} />

    </Container>
  );
}
