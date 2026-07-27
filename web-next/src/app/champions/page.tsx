import type { Metadata } from "next";
import { site, getChampions } from "@/lib/data";
import { getCnChampions, cnRoles, CN_META } from "@/lib/cn";
import { Container } from "@/components/ui";
import { ChampionsExplorer } from "@/components/champions-explorer";
import { NewChampions } from "@/components/new-champions";

export const metadata: Metadata = {
  title: "Wild Rift Champions | Stats & Win Rates",
  description:
    "Every Wild Rift champion ranked by real EU top-50 player win rates. Search and filter by role, then open a champion for full stats and its best player.",
  alternates: { canonical: "/champions" },
};

export default function ChampionsPage() {
  const champions = getChampions();
  return (
    <Container className="py-12">
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Champions</h1>
      <div className="mt-8">
        <ChampionsExplorer
          champions={champions}
          roles={site.roles}
          cnChampions={getCnChampions()}
          cnRoles={cnRoles()}
          cnMeta={CN_META}
          euUpdated={site.collectedOn}
        />
      </div>
      {/* Champions who are live in the game but have no ranked sample yet.
          They cannot be placed in the explorer above without inventing a win
          rate, so they get their own section with the kit we do have. */}
      <div className="mt-14">
        <NewChampions />
      </div>
    </Container>
  );
}
