import type { Metadata } from "next";
import Link from "next/link";
import { buildChampions } from "@/lib/builds";
import { Container, ChampionAvatar } from "@/components/ui";

export const metadata: Metadata = {
  title: "Build Optimizer — Best Wild Rift Builds & Runes",
  description:
    "Optimized Wild Rift builds and rune pages per champion — balanced and max-burst one-shot builds with item order and situational swaps.",
  alternates: { canonical: "/build" },
};

export default function BuildIndex() {
  const champs = buildChampions();
  return (
    <Container className="py-12">
      <div className="flex items-center gap-3">
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Build Optimizer</h1>
        <span className="rounded-md bg-accent/20 px-2 py-1 text-xs font-bold uppercase tracking-wide text-accent">
          Beta
        </span>
      </div>
      <p className="mt-2 max-w-2xl text-muted">
        Optimized builds &amp; runes per champion — a <span className="text-accent">balanced</span>{" "}
        build and a <span className="text-bad">max-burst one-shot</span> build, with item order,
        rune pages, and situational swaps. Item-exclusivity rules enforced.
      </p>

      {champs.length === 0 ? (
        <p className="mt-8 text-muted">Builds are being generated…</p>
      ) : (
        <div className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {champs.map(({ slug, champion, builds }) => (
            <Link
              key={slug}
              href={`/build/${slug}`}
              className="glass glass-hover flex items-center gap-3 rounded-xl p-3"
            >
              <ChampionAvatar champion={champion} size={48} />
              <div className="min-w-0">
                <div className="truncate font-semibold">{champion.name}</div>
                <div className="truncate text-xs text-muted">
                  {champion.role} · {builds.damageProfile}
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}

      <p className="mt-8 text-xs text-faint">
        {champs.length} champion{champs.length === 1 ? "" : "s"} with optimized builds. More coming
        as the roster is processed.
      </p>
    </Container>
  );
}
