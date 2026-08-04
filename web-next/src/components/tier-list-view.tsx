"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { Champion } from "@/lib/data";
import type { CnBracketKey } from "@/lib/cn";
import { TIER_ORDER, tierClass, tierLabel, site } from "@/lib/data";
import { ChampionAvatar } from "@/components/ui";
import { RegionToggle, RegionComingSoon, type Region } from "@/components/region-toggle";
import { CURRENT_PATCH } from "@/lib/patch";
import { moverBySlug } from "@/lib/movers";
import { RegionUpdated } from "@/components/tierlist-updated";

export function TierListView({
  champions,
  roles,
  cnChampionsByBracket,
  cnRolesByBracket,
  cnMeta,
  globalChampions,
  globalRoles,
  initialRegion = "CN",
  initialCnBracket,
}: {
  champions: Champion[];
  roles: string[];
  cnChampionsByBracket: Record<CnBracketKey, Champion[]>;
  cnRolesByBracket: Record<CnBracketKey, string[]>;
  cnMeta: {
    source: string;
    date: string | null;
    bracket: string;
    defaultBracket: CnBracketKey;
    brackets: readonly {
      key: CnBracketKey;
      label: string;
      short: string;
      kind: "regular" | "legendary";
    }[];
  };
  globalChampions: Champion[];
  globalRoles: string[];
  initialCnBracket?: CnBracketKey;
  /** Which region the list opens on. The region tabs are client state, so this
   *  is what decides which ranking ends up in the server-rendered HTML -- and
   *  therefore which one a crawler can read. See /tier-list/china. */
  initialRegion?: Region;
}) {
  const [role, setRole] = useState<string>("All roles");
  const [region, setRegion] = useState<Region>(initialRegion);
  const [cnBracket, setCnBracket] = useState<CnBracketKey>(initialCnBracket ?? cnMeta.defaultBracket);

  const isCN = region === "CN";
  const isGlobal = region === "Global";
  const activeCnChampions = cnChampionsByBracket[cnBracket];
  const activeCnRoles = cnRolesByBracket[cnBracket];
  const activeChampions = isCN ? activeCnChampions : isGlobal ? globalChampions : champions;
  const activeRoles = isCN ? activeCnRoles : isGlobal ? globalRoles : roles;
  const activeCnBracket = cnMeta.brackets.find((option) => option.key === cnBracket)
    ?? cnMeta.brackets.find((option) => option.key === cnMeta.defaultBracket)!;
  const options = useMemo(() => ["All roles", ...activeRoles], [activeRoles]);

  const buckets = useMemo(() => {
    const inRole = options.includes(role) ? role : "All roles";
    const pool =
      inRole === "All roles" ? activeChampions : activeChampions.filter((c) => c.role === inRole);
    const tierOf = (c: Champion) => (inRole === "All roles" ? c.tier : c.tierRole);
    const map: Record<string, Champion[]> = {};
    for (const t of TIER_ORDER) map[t] = [];
    for (const c of [...pool].sort((a, b) => b.wr - a.wr)) {
      (map[tierOf(c)] ??= []).push(c);
    }
    return map;
  }, [role, activeChampions, options]);

  return (
    <div>
      {/* Region */}
      <div className="mb-5">
        <RegionToggle region={region} onChange={(next) => { setRegion(next); setRole("All roles"); }} regions={["CN", "EU", "NA", "Global"]} />
      </div>

      <div className="mb-5">
        <RegionUpdated region={region} euDate={site.collectedOn} cnDate={cnMeta.date} />
      </div>

      {region === "NA" ? (
        <RegionComingSoon region={region} />
      ) : (
        <>
          {isCN && (
            <div className="mb-5">
              {/* The region tabs are client state, not separate URLs, so this
                  heading is what tells a reader (and a crawler reading the
                  page) which tier list they are looking at and for which patch. */}
              <h2 className="text-lg font-semibold tracking-tight">
                Wild Rift China server tier list
                {CURRENT_PATCH && <span className="text-muted"> · Patch {CURRENT_PATCH}</span>}
              </h2>
              <p className="mt-1 text-sm text-muted">
                Official China server win rates from{" "}
                <span className="text-text">{activeCnBracket.label}</span>
                {activeCnBracket.kind === "legendary"
                  ? ", a separate high-elo solo queue"
                  : activeCnBracket.key === "3"
                    ? ", Tencent's top regular-ranked sample"
                    : ", a cumulative regular-ranked sample"}
                . Source: lolm.qq.com. China usually plays the patch ahead of the West, so this list is the
                earliest read on where the meta is going.
              </p>
              <div className="mt-4 flex flex-wrap gap-2" role="tablist" aria-label="China skill bracket">
                {cnMeta.brackets.map((option) => (
                  <button
                    key={option.key}
                    type="button"
                    role="tab"
                    aria-selected={cnBracket === option.key}
                    onClick={() => { setCnBracket(option.key); setRole("All roles"); }}
                    className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition ${
                      cnBracket === option.key
                        ? "bg-accent text-[#07121f]"
                        : "glass glass-hover text-muted"
                    }`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>
          )}
          {isGlobal && (
            <p className="mb-5 text-sm text-muted">
              Combined <span className="text-text">EU + CN Challenger</span> ranking of the champions
              strongest across both servers. See the full{" "}
              <Link href="/global" className="text-accent hover:underline">
                side-by-side comparison
              </Link>
              .
            </p>
          )}

          {/* Role filter */}
          <div className="mb-6 flex flex-wrap gap-2">
            {options.map((o) => (
              <button
                key={o}
                onClick={() => setRole(o)}
                className={`rounded-full px-4 py-1.5 text-sm font-medium transition ${
                  role === o ? "bg-accent text-[#07121f]" : "glass glass-hover text-muted"
                }`}
              >
                {o}
              </button>
            ))}
          </div>

          {/* Tiers */}
          <div className="flex flex-col gap-2.5">
            {TIER_ORDER.map((t) => {
              const champs = buckets[t] ?? [];
              if (champs.length === 0) return null;
              return (
                <div key={t} className="flex items-stretch gap-1.5 sm:gap-2.5">
                  <div
                    className={`grid w-11 shrink-0 place-items-center rounded-xl text-lg font-black sm:w-20 sm:text-2xl ${tierClass[t]}`}
                  >
                    {tierLabel(t)}
                  </div>
                  <div className="glass flex flex-1 flex-wrap content-center gap-x-1.5 gap-y-2 rounded-xl p-2 sm:gap-4 sm:p-4">
                    {champs.map((c) => {
                      const movementBracket = isGlobal ? cnMeta.defaultBracket : cnBracket;
                      const cnMovement = isCN || isGlobal ? moverBySlug(c.slug, movementBracket) : null;
                      // Global is the average of EU and CN. Until the EU data is
                      // refreshed, a CN move changes the combined score by half
                      // of the CN delta. EU itself deliberately gets no badge.
                      const mv = isGlobal && cnMovement
                        ? {
                            ...cnMovement,
                            oldWr: Math.round((c.wr - cnMovement.delta / 2) * 100) / 100,
                            newWr: c.wr,
                            delta: Math.round((cnMovement.delta / 2) * 100) / 100,
                          }
                        : isCN
                          ? cnMovement
                          : null;
                      const up = mv && mv.delta > 0;
                      const changed = Boolean(mv && Math.abs(mv.delta) >= 0.05);
                      return (
                        <Link
                          key={c.slug}
                          href={`/champions/${c.slug}`}
                          className="group flex w-[46px] flex-col items-center text-center transition sm:w-[68px]"
                          title={changed && mv
                            ? `${c.name} · ${c.wr.toFixed(1)}% WR · ${isGlobal ? "CN update impact on Global" : "previous CN scrape"} ${mv.oldWr}% → ${mv.newWr}% (${mv.delta > 0 ? "+" : ""}${mv.delta})`
                            : `${c.name} · ${c.wr.toFixed(1)}% WR`}
                        >
                          <span className="relative transition group-hover:-translate-y-0.5">
                            <ChampionAvatar champion={c} size={52} mobileSize={38} />
                            {changed && mv && (
                              <span className={`absolute -right-1.5 -top-1 rounded-full px-1 text-[0.55rem] font-bold text-white ring-1 ring-black/30 ${up ? "bg-emerald-500" : "bg-bad"}`}>
                                {up ? "▲" : "▼"}
                              </span>
                            )}
                          </span>
                          <span className="mt-1.5 w-full truncate text-[0.7rem] font-medium leading-tight">
                            {c.name}
                          </span>
                          <span className="text-[0.7rem] font-semibold text-accent">
                            {c.wr.toFixed(1)}%
                            {changed && mv && (
                              <span className={`ml-1 ${up ? "text-emerald-400" : "text-bad"}`}>
                                {up ? "+" : ""}{mv.delta}
                              </span>
                            )}
                          </span>
                        </Link>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Legend */}
          <div className="glass mt-6 rounded-xl p-4 text-sm text-muted">
            {isCN ? (
              <p>
                <span className="font-medium text-text">CN tier cutoffs</span>: official CN win
                rates centre on 50%, so tiers use a China-specific scale. GOD 53.5%+ · S 52–53.5% ·
                A 50.8–52% · B 49.5–50.8% · C 48–49.5% · L under 48%.
              </p>
            ) : isGlobal ? (
              <p>
                <span className="font-medium text-text">Global cutoffs</span>: the average of the
                EU and CN win rates (both 50%-centred). GOD 53.5%+ · S 52–53.5% · A 50.8–52% · B
                49.5–50.8% · C 48–49.5% · L under 48%.
              </p>
            ) : role === "All roles" ? (
              (() => {
                const o = site.wrOffset ?? 0;
                const c = (n: number) => (n + o).toFixed(1);
                return (
                  <p>
                    <span className="font-medium text-text">Win rate shown relative to average</span>:{" "}
                    every champion here is carried by its top-50 mains, so the pool naturally sits
                    high; we centre it so 50% = the average champion and you can read the gap at a
                    glance. Tier cutoffs: GOD {c(63)}%+ · S {c(61)}–{c(63)}% · A {c(59)}–{c(61)}% · B{" "}
                    {c(57)}–{c(59)}% · C {c(56)}–{c(57)}% · L under {c(56)}%.
                  </p>
                );
              })()
            ) : (
              <p>
                <span className="font-medium text-text">Percentile cutoffs within {role}</span>: a
                single role&rsquo;s win-rate range is narrower than the whole pool, so tiers adapt to
                keep every tier populated.
              </p>
            )}
          </div>
        </>
      )}
    </div>
  );
}
