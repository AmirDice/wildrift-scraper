import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { BuildStudio } from "@/components/build-studio";
import { Container } from "@/components/ui";
import { BuildsGeneratedPill } from "@/components/builds-counter";
import { BUILD_TOOLS_LIVE } from "@/lib/flags";
import { buildToolsVisible } from "@/lib/access";

export const metadata: Metadata = {
  title: "Build Studio | Optimal Wild Rift Builds, Runes & Live Stats",
  description:
    "Optimal Wild Rift builds for every champion: pick your champion, switch playstyles, customize items and runes, or generate the optimal build tuned to your exact game.",
  alternates: { canonical: "/build" },
  robots: BUILD_TOOLS_LIVE ? undefined : { index: false, follow: false },
};

export default async function BuildPage(props: PageProps<"/build">) {
  // Open once the tools launch, or right now for anyone holding a beta invite.
  if (!(await buildToolsVisible())) redirect("/");
  const search = await props.searchParams;
  const initialChampion = typeof search.champion === "string" ? search.champion : undefined;
  // ?tab=counter is what /counter redirects to, so every link that ever pointed
  // at the standalone Counter Builder still lands on the right tool.
  const initialTab = search.tab === "generate" ? "generate" as const
    : search.tab === "counter" ? "counter" as const
    : search.tab === "lab" ? "customize" as const
    : undefined;
  // ?items=slug,slug&runes=Name,Name imports a saved album build into the Lab.
  const initialLab = typeof search.items === "string" && search.items
    ? {
        items: search.items.split(",").filter(Boolean).slice(0, 8),
        runes: typeof search.runes === "string"
          ? search.runes.split(",").filter(Boolean).slice(0, 6)
          : [],
      }
    : undefined;
  // Prefill from album re-optimize links and quick-start chips. Seeds only.
  const BIAS_KEYS = new Set(["max_durability", "durability", "damage", "max_damage"]);
  const initialConfig = {
    playstyle: typeof search.variant === "string" ? search.variant.slice(0, 30) : undefined,
    role: typeof search.role === "string" ? search.role.slice(0, 20) : undefined,
    bias: typeof search.bias === "string" && BIAS_KEYS.has(search.bias) ? search.bias : undefined,
  };
  const hasConfig = Boolean(initialConfig.playstyle || initialConfig.role || initialConfig.bias);
  return (
    <Container className="py-8">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Build Studio</h1>
        <span className="rounded-md bg-emerald-400/20 px-2 py-1 text-[0.65rem] font-bold uppercase tracking-wide text-emerald-300">
          New
        </span>
        {/* Out of beta 2026-08-06: the full EU roster is collected and every
            generator behaviour on this page is validated and cache-versioned. */}
        <span className="rounded-md bg-accent/20 px-2 py-1 text-[0.65rem] font-bold uppercase tracking-wide text-accent">
          v1
        </span>
      </div>
      <p className="mt-1 max-w-xl text-sm text-muted">
        Optimal builds for every champion. Pick your champion, switch playstyles,
        customize items and runes, or generate the optimal build tuned to your exact game.
      </p>
      {/* The same live figure the home page shows. It belongs here too: this is
          the page where someone decides whether to spend a generation, and
          "other people are using this" is the most honest thing we can say at
          that moment. It refreshes on its own while the page is open. */}
      <div className="mb-6 mt-3">
        <BuildsGeneratedPill />
      </div>
      <BuildStudio initialChampion={initialChampion} initialTab={initialTab} initialLab={initialLab} initialConfig={hasConfig ? initialConfig : undefined} />
    </Container>
  );
}
