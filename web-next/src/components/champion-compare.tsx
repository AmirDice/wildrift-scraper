"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { Champion } from "@/lib/data";
import { TierChip } from "@/components/ui";
import { ChampionCombobox } from "@/components/champion-combobox";

/* eslint-disable @next/next/no-img-element */

type CnStat = { wr: number; pick: number; ban: number; tier: string };
type Counters = Record<string, { weak: string[]; strong: string[] }>;

const A_COLOR = "#4f8dff";
const B_COLOR = "#ffd76e";

/** numeric stats shown as diverging bars + fed into the radar */
const STATS: { label: string; short: string; get: (c: Champion, cn?: CnStat) => number | null; radar: boolean }[] = [
  { label: "Win rate (EU)", short: "WR", get: (c) => c.wr, radar: true },
  { label: "Win rate (CN)", short: "CN", get: (_c, cn) => cn?.wr ?? null, radar: false },
  { label: "Pick rate (CN)", short: "Pick", get: (_c, cn) => cn?.pick ?? null, radar: true },
  { label: "Ban rate (CN)", short: "Ban", get: (_c, cn) => cn?.ban ?? null, radar: true },
  { label: "Ceiling", short: "Ceiling", get: (c) => c.maxWr, radar: true },
  { label: "Skill ceiling", short: "Skill", get: (c) => c.skillSpread, radar: true },
];

function percentileFn(vals: number[]) {
  const sorted = [...vals].sort((a, b) => a - b);
  return (v: number) => {
    if (sorted.length <= 1) return 0.5;
    let lo = 0, hi = sorted.length;
    while (lo < hi) {
      const m = (lo + hi) >> 1;
      if (sorted[m] < v) lo = m + 1;
      else hi = m;
    }
    return lo / (sorted.length - 1);
  };
}

function ChampHeader({ c, color }: { c: Champion; color: string }) {
  return (
    <Link href={`/champions/${c.slug}`} className="group relative block overflow-hidden rounded-xl">
      <div className="absolute inset-0 bg-cover opacity-40 transition group-hover:opacity-50" style={{ backgroundImage: `url(${c.splash})`, backgroundPosition: "center 20%" }} />
      <div className="absolute inset-0 bg-gradient-to-t from-bg via-bg/70 to-transparent" />
      <div className="relative flex w-full flex-col items-center gap-1 p-3 text-center">
        <span className="h-12 w-12 overflow-hidden rounded-full sm:h-14 sm:w-14" style={{ boxShadow: `0 0 0 2px ${color}` }}>
          <img src={c.icon} alt={c.name} width={52} height={52} className="h-full w-full scale-[1.12] object-cover" />
        </span>
        <span className="mt-1 w-full truncate text-sm font-semibold sm:text-base">{c.name}</span>
        <span className="w-full truncate text-[0.7rem] text-muted">{c.role} · {c.class}</span>
        <TierChip tier={c.tier} />
      </div>
    </Link>
  );
}

function Radar({ a, b, cnA, cnB, pcts }: { a: Champion; b: Champion; cnA?: CnStat; cnB?: CnStat; pcts: ((v: number) => number)[] }) {
  const axes = STATS.filter((s) => s.radar);
  const N = axes.length;
  const W = 300, C = 150, R = 108;
  const pt = (i: number, r: number) => {
    const ang = (Math.PI * 2 * i) / N - Math.PI / 2;
    return [C + Math.cos(ang) * r, C + Math.sin(ang) * r];
  };
  const poly = (c: Champion, cn?: CnStat) =>
    axes.map((ax, i) => {
      const v = ax.get(c, cn);
      const n = v == null ? 0 : pcts[STATS.indexOf(ax)](v);
      return pt(i, R * Math.max(0.04, n)).join(",");
    }).join(" ");

  return (
    <svg viewBox={`0 0 ${W} ${W}`} className="mx-auto w-full max-w-[260px] sm:max-w-[300px]">
      {[0.25, 0.5, 0.75, 1].map((f) => (
        <polygon key={f} points={axes.map((_, i) => pt(i, R * f).join(",")).join(" ")} fill="none" stroke="rgba(255,255,255,0.08)" />
      ))}
      {axes.map((ax, i) => {
        const [x, y] = pt(i, R);
        const [lx, ly] = pt(i, R + 18);
        return (
          <g key={ax.short}>
            <line x1={C} y1={C} x2={x} y2={y} stroke="rgba(255,255,255,0.08)" />
            <text x={lx} y={ly} textAnchor="middle" dominantBaseline="middle" className="fill-faint" fontSize="10">{ax.short}</text>
          </g>
        );
      })}
      <polygon points={poly(a, cnA)} fill={A_COLOR} fillOpacity="0.18" stroke={A_COLOR} strokeWidth="2" />
      <polygon points={poly(b, cnB)} fill={B_COLOR} fillOpacity="0.15" stroke={B_COLOR} strokeWidth="2" />
    </svg>
  );
}

