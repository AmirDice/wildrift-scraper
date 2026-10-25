import type { Metadata } from "next";
import Link from "next/link";
import { Container, Card } from "@/components/ui";

export const metadata: Metadata = {
  title: "Terms of Use",
  description: "The terms for using WrTrueMeta: what the data and the build tools are, what they are not, and the rules for accounts.",
  alternates: { canonical: "/terms" },
};

const UPDATED = "October 25, 2026";

/**
 * Plain-language terms of use. Written for what the site does today; paid
 * plans get their own section when they go on sale, together with the
 * operator details German law requires for selling to consumers.
 */
export default function TermsPage() {
  return (
    <Container className="py-12">
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Terms of use</h1>
      <p className="mt-2 max-w-2xl text-muted">Last updated {UPDATED}.</p>

      <div className="mt-8 flex max-w-3xl flex-col gap-5">
        <Section title="Using the site">
          Reading WrTrueMeta is free, and the Build Studio has a free daily allowance. By using
          the site you agree to these terms. If you do not agree, please do not use it.
        </Section>
        <Section title="What the data is">
          Win rates, tiers, builds and player statistics are measured from public leaderboards and
          published game data, and processed as described in the{" "}
          <Link href="/methodology" className="font-medium text-accent hover:opacity-80">methodology</Link>.
          They describe what has happened in ranked games. They are not a promise about what will
          happen in yours, and they can contain errors. If you find one, please{" "}
          <Link href="/contact" className="font-medium text-accent hover:opacity-80">tell us</Link>.
        </Section>
        <Section title="Generated builds">
          The Build Studio and Counter Builder use a language model to choose items and runes and a
          simulation engine to measure them. A generated build is a suggestion for you to judge, not
          advice you have to follow, and it can be wrong. Builds marked experimental are deliberately
          off the standard path.
        </Section>
        <Section id="credits" title="Build credits">
          Credits are optional one-time purchases that add Build Studio generations on top of the free
          daily allowance. One credit is one generation, spent only after the day&rsquo;s free
          generations are used; a generation that fails before it reaches the model gives its credit
          back. Credits do not expire, are tied to your Google sign-in and cannot be exchanged for money
          or moved to another account. The price is shown before you pay, and payments are processed
          by Stripe. <strong className="font-semibold text-text">Right of withdrawal:</strong> as a consumer in the EU you
          normally have 14 days to withdraw from a purchase. Credits are digital content delivered
          immediately, so before checkout you are asked to agree that they are added at once and that
          your right of withdrawal ends when they are; checkout is not possible without that agreement.
          If a payment is taken and no credits arrive, contact us and we will add them or refund you.
          The seller is named in the{" "}
          <Link href="/impressum" className="font-medium text-accent hover:opacity-80">Impressum</Link>.
        </Section>
        <Section title="WRTrueMeta Plus">
          Plus is an optional paid subscription that raises the daily Build Studio allowance. The
          price, billing period and the terms of the purchase, including your right of withdrawal,
          are shown before you pay. Payments are processed by Stripe, and you can cancel at any
          time from your account page; access continues until the end of the period already paid.
        </Section>
        <Section title="Accounts and fair use">
          Signing in with Google is optional and only raises your daily allowance of generations. Do
          not try to get around the daily limits, overload the site, or collect its data
          automatically in bulk. We may block access that does.
        </Section>
        <Section title="Content and trademarks">
          Wild Rift and League of Legends, their names, art and game data belong to Riot Games, Inc.
          WrTrueMeta is not affiliated with or endorsed by Riot Games or Tencent. The site&rsquo;s own
          text, statistics, charts and code may not be republished wholesale without permission;
          quoting and linking with credit is welcome.
        </Section>
        <Section title="Availability and liability">
          The site is provided as it is, without guarantees that it will always be available or
          error free. To the extent the law allows, we are not liable for losses arising from using
          it, such as a ranked game lost on a build it suggested.
        </Section>
        <Section title="Changes">
          These terms may change as the site does. The date at the top shows the latest version.
        </Section>
        <Section title="Privacy">
          How data about you is handled is described on the{" "}
          <Link href="/privacy" className="font-medium text-accent hover:opacity-80">privacy page</Link>.
        </Section>
      </div>
    </Container>
  );
}

function Section({ id, title, children }: { id?: string; title: string; children: React.ReactNode }) {
  return (
    <div id={id} className="scroll-mt-24">
      <Card className="p-5 sm:p-6">
        <h2 className="text-lg font-semibold">{title}</h2>
        <p className="mt-2 text-sm leading-relaxed text-muted">{children}</p>
      </Card>
    </div>
  );
}
