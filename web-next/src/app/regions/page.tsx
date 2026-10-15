import type { Metadata } from "next";
import Link from "next/link";
import { Container } from "@/components/ui";
import { RegionsView } from "@/components/regions-view";
import { getRegionRows, getDivergence, regionCoverage } from "@/lib/regions";
import { site, regionBoard } from "@/lib/data";
import { CN_META } from "@/lib/cn";
import { CURRENT_PATCH } from "@/lib/patch";
import { AdSlot } from "@/components/ad-slot";
import { ChinaAheadSection } from "@/components/merged/china-ahead-section";
import { BracketsSection } from "@/components/merged/brackets-section";

export const metadata: Metadata = {
  title: "Regions & Skill Brackets | EU vs NA vs China",
  description:
    "Where each Wild Rift champion is strong: EU vs NA vs China top-player win rates, the picks China plays before the West, and how win rates change from Diamond+ to Challenger.",
  alternates: { canonical: "/regions" },
};

export default function RegionsPage() {
  const rows = getRegionRows();
  const coverage = regionCoverage();
  const diverging = getDivergence();
  const naFavoured = diverging.filter((r) => (r.euNaGap ?? 0) > 0).slice(0, 3);
  const euFavoured = diverging.filter((r) => (r.euNaGap ?? 0) < 0).slice(0, 3);

  return (
    <Container className="py-12">
      <h1 id="top" className="scroll-mt-24 text-3xl font-semibold tracking-tight sm:text-4xl">
        EU vs NA vs China
      </h1>
      <p className="mt-2 max-w-3xl text-muted">
        The same champion, measured on three servers, on patch {CURRENT_PATCH}.{" "}
        <span className="text-text">EU</span> and <span className="text-text">NA</span> are read the
        same way -- the top players on each champion&rsquo;s leaderboard, each player&rsquo;s own
        win rate -- so a difference between them is a difference between the{" "}
        <span className="text-text">servers</span>, not between two ways of counting.
      </p>

      <nav aria-label="On this page" className="mt-5 flex flex-wrap gap-2 text-xs font-semibold">
        <a href="#top" className="rounded-full border border-line bg-white/[0.04] px-3 py-1.5 text-muted transition hover:border-accent/40 hover:text-text">By region</a>
        <a href="#china-ahead" className="rounded-full border border-line bg-white/[0.04] px-3 py-1.5 text-muted transition hover:border-accent/40 hover:text-text">China ahead of the West</a>
        <a href="#brackets" className="rounded-full border border-line bg-white/[0.04] px-3 py-1.5 text-muted transition hover:border-accent/40 hover:text-text">By skill bracket</a>
      </nav>

      {/* The honest caveat, stated before the numbers rather than under them. */}
      <div className="mt-5 glass rounded-2xl p-4 text-sm leading-relaxed text-muted">
        <p>
          <span className="font-semibold text-text">* China is a different measurement.</span>{" "}
          Those numbers are Tencent&rsquo;s own published {coverage.cnBracket} sample: the whole
          ladder population, not a cut of the top players. It is real signal about a third server, but an
          EU-vs-CN gap mixes the region with the method. Only the{" "}
          <span className="text-text">NA - EU</span> column isolates the region.
        </p>
        {coverage.na < coverage.eu && (
          <p className="mt-2">
            NA collection is still running: {coverage.na} of {coverage.total} champions so far,{" "}
            {coverage.euNaBoth} of them comparable with EU. Champions NA has not reached yet show{" "}
            <span className="text-faint">--</span> rather than a guess.
          </p>
        )}
      </div>

      {(naFavoured.length > 0 || euFavoured.length > 0) && (
        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          <div className="glass rounded-2xl p-4">
            <p className="text-[0.65rem] font-bold uppercase tracking-wide text-sky-300">
              Stronger on NA
            </p>
            <ul className="mt-2 space-y-1 text-sm">
              {naFavoured.map((r) => (
                <li key={r.slug} className="flex items-center justify-between gap-3">
                  <Link href={`/champions/${r.slug}`} className="font-medium hover:text-accent">
                    {r.name}
                  </Link>
                  <span className="tabular-nums text-muted">
                    {r.na!.toFixed(1)}% vs {r.eu!.toFixed(1)}%{" "}
                    <span className="font-semibold text-sky-300">+{r.euNaGap!.toFixed(1)}</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
          <div className="glass rounded-2xl p-4">
            <p className="text-[0.65rem] font-bold uppercase tracking-wide text-amber-300">
              Stronger on EU
            </p>
            <ul className="mt-2 space-y-1 text-sm">
              {euFavoured.map((r) => (
                <li key={r.slug} className="flex items-center justify-between gap-3">
                  <Link href={`/champions/${r.slug}`} className="font-medium hover:text-accent">
                    {r.name}
                  </Link>
                  <span className="tabular-nums text-muted">
                    {r.eu!.toFixed(1)}% vs {r.na!.toFixed(1)}%{" "}
                    <span className="font-semibold text-amber-300">{r.euNaGap!.toFixed(1)}</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      <AdSlot placement="inline" bare className="my-6" />
      <div className="mt-8">
        <RegionsView rows={rows} roles={site.roles} cnBracket={coverage.cnBracket} />
      </div>

      <p className="mt-6 text-sm text-muted">
        EU collected {site.collectedOn}; NA collected {regionBoard("NA").collectedOn}; China
        collected {regionBoard("CN").collectedOn}, with the bracket figures on this page updated
        daily from lolm.qq.com. For the combined ranking as tiers, see the{" "}
        <Link href="/tier-list" className="text-accent hover:underline">
          Global tier list
        </Link>
        .
      </p>

      {/* Merged 2026-10-16 from /rising and /ranks: one page for "where is
          this champion strong", by server and by rank. */}
      <ChinaAheadSection />
      <BracketsSection />
    </Container>
  );
}
