import type { Metadata } from "next";
import Link from "next/link";
import { site, getChampions, regionBoard } from "@/lib/data";
import { getCnChampions, cnRoles, CN_META, cnChampionsWithoutData } from "@/lib/cn";
import rosterData from "@/data/roster.json";
import { AdSlot } from "@/components/ad-slot";
import { Container } from "@/components/ui";
import { ChampionsExplorer } from "@/components/champions-explorer";
import { NewChampions } from "@/components/new-champions";
import { NextStep } from "@/components/next-step";

export const metadata: Metadata = {
  title: "Wild Rift Champions | Stats & Win Rates",
  description:
    "Every Wild Rift champion ranked by the real win rates of its top players on EU and NA. Search and filter by role, then open a champion for full stats and its best player.",
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
    <section
      className="champions-revamp no-plate"
      style={{
        backgroundImage:
          "radial-gradient(55rem 28rem at 88% 2%, rgba(52,170,173,.16), transparent 70%), radial-gradient(42rem 28rem at 8% 18%, rgba(82,130,225,.15), transparent 72%), linear-gradient(180deg, rgba(8,19,33,.84), rgba(6,15,29,.91))",
      }}
    >
      <Container className="relative py-10 sm:py-14">
      <div className="flex flex-wrap items-end justify-between gap-5">
        <div className="max-w-2xl">
          <p className="mb-3 text-xs font-bold uppercase tracking-[0.2em] text-emerald-300">Champion atlas</p>
          <h1 className="display-title text-6xl leading-[0.9] sm:text-7xl lg:text-[5.5rem]">Champions</h1>
          <p className="mt-4 text-base text-muted sm:text-lg">Find the right pick. See what matters.</p>
        </div>
        <Link
          href="/compare"
          className="liquid-glass glass-hover inline-flex items-center gap-1.5 rounded-xl px-4 py-2.5 text-sm font-semibold text-text"
        >
          Compare champions <span aria-hidden>→</span>
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
      <AdSlot placement="inline" bare className="my-10" />
      {/* Champions who are live in the game but have no ranked sample yet.
          They cannot be placed in the explorer above without inventing a win
          rate, so they get their own section with the kit we do have. */}
      <div className="mt-14">
        <NewChampions />
      </div>
      <NextStep steps={["build", "tierList"]} />

      </Container>
    </section>
  );
}
