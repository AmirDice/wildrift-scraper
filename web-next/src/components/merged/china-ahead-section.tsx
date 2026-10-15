/** was /rising, merged into /regions (2026-10-16): the page's own code, rendered as a section. */
import Link from "next/link";
import { site } from "@/lib/data";
import { CN_META } from "@/lib/cn";
import { getMetaGaps } from "@/lib/gap";
import { MetaGapView, type GapRow } from "@/components/meta-gap-view";
import { RegionUpdated } from "@/components/tierlist-updated";


export function ChinaAheadSection() {
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
    <section id="china-ahead" className="scroll-mt-24 pt-14">
      <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">China ahead of the West</h2>
      <p className="mt-2 max-w-2xl text-muted">
        Where China&rsquo;s top elo (<span className="text-text">{CN_META.bracket}</span>) disagrees
        with EU. Because the highest CN bracket runs ahead of the West, a champion much stronger
        there is often <span className="text-text">rising</span>, worth learning before it hits your
        server. The reverse flags picks EU <span className="text-text">overrates</span>.
      </p>

      <div className="mt-4">
        <RegionUpdated region="Global" euDate={site.collectedOn} cnDate={CN_META.date} />
      </div>
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
          <Link href="#top" className="text-accent hover:underline">
            region table at the top of this page
          </Link>
          .
        </p>
      </div>
    </section>
  );
}
