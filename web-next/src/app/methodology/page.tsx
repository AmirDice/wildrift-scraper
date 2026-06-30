import type { Metadata } from "next";
import { site } from "@/lib/data";
import { Container, Card } from "@/components/ui";

export const metadata: Metadata = {
  title: "Methodology — How WrTrueMeta Calculates Win Rates",
  description:
    "How WrTrueMeta turns the top 50 players of every Wild Rift champion into a fair tier list: Bayesian shrinkage, Wilson best-player scores, and adaptive games floors.",
  alternates: { canonical: "/methodology" },
};

export default function MethodologyPage() {
  return (
    <Container className="py-12">
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Methodology</h1>
      <p className="mt-2 max-w-2xl text-muted">
        Every number on the site is computed the same way. Here&rsquo;s exactly how.
        {site.collectedOn && (
          <span className="text-faint"> Data collected {site.collectedOn}.</span>
        )}
      </p>

      <div className="mt-8 flex max-w-3xl flex-col gap-5">
        <Section title="Why every win rate is above 50%">
          We read the <strong className="text-text">top 50 players</strong> of each champion
          straight from the in-game leaderboard. These are mains at the highest level, so none of
          them has a losing record on the champion. The useful signal is the{" "}
          <strong className="text-text">gap between champions</strong>, not the raw number — a
          champion at 64% is meaningfully stronger at the top than one at 56%.
        </Section>

        <Section title="Confidence-adjusted win rate (Bayesian shrinkage)">
          A 5-game player at 80% isn&rsquo;t really an 80% champion. We pull every player&rsquo;s
          win rate toward the champion&rsquo;s own high-elo average by a fixed amount of synthetic
          evidence, so small samples are muted and large samples speak for themselves. A 10-game
          70% smurf lands near the average; a 400-game 60% main barely moves. The champion&rsquo;s
          score is the games-weighted mean of these adjusted rates.
        </Section>

        <Section title="Adaptive games floor">
          Play volume differs wildly per champion, so the entry bar scales with each
          champion&rsquo;s own median games rather than a global cutoff. A spammer can&rsquo;t own
          the number, and a niche pick&rsquo;s mains aren&rsquo;t unfairly excluded.
        </Section>

        <Section title="Best player (Wilson lower bound)">
          &ldquo;Best&rdquo; means demonstrably best, not luckily best. We rank each champion&rsquo;s
          players by the Wilson score lower bound — the conservative end of the 95% confidence
          interval for their true win rate. A 3-game 100% run scores low (huge uncertainty); a
          134-game 67% main scores high (tight interval).
        </Section>

        <Section title="Tiers">
          Champions are bucketed GOD · S · A · B · C · Ass by their confidence-adjusted win rate.
          The all-roles list uses fixed cutoffs (GOD 63%+, S 61–63%, A 59–61%, B 57–59%, C
          56–57%, Ass under 56%). When you filter to a single role, a role&rsquo;s narrower win-rate
          range means we switch to percentile cutoffs so every tier stays populated.
        </Section>

        <Section title="Updates">
          Data is refreshed roughly twice a month. Each refresh re-scrapes the top 50 players of
          every champion and recomputes everything above.
        </Section>
      </div>
    </Container>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card className="p-6">
      <h2 className="text-lg font-semibold">{title}</h2>
      <p className="mt-2 leading-relaxed text-muted">{children}</p>
    </Card>
  );
}
