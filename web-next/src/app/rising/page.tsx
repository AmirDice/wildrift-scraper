import type { Metadata } from "next";
import Link from "next/link";
import { site } from "@/lib/data";
import { CN_META } from "@/lib/cn";
import { getMetaGaps } from "@/lib/gap";
import { Container } from "@/components/ui";
import { MetaGapView, type GapRow } from "@/components/meta-gap-view";

export const metadata: Metadata = {
  title: "Rising Picks | What China Is Playing Before the West",
  description:
    "Wild Rift champions China's top elo (Challenger+) rates far higher than EU does, a leading indicator of the meta. Plus the champions EU overrates that fall off against high-skill play.",
  alternates: { canonical: "/rising" },
};

export default function RisingPage() {
  const rows: GapRow[] = getMetaGaps().map((g) => ({
    slug: g.champion.slug,
    name: g.champion.name,
    icon: g.champion.icon,
    role: g.champion.role,
    isHard: g.champion.isHard,
    euWr: g.euWr,
    cnWr: g.cnWr,
    euTier: g.euTier,
    cnTier: g.cnTier,
    gap: g.gap,
    contest: g.contest,
    rising: g.rising,
  }));

  return (
    <Container className="py-12">
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">The Meta Gap</h1>
      <p className="mt-2 max-w-2xl text-muted">
        Where China&rsquo;s top elo (<span className="text-text">{CN_META.bracket}</span>) disagrees
        with EU. Because the highest CN bracket runs ahead of the West, a champion much stronger
        there is often <span className="text-text">rising</span>, worth learning before it hits your
        server. The reverse flags picks EU <span className="text-text">overrates</span>.
      </p>

      <div className="mt-8">
        <MetaGapView rows={rows} roles={site.roles} />
      </div>

      <div className="mt-8 max-w-2xl space-y-2 text-xs text-faint">
        <p>
          Each win rate is measured against its own server&rsquo;s average (EU is 50%-centred, CN on
          its own mean), so the gap isn&rsquo;t skewed by one server running hotter. &ldquo;Contest&rdquo;
          is CN pick% + ban%, how much the top bracket prioritises the champion.
        </p>
        <p>
          Prefer the raw side-by-side numbers? See the{" "}
          <Link href="/global" className="text-accent hover:underline">
            cross-server table
          </Link>
          . EU updated {site.collectedOn ?? "recently"}
          {CN_META.date ? ` · CN ${CN_META.date.replace(/(\d{4})(\d{2})(\d{2})/, "$1-$2-$3")}` : ""}.
        </p>
      </div>
    </Container>
  );
}
