import type { Metadata } from "next";
import { getChampions } from "@/lib/data";
import { Container } from "@/components/ui";
import { WinrateScatter } from "@/components/winrate-scatter";

export const metadata: Metadata = {
  title: "Consistency & Skill Ceiling | Wild Rift Meta Chart",
  description:
    "Every Wild Rift champion plotted by win rate vs skill ceiling. Spot the reliably-strong picks, and the high-variance champions that only pay off with mastery.",
  alternates: { canonical: "/consistency" },
};

export default function ConsistencyPage() {
  const champions = getChampions();
  return (
    <Container className="py-12">
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Consistency &amp; Skill Ceiling</h1>
      <p className="mt-2 max-w-2xl text-muted">
        Every champion by <span className="text-text">win rate</span> (how strong) and{" "}
        <span className="text-text">skill ceiling</span> (how much a champion&rsquo;s top mains
        out-perform the average). <span className="text-accent">Bottom-right</span> = reliably strong;{" "}
        <span className="text-gold">top-right</span> = strong but rewards mastery (e.g. Lee Sin);
        the higher a champion sits, the more its win rate depends on the player. Hover any dot.
      </p>
      <div className="mt-8">
        <WinrateScatter champions={champions} />
      </div>
      <div className="mt-4 flex flex-wrap gap-3 text-xs text-muted">
        {[
          ["GOD", "#ffd76e"],
          ["S", "#7fd1ff"],
          ["A", "#4f8dff"],
          ["B", "#8aa0c0"],
          ["C", "#6b7890"],
          ["L", "#ff6a6a"],
        ].map(([t, col]) => (
          <span key={t} className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: col }} />
            {t}
          </span>
        ))}
      </div>
    </Container>
  );
}
