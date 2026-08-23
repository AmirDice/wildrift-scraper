import type { Metadata } from "next";
import { site } from "@/lib/data";
import { Container, Card } from "@/components/ui";

export const metadata: Metadata = {
  title: "Methodology | How WrTrueMeta Calculates Win Rates",
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
        <Section title="Win rate shown relative to the average champion">
          We read the <strong className="text-text">top 50 players</strong> of each champion
          straight from the in-game leaderboard. These are mains at the highest level, so the raw
          win rates all sit above 50%, which reads oddly on a tier list. So we{" "}
          <strong className="text-text">centre the scale</strong>: the pool average becomes 50%, and
          a champion above or below that is above or below the average champion. Nothing about the
          ranking changes; it&rsquo;s a constant shift that just makes the{" "}
          <strong className="text-text">gap between champions</strong> easy to read. (A champion&rsquo;s
          best individual main, shown as the ceiling, stays a real win rate.)
        </Section>

        <Section title="Confidence-adjusted win rate (Bayesian shrinkage)">
          A 5-game player at 80% isn&rsquo;t really an 80% champion. We pull every player&rsquo;s
          win rate toward the champion&rsquo;s own high-elo average by a fixed amount of synthetic
          evidence, so small samples are muted and large samples speak for themselves. A 10-game
          70% smurf lands near the average; a 400-game 60% main barely moves. The champion&rsquo;s
          score is the games-weighted mean of these adjusted rates.
        </Section>

        <Section title="Boosting adverts and banned accounts">
          Two kinds of account get special handling, and they lose different things.{" "}
          <strong className="text-text">Accounts that advertise a boosting service in their own
          name</strong> keep their rank and their games count toward every statistic -- an
          advertising name says how an account is marketed, not how it is played, and many of
          the people advertising are simply good. What they lose is the name: rendering it on a
          public page is free marketing, so the board shows their rank with the name hidden, and
          they are never crowned best player or given a Hall of Fame record, because a title is
          a name. Detection is deliberately narrow and based only on what the account declares
          about itself, so ordinary players are never labelled.{" "}
          <strong className="text-text">Permanently banned accounts</strong> are the reverse:
          their name stays visible with a Permabanned tag, because hiding it would quietly
          rewrite the board, but their games are excluded from champion win rates, records and
          every other statistic. That list is curated by hand from in-game evidence -- nothing
          in a win rate alone proves misconduct, and we never infer a ban from performance.
        </Section>

        <Section title="Adaptive games floor">
          Play volume differs wildly per champion, so the entry bar scales with each
          champion&rsquo;s own median games rather than a global cutoff. A spammer can&rsquo;t own
          the number, and a niche pick&rsquo;s mains aren&rsquo;t unfairly excluded.
        </Section>

        <Section title="Best player (Wilson lower bound)">
          &ldquo;Best&rdquo; means demonstrably best, not luckily best. We rank each champion&rsquo;s
          players by the Wilson score lower bound, the conservative end of the 95% confidence
          interval for their true win rate. A 3-game 100% run scores low (huge uncertainty); a
          134-game 67% main scores high (tight interval).
        </Section>

        <Section title="Tiers">
          Champions are bucketed GOD · S · A · B · C · L by their confidence-adjusted win rate.
          The all-roles list uses fixed cutoffs (GOD 63%+, S 61–63%, A 59–61%, B 57–59%, C
          56–57%, L under 56%). When you filter to a single role, a role&rsquo;s narrower win-rate
          range means we switch to percentile cutoffs so every tier stays populated.
        </Section>

        <Section title="Roles">
          A champion&rsquo;s role comes from what its best players actually equip, not from a fixed
          list we maintain by hand. Someone carrying Smite was in the jungle; someone carrying a
          support item was the support. When a champion is genuinely played in two roles we compare
          how each group performs and go with the stronger one, so a champion that has quietly
          moved lanes follows the players rather than waiting for us to notice.
        </Section>

        <Section title="OTP score and player tags">
          The OTP score answers one question: how much of a player&rsquo;s ranked play is actually
          spent on this champion. If a champion&rsquo;s best players spend a large share of their
          games on it, that board is made of specialists. If they spread their time across many
          champions, it isn&rsquo;t, however hard the top few grind. The score is that share taken
          across the whole board, so it is a number you can read directly rather than an index.
          <br /><br />
          Three signals (that share, the win rate, and how much the champion is played) tend to
          fall into recognisable shapes, which we surface as tags.{" "}
          <strong className="text-text">OTP</strong> means the board really is specialists.{" "}
          <strong className="text-text">Comfort</strong> means heavily played and heavily
          specialised but winning below average: people pick it because they enjoy it.{" "}
          <strong className="text-text">Contested</strong> means a strong win rate with few games
          and few specialists, the shape of a champion people often cannot get. We do not hold
          ban data, so treat that one as a pattern rather than a fact.
        </Section>

        <Section title="Patch winners and losers">
          This compares the current numbers against a snapshot taken just before the patch went
          live, not against yesterday. Comparing two consecutive days would mostly measure daily
          noise; measuring from the patch itself is what tells you whether a change landed. The
          window therefore grows a little each day as new data arrives. This section reads the
          Chinese Challenger ladder, which updates daily, while the tier list is built from
          European data, so the two are answering different questions on purpose.
        </Section>

        <Section title="Updates">
          Data is refreshed roughly twice a month. Each refresh re-scrapes the top 50 players of
          every champion and recomputes everything above. The Chinese win rates behind the patch
          winners and losers refresh daily.
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
