"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { Champion } from "@/lib/data";
import type { CnChampion } from "@/lib/cn";
import { ChampionAvatar, TierChip } from "@/components/ui";
import { RegionToggle, RegionComingSoon, type Region } from "@/components/region-toggle";

export type WinRateView = "highest" | "lowest" | "off-meta";

const VIEWS: { key: WinRateView; label: string; description: string }[] = [
  { key: "highest", label: "Highest", description: "The strongest win rates in the current sample." },
  { key: "lowest", label: "Lowest", description: "Champions currently struggling most in the tracked sample." },
  { key: "off-meta", label: "Off-meta", description: "Strong results without matching popularity or attention." },
];

export function WinRateExplorer({ eu, cn, roles, offMetaSlugs, initialView }: { eu: Champion[]; cn: CnChampion[]; roles: string[]; offMetaSlugs: string[]; initialView: WinRateView }) {
  const [view, setView] = useState<WinRateView>(initialView);
  const [region, setRegion] = useState<Region>("EU");
  const [role, setRole] = useState("All roles");
  const [query, setQuery] = useState("");
  const offMeta = useMemo(() => new Set(offMetaSlugs), [offMetaSlugs]);
  const active = region === "CN" ? cn : eu;

  const rows = useMemo(() => {
    let list = active.filter((champion) => role === "All roles" || champion.role === role);
    const normalized = query.trim().toLowerCase();
    if (normalized) list = list.filter((champion) => champion.name.toLowerCase().includes(normalized));
    if (view === "off-meta") {
      if (region === "EU") list = list.filter((champion) => offMeta.has(champion.slug));
      else {
        const picks = cn.map((champion) => champion.cnPickRate).sort((a, b) => a - b);
        const medianPick = picks[Math.floor(picks.length / 2)] ?? 0;
        list = list.filter((champion) => (champion as CnChampion).cnPickRate <= medianPick && champion.wr >= 50);
      }
    }
    return [...list].sort((left, right) => view === "lowest" ? left.wr - right.wr : right.wr - left.wr);
  }, [active, cn, offMeta, query, region, role, view]);

  return (
    <div>
      <div className="glass rounded-2xl p-4 sm:p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="flex flex-wrap gap-2" role="tablist" aria-label="Win rate view">
            {VIEWS.map((option) => <button key={option.key} type="button" role="tab" aria-selected={view === option.key} onClick={() => setView(option.key)} className={`rounded-xl px-4 py-2 text-sm font-semibold transition ${view === option.key ? "bg-accent text-[#07121f]" : "bg-white/[0.05] text-muted hover:text-text"}`}>{option.label}</button>)}
          </div>
          <RegionToggle region={region} onChange={(value) => { setRegion(value); setRole("All roles"); }} />
        </div>
        <p className="mt-3 text-sm text-muted">{VIEWS.find((option) => option.key === view)?.description}</p>
      </div>

      {region === "NA" ? <div className="mt-5"><RegionComingSoon region="NA" /></div> : <>
        <div className="mt-5 grid gap-3 sm:grid-cols-[1fr_180px]">
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search champions…" className="glass rounded-xl px-4 py-3 text-sm outline-none placeholder:text-faint focus:border-accent/50" />
          <select value={role} onChange={(event) => setRole(event.target.value)} className="rounded-xl border border-line bg-[#111827] px-4 py-3 text-sm outline-none focus:border-accent/50"><option>All roles</option>{roles.map((value) => <option key={value}>{value}</option>)}</select>
        </div>
        <div className="mt-3 flex justify-between text-xs text-muted"><span>{rows.length} champions</span><span>{region} · {view === "off-meta" ? "low popularity, strong results" : "win-rate order"}</span></div>

        <div className="mt-3 overflow-hidden rounded-2xl border border-line bg-white/[0.025]">
          <div className="hidden grid-cols-[3rem_1fr_7rem_7rem_7rem] gap-3 border-b border-line px-5 py-3 text-[0.65rem] font-semibold uppercase tracking-wide text-faint sm:grid"><span>Rank</span><span>Champion</span><span>Role</span><span className="text-center">Tier</span><span className="text-right">Win rate</span></div>
          <div className="divide-y divide-line/60">{rows.map((champion, index) => <Link key={champion.slug} href={`/champions/${champion.slug}`} className="grid grid-cols-[2rem_2.75rem_1fr_auto] items-center gap-3 px-4 py-3 transition hover:bg-white/[0.04] sm:grid-cols-[3rem_2.75rem_1fr_7rem_7rem_7rem] sm:px-5"><span className="text-center text-sm font-semibold text-faint">{index + 1}</span><ChampionAvatar champion={champion} size={42} showBadges={false}/><span className="min-w-0"><strong className="block truncate text-sm">{champion.name}</strong><span className="text-xs text-muted sm:hidden">{champion.role} · {champion.class}</span></span><span className="hidden text-sm text-muted sm:block">{champion.role}</span><span className="hidden justify-center sm:flex"><TierChip tier={champion.tier}/></span><span className={`text-right font-semibold ${view === "lowest" ? "text-bad" : "text-accent"}`}>{champion.wr.toFixed(1)}%</span></Link>)}</div>
        </div>
      </>}
    </div>
  );
}
