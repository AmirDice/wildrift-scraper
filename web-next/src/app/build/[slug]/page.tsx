import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getBuild, buildChampions } from "@/lib/builds";
import { Container, ChampionAvatar } from "@/components/ui";
import { BuildView } from "@/components/build-view";

export function generateStaticParams() {
  return buildChampions().map((b) => ({ slug: b.slug }));
}

export async function generateMetadata(props: PageProps<"/build/[slug]">): Promise<Metadata> {
  const { slug } = await props.params;
  const data = getBuild(slug);
  if (!data) return { title: "Build not found" };
  const { champion } = data;
  const title = `${champion.name} Build & Runes — Wild Rift Optimizer`;
  const desc = `The best ${champion.name} build and runes in Wild Rift: balanced and max-burst one-shot builds with item order, situational swaps, and rune page.`;
  return {
    title,
    description: desc,
    alternates: { canonical: `/build/${champion.slug}` },
    openGraph: { title, description: desc, images: [champion.splash] },
    twitter: { card: "summary_large_image", title, description: desc, images: [champion.splash] },
  };
}

export default async function BuildPage(props: PageProps<"/build/[slug]">) {
  const { slug } = await props.params;
  const data = getBuild(slug);
  if (!data) notFound();
  const { champion, builds } = data;

  return (
    <>
      <section className="relative overflow-hidden border-b border-line">
        <div
          className="absolute inset-0 bg-cover opacity-40"
          style={{ backgroundImage: `url(${champion.splash})`, backgroundPosition: "center 22%" }}
        />
        <div className="absolute inset-0 bg-gradient-to-r from-bg via-bg/85 to-bg/30" />
        <div className="absolute inset-0 bg-gradient-to-t from-bg to-transparent" />
        <Container className="relative py-12">
          <Link href="/build" className="text-sm text-muted transition hover:text-text">
            ← All builds
          </Link>
          <div className="mt-5 flex items-center gap-4">
            <ChampionAvatar champion={champion} size={72} showBadges={false} />
            <div>
              <div className="flex items-center gap-2.5">
                <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
                  {champion.name} Build &amp; Runes
                </h1>
                <span className="rounded-md bg-accent/20 px-2 py-0.5 text-[0.65rem] font-bold uppercase tracking-wide text-accent">
                  Beta
                </span>
              </div>
              <p className="mt-1 text-muted">
                {champion.role} · {champion.class} ·{" "}
                <span className="text-accent">{builds.damageProfile}</span>
              </p>
            </div>
          </div>
        </Container>
      </section>

      <Container className="py-10">
        <BuildView data={builds} />
        <p className="mt-10 text-xs text-faint">
          Builds respect Wild Rift item-exclusivity rules (one item per shared unique passive).
          Damage build optimised for burst; balanced build trades some damage for survivability.
        </p>
      </Container>
    </>
  );
}
