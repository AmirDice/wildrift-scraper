import type { Metadata } from "next";
import Link from "next/link";
import { site } from "@/lib/data";
import { getEloSkews } from "@/lib/skew";
import { Container } from "@/components/ui";
import { EloSkewView, type SkewRow } from "@/components/elo-skew-view";
import { ChinaUpdated } from "@/components/tierlist-updated";

export const metadata: Metadata = {
  title: "Win Rate by Skill Bracket | Wild Rift China Rank Data",
  description:
    "Compare Wild Rift champion win rates across China's cumulative Diamond+, Master+, and Challenger samples, with CN Legendary shown as a separate solo-queue benchmark.",
  alternates: { canonical: "/ranks" },
};

export default function RanksPage() {
  const rows: SkewRow[] = getEloSkews().map((s) => ({
    slug: s.champion.slug,
    name: s.champion.name,
    icon: s.champion.icon,
    role: s.champion.role,
    isHard: s.champion.isHard,
    curve: s.curve,
    legendary: s.legendary,
    low: s.low,
    high: s.high,
    skew: s.skew,
    climbing: s.climbing,
    stomper: s.stomper,
  }));

  return (
    <Container className="py-12">
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Win Rate by Skill Bracket</h1>
      <p className="mt-2 max-w-2xl text-muted">
        Follow champion performance through Tencent&rsquo;s cumulative{" "}
        <span className="text-text">Diamond+ → Master+ → Challenger</span> samples. This is a
        skill-bracket comparison rather than isolated rank data: Diamond+ already contains the
        higher regular ranks. CN Legendary is shown separately as a high-elo solo-queue benchmark.
      </p>

      <div className="mt-4">
        <ChinaUpdated />
      </div>

      <div className="mt-8">
        <EloSkewView rows={rows} roles={site.roles} />
      </div>

      <div className="mt-8 max-w-2xl space-y-2 text-xs text-faint">
        <p>
          The sparkline runs Diamond+ → Master+ → Challenger. Change is Challenger minus Diamond+:
          positive means the champion performs better in Tencent&rsquo;s top regular-ranked sample.
          Legendary is a separate CN solo queue and is never treated as the next rank after Challenger.
        </p>
        <p>
          Want the cross-server view instead? See{" "}
          <Link href="/rising" className="text-accent hover:underline">
            the meta gap
          </Link>.
        </p>
      </div>
    </Container>
  );
}
