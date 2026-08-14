import type { Metadata } from "next";
import { Container, Card } from "@/components/ui";
import { WinRateExplorer, type WinRateView } from "@/components/win-rate-explorer";
import { PatchLagNotice } from "@/components/patch-lag-notice";
import { freshness } from "@/lib/patch-freshness";
import { getChampions, site } from "@/lib/data";
import { getCnChampions } from "@/lib/cn";

export const metadata: Metadata = {
  title: "Wild Rift Champion Win Rates | Highest, Lowest & Off-Meta",
  description: "Explore every Wild Rift champion by highest win rate, lowest win rate, role, region and strong off-meta performance.",
  alternates: { canonical: "/win-rates" },
};

export default async function WinRatesPage({ searchParams }: { searchParams: Promise<{ view?: string }> }) {
  const requested = (await searchParams).view;
  const initialView: WinRateView = requested === "lowest" || requested === "off-meta" ? requested : "highest";
  const champions = getChampions();
  return <Container className="py-10 sm:py-14"><div className="max-w-3xl"><p className="text-xs font-semibold uppercase tracking-[0.16em] text-accent">Win Rate Explorer</p><h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">Find what is winning—and what is not</h1><p className="mt-3 leading-relaxed text-muted">Explore the full roster instead of stopping at a homepage top five. Switch between the highest performers, lowest performers and strong off-meta picks.</p></div><div className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-3"><Card className="p-4"><p className="text-[0.65rem] font-semibold uppercase tracking-wide text-faint">EU champions</p><p className="mt-2 text-2xl font-semibold">{champions.length}</p></Card><Card className="p-4"><p className="text-[0.65rem] font-semibold uppercase tracking-wide text-faint">Top-50 records</p><p className="mt-2 text-2xl font-semibold text-accent">{site.nPlayers.toLocaleString()}</p></Card><Card className="col-span-2 p-4 sm:col-span-1"><p className="text-[0.65rem] font-semibold uppercase tracking-wide text-faint">Updated</p><p className="mt-2 text-xl font-semibold text-gold">{site.collectedOn ?? "Current dataset"}</p></Card></div><PatchLagNotice freshness={freshness(site.collectedOn)} className="mt-6" /><div className="mt-8"><WinRateExplorer eu={champions} cn={getCnChampions()} roles={site.roles} offMetaSlugs={site.offMetaSlugs} initialView={initialView}/></div></Container>;
}
