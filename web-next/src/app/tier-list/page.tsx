import type { Metadata } from "next";
import { site, getChampions } from "@/lib/data";
import { Container } from "@/components/ui";
import { TierListView } from "@/components/tier-list-view";

export const metadata: Metadata = {
  title: "Wild Rift Tier List — EU Top 50 Player Win Rates",
  description:
    "The Wild Rift tier list ranked by real top-50 EU player win rates. Filter by role. GOD to Ass tiers, updated twice a month.",
  alternates: { canonical: "/tier-list" },
};

export default function TierListPage() {
  const champions = getChampions();
  return (
    <Container className="py-12">
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Tier List</h1>
      <p className="mt-2 max-w-2xl text-muted">
        Champions ranked by the confidence-adjusted win rate of their top 50 players. Filter by
        role for role-specific tiers.
        {site.collectedOn && (
          <span className="text-faint"> Data collected {site.collectedOn}.</span>
        )}
      </p>

      <div className="mt-5 grid gap-2 sm:grid-cols-2">
        <Notice>
          Every win rate is above 50% — these are each champion&rsquo;s <strong className="text-text">top-50 mains</strong>.
          Read the gap between champions, not the raw number.
        </Notice>
        <Notice>
          A higher win rate means that champion&rsquo;s average top player <strong className="text-text">carries more games</strong> —
          often down to difficulty, not that the champion is weak (e.g. Lee Sin).
        </Notice>
      </div>

      <div className="mt-8">
        <TierListView champions={champions} roles={site.roles} />
      </div>
    </Container>
  );
}

function Notice({ children }: { children: React.ReactNode }) {
  return (
    <div className="glass flex items-start gap-2.5 rounded-xl px-3.5 py-2.5 text-xs leading-relaxed text-muted">
      <span className="mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full bg-accent/20 text-[0.6rem] font-bold text-accent">
        i
      </span>
      <span>{children}</span>
    </div>
  );
}