export function ChampionCompare({ champions, cn, counters }: { champions: Champion[]; cn: Record<string, CnStat>; counters: Counters }) {
  const options = useMemo(() => [...champions].sort((x, y) => x.name.localeCompare(y.name)).map((c) => ({ name: c.name, slug: c.slug, icon: c.icon })), [champions]);
  const bySlug = useMemo(() => new Map(champions.map((c) => [c.slug, c])), [champions]);
  const pcts = useMemo(
    () => STATS.map((s) => percentileFn(champions.map((c) => s.get(c, cn[c.slug])).filter((v): v is number => v != null))),
    [champions, cn]
  );

  const [slugA, setSlugA] = useState(champions[0]?.slug ?? "");
  const [slugB, setSlugB] = useState(champions[1]?.slug ?? "");
  const a = bySlug.get(slugA);
  const b = bySlug.get(slugB);
  const cnA = cn[slugA];
  const cnB = cn[slugB];

  const verdict = useMemo(() => {
    if (!a || !b) return { aw: 0, bw: 0 };
    let aw = 0, bw = 0;
    for (const s of STATS) {
      const va = s.get(a, cnA), vb = s.get(b, cnB);
      if (va == null || vb == null || va === vb) continue;
      if (va > vb) aw++; else bw++;
    }
    return { aw, bw };
  }, [a, b, cnA, cnB]);

  const matchup = useMemo(() => {
    if (!a || !b) return null;
    const ca = counters[a.slug], cb = counters[b.slug];
    if (ca?.strong?.includes(b.slug) || cb?.weak?.includes(a.slug)) return { winner: a, loser: b };
    if (ca?.weak?.includes(b.slug) || cb?.strong?.includes(a.slug)) return { winner: b, loser: a };
    return null;
  }, [a, b, counters]);

  return (
    <div>
      {/* Pickers */}
      <div className="grid grid-cols-2 gap-3 sm:gap-6">
        <ChampionCombobox champions={options} placeholder="First champion…" onSelect={setSlugA} />
        <ChampionCombobox champions={options} placeholder="Second champion…" onSelect={setSlugB} />
      </div>

      {a && b ? (
        <div className="mt-6 space-y-5">
          {/* Headers (always side by side) + verdict + radar */}
          <div className="glass rounded-2xl p-4 sm:p-5">
            <div className="grid grid-cols-2 gap-2.5 sm:gap-4">
              <ChampHeader c={a} color={A_COLOR} />
              <ChampHeader c={b} color={B_COLOR} />
            </div>
            <div className="my-4 text-center">
              <span className="text-[0.65rem] font-semibold uppercase tracking-wide text-faint">Head-to-head · </span>
              <span className="text-lg font-bold" style={{ color: A_COLOR }}>{verdict.aw}</span>
              <span className="mx-2 text-faint">—</span>
              <span className="text-lg font-bold" style={{ color: B_COLOR }}>{verdict.bw}</span>
              <span className="ml-1.5 text-[0.7rem] text-muted">stats won</span>
            </div>
            <Radar a={a} b={b} cnA={cnA} cnB={cnB} pcts={pcts} />
          </div>

          {/* Matchup callout */}
          {matchup && (
            <div className="glass flex items-center gap-3 rounded-xl border-l-2 border-accent/60 p-4 text-sm">
              <span className="h-9 w-9 shrink-0 overflow-hidden rounded-full ring-1 ring-white/15">
                <img src={matchup.winner.icon} alt="" className="h-full w-full scale-[1.12] object-cover" />
              </span>
              <p>
                <span className="font-semibold text-accent">{matchup.winner.name}</span> is generally{" "}
                <span className="font-semibold text-accent">strong against</span>{" "}
                <span className="font-semibold">{matchup.loser.name}</span> in lane.
              </p>
            </div>
          )}

          {/* Diverging stat bars */}
          <div className="glass rounded-2xl p-5">
            <div className="mb-4 flex items-center justify-center gap-6 text-xs font-semibold">
              <span style={{ color: A_COLOR }}>● {a.name}</span>
              <span style={{ color: B_COLOR }}>● {b.name}</span>
            </div>
            <div className="flex flex-col gap-3.5">
              {STATS.map((s) => {
                const va = s.get(a, cnA) ?? 0;
                const vb = s.get(b, cnB) ?? 0;
                const total = va + vb || 1;
                const aShare = (va / total) * 100;
                return (
                  <div key={s.label}>
                    <div className="mb-1 flex items-center justify-between text-xs">
                      <span className="font-semibold" style={{ color: va >= vb ? A_COLOR : "var(--color-muted)" }}>
                        {s.get(a, cnA) != null ? s.get(a, cnA)!.toFixed(1) : "—"}
                      </span>
                      <span className="text-faint">{s.label}</span>
                      <span className="font-semibold" style={{ color: vb >= va ? B_COLOR : "var(--color-muted)" }}>
                        {s.get(b, cnB) != null ? s.get(b, cnB)!.toFixed(1) : "—"}
                      </span>
                    </div>
                    <div className="flex h-2 overflow-hidden rounded-full bg-white/[0.06]">
                      <div style={{ width: `${aShare}%`, background: A_COLOR, opacity: 0.85 }} />
                      <div style={{ width: `${100 - aShare}%`, background: B_COLOR, opacity: 0.85 }} />
                    </div>
                  </div>
                );
              })}
            </div>

            {/* categorical rows */}
            <div className="mt-5 divide-y divide-line/60 border-t border-line/60 text-sm">
              {[
                { label: "Role", a: a.role, b: b.role },
                { label: "Class", a: a.class, b: b.class },
                { label: "Difficulty", a: a.difficultyLabel, b: b.difficultyLabel },
                { label: "Best player", a: a.bestPlayer?.player ?? "—", b: b.bestPlayer?.player ?? "—" },
              ].map((r) => (
                <div key={r.label} className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 py-2">
                  <span className="text-right text-muted">{r.a}</span>
                  <span className="w-24 text-center text-[0.7rem] uppercase tracking-wide text-faint">{r.label}</span>
                  <span className="text-left text-muted">{r.b}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <div className="glass mt-6 rounded-2xl p-10 text-center text-muted">Pick two champions to compare.</div>
      )}
    </div>
  );
}
