"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { Champion } from "@/lib/data";
import { TIER_ORDER, tierClass } from "@/lib/data";
import { ChampionAvatar } from "@/components/ui";

export function TierListView({
  champions,
  roles,
}: {
  champions: Champion[];
  roles: string[];
}) {
  const [role, setRole] = useState<string>("All roles");
  const options = ["All roles", ...roles];

  const buckets = useMemo(() => {
    const pool =
      role === "All roles" ? champions : champions.filter((c) => c.role === role);
    const tierOf = (c: Champion) => (role === "All roles" ? c.tier : c.tierRole);
    const map: Record<string, Champion[]> = {};
    for (const t of TIER_ORDER) map[t] = [];
    for (const c of [...pool].sort((a, b) => b.wr - a.wr)) {
      (map[tierOf(c)] ??= []).push(c);
    }
    return map;
  }, [role, champions]);

  return (
    <div>
      {/* Role filter */}
      <div className="mb-6 flex flex-wrap gap-2">
        {options.map((o) => (
          <button
            key={o}
            onClick={() => setRole(o)}
            className={`rounded-full px-4 py-1.5 text-sm font-medium transition ${
              role === o
                ? "bg-accent text-[#07121f]"
                : "glass glass-hover text-muted"
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
        {role === "All roles" ? (
          <p>
            <span className="font-medium text-text">Tier cutoffs</span> — confidence-adjusted
            win rate of each champion&rsquo;s top 50 players. GOD 63%+ · S 61–63% · A 59–61% ·
            B 57–59% · C 56–57% · Ass under 56%.
          </p>
        ) : (
          <p>
            <span className="font-medium text-text">Percentile cutoffs within {role}</span> —
            a single role&rsquo;s win-rate range is narrower than the whole pool, so tiers adapt
            to keep every tier populated.
          </p>
        )}
      </div>
    </div>
  );
}
