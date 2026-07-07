import type { Metadata } from "next";
import Link from "next/link";
import { site } from "@/lib/data";
import { CN_META } from "@/lib/cn";
import { getEloSkews } from "@/lib/skew";
import { Container } from "@/components/ui";
import { EloSkewView, type SkewRow } from "@/components/elo-skew-view";

export const metadata: Metadata = {
  title: "Win Rate by Rank — Low Elo vs High Elo Wild Rift Champions",
  description:
    "How Wild Rift champion win rates change from the whole ladder up to China's Sovereign bracket. Find high-skill specialists that scale with elo and low-elo stompers that fall off at the top.",
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
    low: s.low,
    high: s.high,
    skew: s.skew,
    climbing: s.climbing,
    stomper: s.stomper,
  }));

  return (
    <Container className="py-12">
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Win Rate by Rank</h1>
      <p className="mt-2 max-w-2xl text-muted">
        China publishes win rates for every rank bracket, from the whole ladder up to{" "}
        <span className="text-text">{CN_META.bracket}</span>. That skill gradient shows which
        champions <span className="text-emerald-300">scale with elo</span> (high-skill specialists)
        and which <span className="text-rose-300">fall off</span> against better players (low-elo
        stompers) — so you can pick what actually works at <em>your</em> rank.
      </p>

      <div className="mt-8">
        <EloSkewView rows={rows} roles={site.roles} />
      </div>

      <div className="mt-8 max-w-2xl space-y-2 text-xs text-faint">
        <p>
          The sparkline runs All ranks → Diamond+ → Master+ → Challenger → Sovereign. Skew is the
          Sovereign win rate minus the All-ranks win rate: positive means the champion gets stronger
          the higher you climb.
        </p>
        <p>
          Want the cross-server view instead? See{" "}
          <Link href="/rising" className="text-accent hover:underline">
            the meta gap
          </Link>
          {CN_META.date ? ` · CN ${CN_META.date.replace(/(\d{4})(\d{2})(\d{2})/, "$1-$2-$3")}` : ""}.
        </p>
      </div>
    </Container>
  );
}
