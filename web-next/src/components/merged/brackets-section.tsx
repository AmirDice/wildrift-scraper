/** was /ranks, merged into /regions (2026-10-16): the page's own code, rendered as a section. */
import Link from "next/link";
import { site } from "@/lib/data";
import { getEloSkews } from "@/lib/skew";
import { EloSkewView, type SkewRow } from "@/components/elo-skew-view";
import { ChinaUpdated } from "@/components/tierlist-updated";


export function BracketsSection() {
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
    <section id="brackets" className="scroll-mt-24 pt-14">
      <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">Win Rate by Skill Bracket</h2>
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
          <Link href="#china-ahead" className="text-accent hover:underline">
            China ahead of the West
          </Link>{" "}above.
        </p>
      </div>

    </section>
  );
}
