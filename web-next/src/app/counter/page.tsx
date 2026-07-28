import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { EnemyBuildAdvisor } from "@/components/enemy-build";
import { CounterTour } from "@/components/counter-tour";
import { StudioCta } from "@/components/tool-crosslinks";
import { Container } from "@/components/ui";
import { buildToolsVisible } from "@/lib/access";

export const metadata: Metadata = {
  // No "| WrTrueMeta" suffix here: the root layout's title template already
  // appends one, and spelling it out again renders it twice in the tab and in
  // search results.
  title: "Counter Builder | Optimal Counter Builds",
  description: "Pick your champion and the enemy team, and get the optimal build: items, order, boots and runes, tuned to that specific comp.",
  robots: { index: false, follow: false },
};

export default async function CounterPage(props: PageProps<"/counter">) {
  if (!(await buildToolsVisible())) redirect("/");
  const search = await props.searchParams;
  // Shared counter links arrive with the champion already chosen; it stays
  // changeable, unlike the studio's embedded advisor.
  const initialChampion = typeof search.champion === "string" ? search.champion : undefined;

  return (
    <Container className="py-8">
      <CounterTour />
      <div className="mb-1 flex items-center gap-3">
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Counter Builder</h1>
        <span className="rounded-md bg-emerald-400/20 px-2 py-1 text-[0.65rem] font-bold uppercase tracking-wide text-emerald-300">
          New
        </span>
        <span className="rounded-md bg-accent/20 px-2 py-1 text-[0.65rem] font-bold uppercase tracking-wide text-accent">
          Beta
        </span>
      </div>
      <p className="mb-6 max-w-xl text-sm text-muted">
        Pick your champion and the enemy team. It reads every enemy&rsquo;s damage type and kit,
        then builds the optimal loadout: items, purchase order, boots and runes, for that specific comp,
        with a complete evaluation of the final build.
      </p>
      <EnemyBuildAdvisor mode="counter" initialChampion={initialChampion} />

      <div className="mt-8">
        <StudioCta champion={initialChampion} />
      </div>
    </Container>
  );
}
