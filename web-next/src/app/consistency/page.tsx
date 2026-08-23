import type { Metadata } from "next";
import Link from "next/link";
import { getGlobalChampions } from "@/lib/cn";
import { getSkillCeilingRows, topSkillCeilings } from "@/lib/regions";
import { Container, ChampionAvatar } from "@/components/ui";
import { WinrateScatter } from "@/components/winrate-scatter";

export const metadata: Metadata = {
  title: "Consistency & Skill Ceiling | Wild Rift Meta Chart",
  description:
    "Every Wild Rift champion plotted by win rate vs skill ceiling. Spot the reliably-strong picks, and the high-variance champions that only pay off with mastery.",
  alternates: { canonical: "/consistency" },
};

export default function ConsistencyPage() {
  // EU and NA blended, the same rule the videos use: a champion's ceiling is
  // the mean of its two regional gaps, and only where the two regions agree.
  // The EU-only chart put Lillia on top at a 48% win rate because one NA
  // account set her ceiling; blended and agreement-gated, she is not a data
  // point at all.
  const ceilings = getSkillCeilingRows();
  const blended = new Map(ceilings.filter((r) => r.agree).map((r) => [r.slug, r.blended]));
  const champions = getGlobalChampions().map((c) => ({ ...c, skillSpread: blended.get(c.slug) ?? null }));
  const dropped = ceilings.filter((r) => !r.agree).length;
  const top = topSkillCeilings(5);
  const bySlug = new Map(champions.map((c) => [c.slug, c]));
  return (
    <Container className="py-12">
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Consistency &amp; Skill Ceiling</h1>
      <p className="mt-2 max-w-2xl text-muted">
        Every champion by <span className="text-text">win rate</span> (how strong) and{" "}
        <span className="text-text">skill ceiling</span> (how much a champion&rsquo;s top mains
        out-perform the average), both averaged across <span className="text-text">EU and NA</span>.{" "}
        <span className="text-accent">Bottom-right</span> = reliably strong;{" "}
        <span className="text-gold">top-right</span> = strong but rewards mastery;
        the higher a champion sits, the more its win rate depends on the player. Hover any dot.
      </p>
      <div className="glass mt-8 rounded-2xl border border-line p-4 sm:p-5">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="text-lg font-semibold">Highest skill ceilings</h2>
          <span className="text-xs text-muted">EU + NA · wins above average on both boards</span>
        </div>
        <ol className="mt-3 grid gap-2 sm:grid-cols-5">
          {top.map((r, i) => (
            <li key={r.slug}>
              <Link href={`/champions/${r.slug}`} className="flex items-center gap-3 rounded-xl bg-white/[0.04] px-3 py-2 transition hover:bg-white/[0.08]">
                <span className="w-5 text-sm font-bold text-faint">#{i + 1}</span>
                {bySlug.get(r.slug) && <ChampionAvatar champion={bySlug.get(r.slug)!} size={36} showBadges={false} />}
                <span className="min-w-0">
                  <span className="block truncate text-sm font-semibold">{r.name}</span>
                  <span className="block text-xs text-muted">+{r.blended.toFixed(1)} · EU +{r.eu.toFixed(1)} · NA +{r.na.toFixed(1)}</span>
                </span>
              </Link>
            </li>
          ))}
        </ol>
      </div>
      <div className="mt-8">
        <WinrateScatter champions={champions} />
      </div>
      {dropped > 0 && (
        <p className="mt-3 text-xs text-muted">
          {dropped} champion{dropped === 1 ? "" : "s"} left off the chart: EU and NA measured
          ceilings more than 8 points apart, which on a 50-player board is one outlier account,
          not a ceiling.
        </p>
      )}
      <div className="mt-4 flex flex-wrap gap-3 text-xs text-muted">
        {/* same tier palette as every other chart (meta-charts TIER_COLOR) */}
        {[
          ["GOD", "#ff9d3c"],
          ["S", "#ff7f3a"],
          ["A", "#f3b400"],
          ["B", "#4f8dff"],
          ["C", "#8a92a6"],
          ["L", "#4a5266"],
        ].map(([t, col]) => (
          <span key={t} className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: col }} />
            {t}
          </span>
        ))}
      </div>
    </Container>
  );
}
