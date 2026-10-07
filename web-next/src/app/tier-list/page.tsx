import type { Metadata } from "next";
import Link from "next/link";
import { site, getChampions, regionBoard } from "@/lib/data";
import { freshness } from "@/lib/patch-freshness";
import { getCnChampionsByBracket, getCnRolesByBracket, CN_META, getGlobalChampions, globalRoles } from "@/lib/cn";
import { AdSlot } from "@/components/ad-slot";
import { TierListView } from "@/components/tier-list-view";
import { CURRENT_PATCH } from "@/lib/patch";
import { NextStep } from "@/components/next-step";

// The patch belongs in the title: people search "wild rift tier list patch
// 7.2a", and a tier list with no patch on it reads as undated to both a
// searcher and a crawler. CURRENT_PATCH tracks the data, so this cannot drift.
export const metadata: Metadata = {
  title: `Wild Rift Tier List Patch ${CURRENT_PATCH} | EU, NA & China Win Rates`,
  description:
    `The Wild Rift tier list for patch ${CURRENT_PATCH}, combining real top-player win rates from EU and NA with official China server data from lolm.qq.com. Switch regions and filter by role from GOD to L tiers.`,
  alternates: { canonical: "/tier-list" },
  openGraph: {
    title: `Wild Rift Tier List Patch ${CURRENT_PATCH} | EU, NA & China Win Rates`,
    description: `Every Wild Rift champion ranked for patch ${CURRENT_PATCH} by the real win rates of its best players across EU, NA and China.`,
    url: "https://wrtruemeta.com/tier-list",
  },
};

export default function TierListPage() {
  const champions = getChampions();
  return (
    <div
      className="tierlist-revamp no-plate min-h-screen overflow-x-clip"
      style={{ background: "linear-gradient(180deg, rgba(8,19,33,.84), rgba(6,15,29,.92))" }}
    >
      <div className="mx-auto max-w-[1280px] px-4 pb-12 pt-8 sm:px-6 sm:pt-10">
        <section className="glass relative overflow-hidden rounded-[1.75rem] border border-white/[0.11] px-5 py-6 shadow-[0_26px_90px_rgba(0,0,0,.32)] sm:px-7 sm:py-7">
          <div aria-hidden className="absolute -right-24 -top-32 h-80 w-80 rounded-full bg-accent/10 blur-3xl" />
          <div className="relative grid gap-7 lg:grid-cols-[1fr_auto] lg:items-end">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[0.62rem] font-bold uppercase tracking-[0.2em] text-accent">Every champion · ranked</span>
                {CURRENT_PATCH && <span className="rounded-full border border-white/[0.09] bg-white/[0.045] px-2.5 py-1 text-[0.62rem] font-bold uppercase tracking-[0.12em] text-muted">Patch {CURRENT_PATCH}</span>}
              </div>
              <h1 className="mt-3 text-4xl leading-[0.98] tracking-[-0.045em] sm:text-[3.35rem]" style={{ fontFamily: "var(--font-sans)", fontWeight: 800 }}>Wild Rift Tier List</h1>
              <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted sm:text-base">Real top-player performance across Global, EU, NA and China. Switch server, role or player depth without leaving the board.</p>
            </div>
            <div className="grid grid-cols-3 overflow-hidden rounded-2xl border border-white/[0.08] bg-black/15">
              <TierMetric label="Champions" value={champions.length.toString()} />
              <TierMetric label="Regions" value="3" bordered />
              <TierMetric label="Player pool" value="Top 50" bordered />
            </div>
          </div>
          <div className="relative mt-5 grid gap-2 border-t border-white/[0.07] pt-4 sm:grid-cols-2">
            <div className="flex items-center gap-3 rounded-xl bg-white/[0.025] px-3 py-2.5">
              <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-gold/10 text-gold">↻</span>
              <div className="min-w-0"><p className="text-xs font-semibold text-text">New-season schedule</p><p className="truncate text-[0.68rem] text-faint">Collected after one week, once samples stabilize.</p></div>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-white/[0.025] px-3 py-2.5">
              <div className="min-w-0"><p className="text-xs font-semibold text-text">Mastery curves</p><p className="truncate text-[0.68rem] text-faint">Diamond+ to Challenger performance.</p></div>
              <div className="flex items-center gap-3 text-xs font-semibold"><Link href="/ranks" className="text-gold hover:text-text">Ranks →</Link><Link href="/consistency" className="text-accent hover:text-text">Consistency →</Link></div>
            </div>
          </div>
        </section>

        <div className="mt-5">
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
        {/* Below the board. The longest page on the site, so the layout's bottom
            unit is thousands of pixels from anyone still reading here. */}
        <AdSlot placement="inline" bare className="my-10" />
        <NextStep steps={["build", "counter", "meta"]} />
      </div>
    </div>
  );
}

function TierMetric({ label, value, bordered = false }: { label: string; value: string; bordered?: boolean }) {
  return <div className={`min-w-[5.5rem] px-3 py-3 sm:min-w-[7rem] sm:px-4 ${bordered ? "border-l border-white/[0.07]" : ""}`}><p className="text-[0.55rem] font-bold uppercase tracking-[0.14em] text-faint">{label}</p><p className="mt-1 text-base font-semibold text-text sm:text-lg">{value}</p></div>;
}
