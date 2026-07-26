import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { BuildStudio } from "@/components/build-studio";
import { Container } from "@/components/ui";
import { BUILD_TOOLS_LIVE } from "@/lib/flags";
import { buildToolsVisible } from "@/lib/access";

export const metadata: Metadata = {
  title: "Build Studio | Wild Rift Builds, Runes & Live Stats",
  description:
    "Optimized Wild Rift builds for every champion: pick your champion, switch playstyles, customize items and runes, or generate a build tuned to your exact game.",
  alternates: { canonical: "/build" },
  robots: BUILD_TOOLS_LIVE ? undefined : { index: false, follow: false },
};

export default async function BuildPage(props: PageProps<"/build">) {
  // Open once the tools launch, or right now for anyone holding a beta invite.
  if (!(await buildToolsVisible())) redirect("/");
  const search = await props.searchParams;
  const initialChampion = typeof search.champion === "string" ? search.champion : undefined;
  const initialTab = search.tab === "generate" ? "generate" as const : undefined;
  // Shared build links carry the playstyle variant so the recipient opens the
  // exact build that was shared, not the default one.
  const initialVariant = typeof search.variant === "string" ? search.variant : undefined;
  return (
    <Container className="py-8">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Build Studio</h1>
        <span className="rounded-md bg-emerald-400/20 px-2 py-1 text-[0.65rem] font-bold uppercase tracking-wide text-emerald-300">
          New
        </span>
        <span className="rounded-md bg-accent/20 px-2 py-1 text-[0.65rem] font-bold uppercase tracking-wide text-accent">
          Beta
        </span>
      </div>
      <p className="mb-6 mt-1 max-w-xl text-sm text-muted">
        Optimized builds for every champion. Pick your champion, switch playstyles,
        customize items and runes, or generate a build tuned to your exact game.
      </p>
      <BuildStudio initialChampion={initialChampion} initialTab={initialTab} initialVariant={initialVariant} />
    </Container>
  );
}
