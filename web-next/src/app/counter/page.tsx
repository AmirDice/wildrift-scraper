import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { EnemyBuildAdvisor } from "@/components/enemy-build";
import { Container } from "@/components/ui";
import { BUILD_TOOLS_LIVE } from "@/lib/flags";

export const metadata: Metadata = {
  title: "Counter Builder | WrTrueMeta",
  description: "Pick your champion and the enemy team, and get a full build — items, order, boots and runes — optimized for that specific comp.",
  robots: { index: false, follow: false },
};

export default function CounterPage() {
  if (!BUILD_TOOLS_LIVE) redirect("/");
  return (
    <Container className="py-8">
      <div className="mb-1 flex items-center gap-3">
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Counter Builder</h1>
        <span className="rounded-md bg-accent/20 px-2 py-1 text-[0.65rem] font-bold uppercase tracking-wide text-accent">
          Preview
        </span>
      </div>
      <p className="mb-6 max-w-xl text-sm text-muted">
        Pick your champion and the enemy team. It reads every enemy&rsquo;s damage type and kit
        and builds the full loadout — items, purchase order, boots and runes — for that specific comp,
        with an independent fight-engine score as a sanity check.
      </p>
      <EnemyBuildAdvisor />
    </Container>
  );
}
