import type { Metadata } from "next";
import { site, getChampions } from "@/lib/data";
import { Container } from "@/components/ui";
import { ChampionsExplorer } from "@/components/champions-explorer";

export const metadata: Metadata = {
  title: "Wild Rift Champions — Stats & Win Rates",
  description:
    "Every Wild Rift champion ranked by real EU top-50 player win rates. Search and filter by role, then open a champion for full stats and its best player.",
  alternates: { canonical: "/champions" },
};

export default function ChampionsPage() {
  const champions = getChampions();
  return (
    <Container className="py-12">
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Champions</h1>
      <p className="mt-2 max-w-2xl text-muted">
        Every champion tracked on EU, ranked by top-50 player win rates.
      </p>
      <div className="mt-8">
        <ChampionsExplorer champions={champions} roles={site.roles} />
      </div>
    </Container>
  );
}
