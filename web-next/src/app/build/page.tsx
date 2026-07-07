import type { Metadata } from "next";
import Link from "next/link";
import { Container } from "@/components/ui";

export const metadata: Metadata = {
  title: "Build Optimizer (Coming Soon) | Wild Rift Builds & Runes",
  description:
    "A per-champion Wild Rift build & rune optimizer is on the way: balanced and max-burst one-shot builds with item order, situational swaps, and item-exclusivity rules.",
  alternates: { canonical: "/build" },
};

export default function BuildIndex() {
  return (
    <Container className="py-20">
      <div className="mx-auto max-w-xl text-center">
        <span className="inline-block rounded-full border border-accent/30 bg-accent/10 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-accent">
          Coming soon
        </span>
        <h1 className="mt-5 text-3xl font-semibold tracking-tight sm:text-4xl">Build Optimizer</h1>
        <p className="mt-4 text-muted">
          We&rsquo;re building a per-champion build &amp; rune optimizer: a{" "}
          <span className="text-accent">balanced</span> build and a{" "}
          <span className="text-bad">max-burst one-shot</span> build for every champion, with item
          order, rune pages, situational swaps, and Riot&rsquo;s item-exclusivity rules enforced.
        </p>
        <p className="mt-3 text-sm text-faint">
          Landing with the next patch. In the meantime, explore the tier list and champion data.
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <Link
            href="/tier-list"
            className="rounded-xl bg-accent px-5 py-2.5 font-semibold text-[#07121f] transition hover:brightness-110"
          >
            View the tier list
          </Link>
          <Link
            href="/champions"
            className="glass glass-hover rounded-xl px-5 py-2.5 font-semibold text-text"
          >
            Browse champions
          </Link>
        </div>
      </div>
    </Container>
  );
}
