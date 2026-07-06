"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { Champion } from "@/lib/data";
import { TIER_ORDER } from "@/lib/data";
import { TierChip } from "@/components/ui";
import { ChampionCombobox } from "@/components/champion-combobox";

/* eslint-disable @next/next/no-img-element */

type CnStat = { wr: number; pick: number; ban: number; tier: string };

type Metric = {
  label: string;
  /** higher value is better | lower is better | not comparable */
  better: "high" | "low" | "none";
  value: (c: Champion, cn?: CnStat) => number | null;
  render: (c: Champion, cn?: CnStat) => React.ReactNode;
};

const pct = (v: number | null) => (v == null ? "—" : `${v.toFixed(1)}%`);
const tierRank = (t: string) => {
  const i = TIER_ORDER.indexOf(t as (typeof TIER_ORDER)[number]);
  return i < 0 ? TIER_ORDER.length : i;
};

const METRICS: Metric[] = [
  { label: "Win rate (EU)", better: "high", value: (c) => c.wr, render: (c) => pct(c.wr) },
  {
    label: "Tier (EU)",
    better: "low",
    value: (c) => tierRank(c.tier),
    render: (c) => <TierChip tier={c.tier} />,
  },
  { label: "Win rate (CN)", better: "high", value: (_c, cn) => cn?.wr ?? null, render: (_c, cn) => pct(cn?.wr ?? null) },
  { label: "Pick rate (CN)", better: "high", value: (_c, cn) => cn?.pick ?? null, render: (_c, cn) => pct(cn?.pick ?? null) },
  { label: "Ban rate (CN)", better: "none", value: (_c, cn) => cn?.ban ?? null, render: (_c, cn) => pct(cn?.ban ?? null) },
  { label: "Ceiling (best main)", better: "high", value: (c) => c.maxWr, render: (c) => pct(c.maxWr) },
  { label: "Skill ceiling", better: "high", value: (c) => c.skillSpread, render: (c) => (c.skillSpread != null ? `+${c.skillSpread.toFixed(1)}` : "—") },
  { label: "Games (top 50)", better: "none", value: (c) => c.totalGames, render: (c) => (c.totalGames != null ? c.totalGames.toLocaleString() : "—") },
  { label: "Role", better: "none", value: () => null, render: (c) => c.role },
  { label: "Class", better: "none", value: () => null, render: (c) => c.class },
  { label: "Difficulty", better: "none", value: () => null, render: (c) => <span className={c.isHard ? "text-bad" : ""}>{c.difficultyLabel}</span> },
  { label: "Best player", better: "none", value: () => null, render: (c) => c.bestPlayer?.player ?? "—" },
];

function ChampHeader({ c }: { c: Champion }) {
  return (
    <Link href={`/champions/${c.slug}`} className="flex flex-col items-center gap-2 text-center transition hover:opacity-90">
      <img
        src={c.icon}
        alt={c.name}
        width={64}
        height={64}
        className={`h-16 w-16 rounded-full object-cover ${c.isHard ? "ring-2 ring-bad/70" : "ring-1 ring-white/15"}`}
      />
      <span className="font-semibold">{c.name}</span>
      <span className="text-xs text-muted">{c.role} · {c.class}</span>
    </Link>
  );
}

export function ChampionCompare({
  champions,
  cn,
}: {
  champions: Champion[];
  cn: Record<string, CnStat>;
}) {
  const options = useMemo(
    () => [...champions].sort((a, b) => a.name.localeCompare(b.name)).map((c) => ({ name: c.name, slug: c.slug, icon: c.icon })),
    [champions]
  );
  const bySlug = useMemo(() => new Map(champions.map((c) => [c.slug, c])), [champions]);

  const [slugA, setSlugA] = useState(champions[0]?.slug ?? "");
  const [slugB, setSlugB] = useState(champions[1]?.slug ?? "");
  const a = bySlug.get(slugA);
  const b = bySlug.get(slugB);
  const cnA = cn[slugA];
  const cnB = cn[slugB];

  return (
    <div>
      {/* Pickers */}
      <div className="grid grid-cols-2 gap-3 sm:gap-6">
        <ChampionCombobox champions={options} placeholder="First champion…" onSelect={setSlugA} />
        <ChampionCombobox champions={options} placeholder="Second champion…" onSelect={setSlugB} />
      </div>

      {a && b ? (
        <div className="glass mt-6 overflow-hidden rounded-2xl">
          {/* Headers */}
          <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 border-b border-line p-5">
            <ChampHeader c={a} />
            <span className="text-xs font-bold uppercase tracking-wide text-faint">vs</span>
            <ChampHeader c={b} />
          </div>

          {/* Metric rows */}
          <div className="divide-y divide-line/60">
            {METRICS.map((m) => {
              const va = m.value(a, cnA);
              const vb = m.value(b, cnB);
              let winA = false, winB = false;
              if (m.better !== "none" && va != null && vb != null && va !== vb) {
                const aWins = m.better === "high" ? va > vb : va < vb;
                winA = aWins;
                winB = !aWins;
              }
              return (
                <div key={m.label} className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 px-5 py-2.5 text-sm">
                  <div className={`text-right font-semibold ${winA ? "text-accent" : "text-muted"}`}>
                    {m.render(a, cnA)}
                  </div>
                  <div className="w-28 text-center text-[0.7rem] font-medium uppercase tracking-wide text-faint sm:w-40">
                    {m.label}
                  </div>
                  <div className={`text-left font-semibold ${winB ? "text-accent" : "text-muted"}`}>
                    {m.render(b, cnB)}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <div className="glass mt-6 rounded-2xl p-10 text-center text-muted">Pick two champions to compare.</div>
      )}
    </div>
  );
}
