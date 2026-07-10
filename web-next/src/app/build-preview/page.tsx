import type { Metadata } from "next";
import { buildChampions } from "@/lib/builds";
import { BuildView } from "@/components/build-view";
import { BuildDial } from "@/components/build-dial";
import { BuildCustomizer } from "@/components/build-customizer";
import { Container, ChampionAvatar, TierChip } from "@/components/ui";

// Local review page for the build optimizer while /build is "coming soon".
// Renders every generated (validated) champion build on one scrollable page.
// Not linked in nav/sitemap; noindex.
export const metadata: Metadata = {
  title: "Build Optimizer Preview | WrTrueMeta",
  robots: { index: false, follow: false },
};

export default function BuildPreviewPage() {
  const champs = buildChampions();
  return (
    <Container className="py-12">
      <div className="flex items-center gap-3">
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Build Optimizer Preview</h1>
        <span className="rounded-md bg-accent/20 px-2 py-1 text-xs font-bold uppercase tracking-wide text-accent">
          Internal
        </span>
      </div>
      <p className="mt-2 max-w-2xl text-muted">
        Every validated build the generator produced, on one page. Public {"/build"} stays a
        &ldquo;coming soon&rdquo; placeholder until the full roster is generated on patch 7.2.
        Toggle each champion&rsquo;s variants to review items, boots, runes and one-shot flags.
      </p>
      <p className="mt-2 text-sm text-faint">{champs.length} champions with validated builds</p>

      <div className="mt-8 flex flex-col gap-8">
        {champs.map(({ slug, champion, builds }) => (
          <section key={slug} className="glass rounded-2xl p-5 sm:p-6">
            <div className="mb-5 flex flex-wrap items-center gap-3 border-b border-line pb-4">
              <ChampionAvatar champion={champion} size={52} showBadges={false} />
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <h2 className="text-xl font-bold">{champion.name}</h2>
                  <TierChip tier={champion.tier} />
                </div>
                <p className="text-sm text-muted">
                  {builds.class} · {builds.role} · {builds.damageProfile}
                  {builds.canOneshot ? " · can one-shot" : ""}
                </p>
              </div>
            </div>
            {(builds.dial ?? []).length > 0 && (
              <div className="mb-6">
                <BuildDial dial={builds.dial!} />
              </div>
            )}
            <BuildView data={builds} />
            <div className="mt-6">
              <BuildCustomizer name={champion.name} data={builds} />
            </div>
          </section>
        ))}
      </div>
    </Container>
  );
}
