import type { Metadata } from "next";
import { EnemyOptimizer } from "@/components/enemy-optimizer";
import { Container } from "@/components/ui";

export const metadata: Metadata = {
  title: "Counter Builder | WrTrueMeta",
  description: "Pick your champion and the enemy team, and get the exact items and runes that counter this specific comp — scored by a real fight engine.",
  robots: { index: false, follow: false },
};

export default function CounterPage() {
  return (
    <Container className="py-8">
      <div className="mb-1 flex items-center gap-3">
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Counter Builder</h1>
        <span className="rounded-md bg-accent/20 px-2 py-1 text-[0.65rem] font-bold uppercase tracking-wide text-accent">
          Preview
        </span>
      </div>
      <p className="mb-6 max-w-xl text-sm text-muted">
        Pick your champion and the enemy team. The engine reads every enemy&rsquo;s damage type
        and kit, then tells you exactly which items to swap in to beat this comp — and how much it helps.
      </p>
      <EnemyOptimizer />
    </Container>
  );
}
