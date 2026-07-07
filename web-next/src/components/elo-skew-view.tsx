"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { BracketPoint } from "@/lib/skew";
import { BracketCurve } from "@/components/bracket-curve";

/* eslint-disable @next/next/no-img-element */

export type SkewRow = {
  slug: string;
  name: string;
  icon: string;
  role: string;
  isHard: boolean;
  curve: BracketPoint[];
  low: number;
  high: number;
  skew: number;
  climbing: boolean;
  stomper: boolean;
};

type Mode = "climbing" | "stomper";

function SkewBadge({ skew }: { skew: number }) {
  const up = skew >= 0;
  return (
    <span
      className={`inline-flex min-w-[3.2rem] items-center justify-center rounded-md px-1.5 py-0.5 text-sm font-bold tabular-nums ${
        up ? "bg-emerald-400/15 text-emerald-300" : "bg-rose-400/15 text-rose-300"
      }`}
    >
      {up ? "+" : "−"}
      {Math.abs(skew).toFixed(1)}
    </span>
  );
}

export function EloSkewView({ rows, roles }: { rows: SkewRow[]; roles: string[] }) {
  const [mode, setMode] = useState<Mode>("climbing");
  const [role, setRole] = useState("All roles");
  const options = ["All roles", ...roles];

  const view = useMemo(() => {
    let list =
      mode === "climbing"
        ? rows.filter((r) => r.climbing).sort((a, b) => b.skew - a.skew)
        : rows.filter((r) => r.stomper).sort((a, b) => a.skew - b.skew);
    if (role !== "All roles") list = list.filter((r) => r.role === role);
    return list;
  }, [rows, mode, role]);

  return (
    <div>
      {/* Mode toggle */}
      <div className="mb-4 inline-flex rounded-full border border-line p-1">
        {(
          [
            ["climbing", "Scales with elo"],
            ["stomper", "Falls off up top"],
          ] as [Mode, string][]
        ).map(([m, label]) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={`rounded-full px-4 py-1.5 text-sm font-medium transition ${
              mode === m ? "bg-accent text-[#07121f]" : "text-muted hover:text-text"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <p className="mb-4 max-w-2xl text-sm text-muted">
        {mode === "climbing" ? (
          <>
            High-skill specialists: their win rate <span className="text-emerald-300">climbs</span> from
            the whole ladder up to Challenger+. Rewarding to master, but expect a rough start.
          </>
        ) : (
          <>
            Low-elo stompers: strong across the ladder but they{" "}
            <span className="text-rose-300">fall off</span> against Challenger+ play. Great to climb
            with, less so at the top.
          </>
        )}
      </p>

      {/* Role filter */}
      <div className="mb-5 flex flex-wrap gap-2">
        {options.map((o) => (
          <button
            key={o}
            onClick={() => setRole(o)}
            className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition ${
              role === o ? "bg-white/10 text-text" : "glass glass-hover text-muted"
            }`}
          >
            {o}
          </button>
        ))}
      </div>

      <div className="mb-2 flex items-center justify-between">
        <p className="text-sm text-faint">{view.length} champions</p>
        <p className="text-xs text-faint sm:hidden">swipe table →</p>
      </div>

      <div className="glass overflow-x-auto rounded-2xl">
        <table className="w-full min-w-[620px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
              <th className="w-12 px-3 py-3 text-center font-semibold">#</th>
              <th className="px-3 py-3 text-left font-semibold">Champion</th>
              <th className="px-3 py-3 text-center font-semibold">All → Challenger+</th>
              <th className="px-3 py-3 text-right font-semibold">All ranks</th>
              <th className="px-3 py-3 text-right font-semibold">Challenger+</th>
              <th className="px-3 py-3 text-right font-semibold">Skew</th>
            </tr>
          </thead>
          <tbody>
            {view.map((r, i) => (
              <tr
                key={r.slug}
                className="border-b border-line/60 transition last:border-0 hover:bg-white/[0.03]"
              >
                <td className="px-3 py-2.5 text-center text-faint">{i + 1}</td>
                <td className="px-3 py-2.5">
                  <Link
                    href={`/champions/${r.slug}`}
                    className="flex items-center gap-2.5 transition hover:text-accent"
                  >
                    <span
                      className={`h-8 w-8 shrink-0 overflow-hidden rounded-full ${
                        r.isHard ? "ring-2 ring-bad/70" : "ring-1 ring-white/10"
                      }`}
                    >
                      <img src={r.icon} alt="" width={32} height={32} loading="lazy" className="h-full w-full scale-[1.12] object-cover" />
                    </span>
                    <span>
                      <span className="font-medium">{r.name}</span>
                      <span className="block text-xs text-faint">{r.role}</span>
                    </span>
                  </Link>
                </td>
                <td className="px-3 py-2">
                  <div className="mx-auto w-[96px]">
                    <BracketCurve curve={r.curve} skew={r.skew} />
                  </div>
                </td>
                <td className={`px-3 py-2.5 text-right font-semibold ${r.low >= 50 ? "text-accent" : "text-muted"}`}>
                  {r.low.toFixed(1)}
                </td>
                <td className={`px-3 py-2.5 text-right font-semibold ${r.high >= 50 ? "text-accent" : "text-muted"}`}>
                  {r.high.toFixed(1)}
                </td>
                <td className="px-3 py-2.5 text-right">
                  <SkewBadge skew={r.skew} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {view.length === 0 && (
        <p className="glass mt-3 rounded-xl p-6 text-center text-muted">No champions in this role.</p>
      )}
    </div>
  );
}
