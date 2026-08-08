import type { Metadata } from "next";
import Link from "next/link";
import { site, getChampions, regionBoard } from "@/lib/data";
import { getCnChampionsByBracket, getCnRolesByBracket, CN_BRACKETS, CN_META, getGlobalChampions, globalRoles, type CnBracketKey } from "@/lib/cn";
import { Container } from "@/components/ui";
import { TierListView } from "@/components/tier-list-view";
import { CURRENT_PATCH } from "@/lib/patch";

/**
 * The China tier list, on its own URL.
 *
 * /tier-list has a China tab, but the region tabs are client state: the CN
 * ranking never reaches the server-rendered HTML, so no crawler has ever seen
 * it and it cannot rank for anything. This page renders the same view opened on
 * CN, which puts the China ranking in the HTML where it can be indexed.
 *
 * It is not a duplicate of /tier-list: different data (official China server
 * win rates from lolm.qq.com rather than EU top-50 players), different tier
 * cutoffs, and its own canonical.
 */
export const metadata: Metadata = {
  title: `Wild Rift China Tier List Patch ${CURRENT_PATCH} | CN Server Win Rates`,
  description:
    `The Wild Rift China server tier list for patch ${CURRENT_PATCH}, built from official lolm.qq.com Diamond+, Master+, Challenger, and Legendary win rates.`,
  alternates: { canonical: "/tier-list/china" },
  openGraph: {
    title: `Wild Rift China Tier List Patch ${CURRENT_PATCH}`,
    description:
      "Official China server Wild Rift win rates with selectable skill brackets, ranked into tiers.",
    url: "https://wrtruemeta.com/tier-list/china",
  },
};

export default async function ChinaTierListPage({
  searchParams,
}: {
  searchParams: Promise<{ bracket?: string }>;
}) {
  const requestedBracket = (await searchParams).bracket;
  const initialCnBracket: CnBracketKey = CN_BRACKETS.some(({ key }) => key === requestedBracket)
    ? requestedBracket as CnBracketKey
    : CN_META.defaultBracket;
  return (
    <Container className="py-12">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link href="/tier-list" className="text-sm text-muted transition hover:text-text">
          ← All regions tier list
        </Link>
        <Link href="/consistency" className="glass glass-hover rounded-full px-4 py-1.5 text-sm font-medium text-accent">
          Consistency chart
        </Link>
      </div>
      <h1 className="mt-4 text-3xl font-semibold tracking-tight sm:text-4xl">
        Wild Rift China Tier List
        {CURRENT_PATCH && <span className="text-muted"> · Patch {CURRENT_PATCH}</span>}
      </h1>
      <p className="mt-2 max-w-2xl text-muted">
        Every champion ranked by official China server win rates. Challenger is the default standard-ranked
        view; switch between Diamond+, Master+, Challenger, and the separate Legendary solo queue.
      </p>

      <Link
        href="/ranks"
        className="glass glass-hover mt-5 flex max-w-3xl flex-col gap-2 rounded-xl border border-gold/25 px-4 py-3 transition sm:flex-row sm:items-center sm:justify-between"
      >
        <span>
          <span className="block font-semibold text-text">Which champions reward mastery?</span>
          <span className="mt-0.5 block text-sm text-muted">See who gains or loses win rate across China&rsquo;s Diamond+, Master+, and Challenger samples.</span>
        </span>
        <span className="shrink-0 text-sm font-semibold text-gold">View skill-bracket trends →</span>
      </Link>

      <div className="mt-8">
        <TierListView
          champions={getChampions()}
          naChampions={regionBoard("NA").champions}
          naRoles={regionBoard("NA").roles}
          naUpdated={regionBoard("NA").collectedOn}
          roles={site.roles}
          cnChampionsByBracket={getCnChampionsByBracket()}
          cnRolesByBracket={getCnRolesByBracket()}
          cnMeta={CN_META}
          globalChampions={getGlobalChampions()}
          globalRoles={globalRoles()}
          initialRegion="CN"
          initialCnBracket={initialCnBracket}
        />
      </div>
    </Container>
  );
}
