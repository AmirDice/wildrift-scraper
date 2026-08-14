import type { Metadata } from "next";
import Link from "next/link";
import { site, getChampions, regionBoard } from "@/lib/data";
import { freshness } from "@/lib/patch-freshness";
import { getCnChampionsByBracket, getCnRolesByBracket, CN_META, getGlobalChampions, globalRoles } from "@/lib/cn";
import { Container } from "@/components/ui";
import { TierListView } from "@/components/tier-list-view";
import { CURRENT_PATCH } from "@/lib/patch";
import { NextStep } from "@/components/next-step";

// The patch belongs in the title: people search "wild rift tier list patch
// 7.2a", and a tier list with no patch on it reads as undated to both a
// searcher and a crawler. CURRENT_PATCH tracks the data, so this cannot drift.
export const metadata: Metadata = {
  title: `Wild Rift Tier List Patch ${CURRENT_PATCH} | EU, NA & China Win Rates`,
  description:
    `The Wild Rift tier list for patch ${CURRENT_PATCH}, combining real top-50 player win rates from EU and NA with official China server data from lolm.qq.com. Switch regions and filter by role from GOD to L tiers.`,
  alternates: { canonical: "/tier-list" },
  openGraph: {
    title: `Wild Rift Tier List Patch ${CURRENT_PATCH} | EU, NA & China Win Rates`,
    description: `Every Wild Rift champion ranked for patch ${CURRENT_PATCH} by the real win rates of its 50 best players across EU, NA and China.`,
    url: "https://wrtruemeta.com/tier-list",
  },
};

export default function TierListPage() {
  const champions = getChampions();
  return (
    <Container className="py-12">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
          Wild Rift Tier List
          {CURRENT_PATCH && <span className="text-muted"> · Patch {CURRENT_PATCH}</span>}
        </h1>
        <Link
          href="/consistency"
          className="glass glass-hover inline-flex items-center gap-1.5 rounded-full px-4 py-1.5 text-sm font-medium text-accent"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
            <rect x="3" y="12" width="4" height="8" rx="1" />
            <rect x="10" y="7" width="4" height="13" rx="1" />
            <rect x="17" y="3" width="4" height="17" rx="1" />
          </svg>
          Consistency chart
        </Link>
      </div>
      <p className="mt-2 max-w-2xl text-muted">
        Every Wild Rift champion ranked for {CURRENT_PATCH ? `patch ${CURRENT_PATCH}` : "the current patch"} by
        the confidence-adjusted win rate of their top players. Global averages our EU and NA top-50 measurements;
        switch to any one server, then filter by role for role-specific tiers.
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
          champions={champions}
          naChampions={regionBoard("NA").champions}
          naRoles={regionBoard("NA").roles}
          naUpdated={regionBoard("NA").collectedOn}
          euFreshness={freshness(site.collectedOn)}
          naFreshness={freshness(regionBoard("NA").collectedOn)}
          roles={site.roles}
          cnChampionsByBracket={getCnChampionsByBracket()}
          cnRolesByBracket={getCnRolesByBracket()}
          cnMeta={CN_META}
          globalChampions={getGlobalChampions()}
          globalRoles={globalRoles()}
          initialRegion="Global"
        />
      </div>
      <NextStep steps={["build", "counter", "meta"]} />

    </Container>
  );
}
