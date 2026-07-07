"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { Champion } from "@/lib/data";
import { TIER_ORDER, tierClass, site } from "@/lib/data";
import { ChampionAvatar } from "@/components/ui";
import { RegionToggle, RegionComingSoon, type Region } from "@/components/region-toggle";

export function TierListView({
  champions,
  roles,
  cnChampions,
  cnRoles,
  cnMeta,
  globalChampions,
  globalRoles,
}: {
  champions: Champion[];
  roles: string[];
  cnChampions: Champion[];
  cnRoles: string[];
  cnMeta: { source: string; date: string | null; bracket: string };
  globalChampions: Champion[];
  globalRoles: string[];
}) {
  const [role, setRole] = useState<string>("All roles");
  const [region, setRegion] = useState<Region>("EU");

  const isCN = region === "CN";
  const isGlobal = region === "Global";
  const activeChampions = isCN ? cnChampions : isGlobal ? globalChampions : champions;
  const activeRoles = isCN ? cnRoles : isGlobal ? globalRoles : roles;
  const options = ["All roles", ...activeRoles];

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
        <RegionToggle region={region} onChange={setRegion} regions={["EU", "CN", "Global", "NA"]} />
      </div>

      {region === "NA" ? (
        <RegionComingSoon region={region} />
      ) : (
        <>
          {isCN && (
            <p className="mb-5 text-sm text-muted">
              Official China server win rates from{" "}
              <span className="text-text">{cnMeta.bracket}</span> (highest rank)
              {cnMeta.date ? ` · updated ${cnMeta.date.replace(/(\d{4})(\d{2})(\d{2})/, "$1-$2-$3")}` : ""}
              . Source: lolm.qq.com.
            </p>
          )}
          {isGlobal && (
            <p className="mb-5 text-sm text-muted">
              Combined <span className="text-text">EU + CN</span> ranking — the champions strongest
              across both servers. See the full{" "}
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
                <div key={t} className="flex items-stretch gap-2.5">
                  <div
                    className={`grid w-16 shrink-0 place-items-center rounded-xl text-2xl font-black sm:w-20 ${tierClass[t]}`}
                  >
                    {t}
                  </div>
                  <div className="glass flex flex-1 flex-wrap content-center gap-3 rounded-xl p-3 sm:gap-4 sm:p-4">
                    {champs.map((c) => (
                      <Link
                        key={c.slug}
                        href={`/champions/${c.slug}`}
                        className="group flex w-[60px] flex-col items-center text-center transition sm:w-[68px]"
                        title={`${c.name} — ${c.wr.toFixed(1)}% WR`}
                      >
                        <span className="transition group-hover:-translate-y-0.5">
                          <ChampionAvatar champion={c} size={52} />
                        </span>
                        <span className="mt-1.5 w-full truncate text-[0.7rem] font-medium leading-tight">
                          {c.name}
                        </span>
                        <span className="text-[0.7rem] font-semibold text-accent">
                          {c.wr.toFixed(1)}%
                        </span>
                      </Link>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Legend */}
          <div className="glass mt-6 rounded-xl p-4 text-sm text-muted">
            {isCN ? (
              <p>
                <span className="font-medium text-text">CN tier cutoffs</span> — whole-ladder win
                rates centre on 50%, so tiers use a China-specific scale. GOD 53.5%+ · S 52–53.5% ·
                A 50.8–52% · B 49.5–50.8% · C 48–49.5% · Ass under 48%.
              </p>
            ) : isGlobal ? (
              <p>
                <span className="font-medium text-text">Global cutoffs</span> — the average of the
                EU and CN win rates (both 50%-centred). GOD 53.5%+ · S 52–53.5% · A 50.8–52% · B
                49.5–50.8% · C 48–49.5% · Ass under 48%.
              </p>
            ) : role === "All roles" ? (
              (() => {
                const o = site.wrOffset ?? 0;
                const c = (n: number) => (n + o).toFixed(1);
                return (
                  <p>
                    <span className="font-medium text-text">Win rate shown relative to average</span>{" "}
                    — every champion here is carried by its top-50 mains, so the pool naturally sits
                    high; we centre it so 50% = the average champion and you can read the gap at a
                    glance. Tier cutoffs: GOD {c(63)}%+ · S {c(61)}–{c(63)}% · A {c(59)}–{c(61)}% · B{" "}
                    {c(57)}–{c(59)}% · C {c(56)}–{c(57)}% · Ass under {c(56)}%.
                  </p>
                );
              })()
            ) : (
              <p>
                <span className="font-medium text-text">Percentile cutoffs within {role}</span> — a
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
