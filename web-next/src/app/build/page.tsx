import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { BuildStudio } from "@/components/build-studio";
import { BuildsGeneratedPill } from "@/components/builds-counter";
import { BUILD_STUDIO_VERSION, BUILD_TOOLS_LIVE } from "@/lib/flags";
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
  // The studio seeds its state from these props ONCE, at mount. A quick-start
  // chip navigates to this same route with different params, which re-renders
  // the page but leaves the mounted studio's state untouched -- the click
  // "did nothing" until a hard refresh. Keying the studio by its seeds turns
  // that navigation into a remount, which is exactly what opening a different
  // setup means.
  const studioKey = JSON.stringify([initialChampion, initialTab, initialLab, hasConfig ? initialConfig : null]);
  return (
    <div className="build-studio-page no-plate min-h-screen overflow-x-clip">
      <div className="mx-auto max-w-[1280px] px-4 pb-14 pt-8 sm:px-6 sm:pt-10">
        <section className="glass relative overflow-hidden rounded-[1.75rem] border border-white/[0.11] p-5 shadow-[0_28px_90px_rgba(0,0,0,.28)] sm:p-7">
          <div aria-hidden className="absolute -right-20 -top-32 h-96 w-96 rounded-full bg-accent/12 blur-3xl" />
          <div aria-hidden className="absolute -bottom-24 left-[28%] h-56 w-56 rounded-full bg-emerald-400/[0.07] blur-3xl" />
          <div className="relative grid gap-6 lg:grid-cols-[1fr_auto] lg:items-end">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[0.62rem] font-bold uppercase tracking-[0.2em] text-accent">Build engine</span>
                <span className="rounded-full border border-emerald-300/20 bg-emerald-300/10 px-2.5 py-1 text-[0.6rem] font-bold uppercase tracking-[0.12em] text-emerald-300">New</span>
                <span className="rounded-full border border-white/[0.09] bg-white/[0.045] px-2.5 py-1 text-[0.6rem] font-bold uppercase tracking-[0.12em] text-muted">{BUILD_STUDIO_VERSION}</span>
              </div>
              <h1 className="mt-3 text-4xl leading-[0.95] tracking-[-0.05em] sm:text-[3.65rem]" style={{ fontFamily: "var(--font-sans)", fontWeight: 800 }}>Build Studio</h1>
              <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted sm:text-base">One champion. Three ways to solve the build.</p>
            </div>
            <div className="grid grid-cols-3 overflow-hidden rounded-2xl border border-white/[0.08] bg-black/15">
              {[["01", "Personal"], ["02", "Counter"], ["03", "Lab"]].map(([number, label], index) => (
                <div key={label} className={`min-w-[6.5rem] px-4 py-3 ${index ? "border-l border-white/[0.07]" : ""}`}>
                  <p className="text-[0.58rem] font-bold tracking-[0.16em] text-accent">{number}</p>
                  <p className="mt-1 text-xs font-semibold text-text">{label}</p>
                </div>
              ))}
            </div>
          </div>
          <div className="relative mt-6 flex flex-col gap-3 border-t border-white/[0.07] pt-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-3 text-sm">
              <span className="grid h-8 w-8 shrink-0 place-items-center rounded-xl border border-amber-300/20 bg-amber-300/10 text-amber-200">↻</span>
              <div>
                <p className="font-semibold text-amber-100">Engine maintenance</p>
                <p className="text-xs text-muted">Live generations may pause while recommendations update.</p>
              </div>
            </div>
            <BuildsGeneratedPill />
          </div>
        </section>

        <div className="build-studio-workspace mt-5">
          <BuildStudio key={studioKey} initialChampion={initialChampion} initialTab={initialTab} initialLab={initialLab} initialConfig={hasConfig ? initialConfig : undefined} />
        </div>
      </div>
    </div>
  );
}
