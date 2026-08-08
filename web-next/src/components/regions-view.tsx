"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { RegionRow } from "@/lib/regions";

type SortKey = "gap" | "eu" | "na" | "cn" | "average" | "name";
type Filter = "all" | "diverging" | "universal";

const num = (v: number | null) => (v == null ? -Infinity : v);

/** A win rate cell that is honest about a missing measurement. */
function WrCell({ wr, tier }: { wr: number | null; tier: string | null }) {
  if (wr == null) {
    return <td className="px-3 py-2 text-right text-faint" title="not collected yet">--</td>;
  }
  const tone = wr >= 52 ? "text-emerald-300" : wr <= 48 ? "text-bad" : "text-text";
  return (
    <td className="px-3 py-2 text-right tabular-nums">
      <span className={`font-semibold ${tone}`}>{wr.toFixed(1)}%</span>
      {tier && <span className="ml-1.5 text-[0.6rem] uppercase text-faint">{tier === "Ass" ? "L" : tier}</span>}
    </td>
  );
}

function GapCell({ gap }: { gap: number | null }) {
  if (gap == null) {
    return <td className="px-3 py-2 text-right text-faint">--</td>;
  }
  const strong = Math.abs(gap) >= 2.5;
  const tone = gap > 0 ? "text-sky-300" : "text-amber-300";
  return (
    <td className="px-3 py-2 text-right tabular-nums">
      <span className={`font-semibold ${tone} ${strong ? "" : "opacity-70"}`}>
        {gap > 0 ? "+" : ""}{gap.toFixed(1)}
      </span>
    </td>
  );
}

export function RegionsView({
  rows,
  roles,
  cnBracket,
}: {
  rows: RegionRow[];
  roles: string[];
  cnBracket: string;
}) {
  const [role, setRole] = useState("All roles");
  const [filter, setFilter] = useState<Filter>("diverging");
  const [sortKey, setSortKey] = useState<SortKey>("gap");
  const [dir, setDir] = useState<"asc" | "desc">("desc");

  const view = useMemo(() => {
    let list = rows;
    if (role !== "All roles") list = list.filter((r) => r.role === role);
    // Only champions BOTH we-measured servers have reached can be compared;
    // the others would sort as "no gap" and read as agreement.
    if (filter === "diverging") {
      list = list.filter((r) => r.euNaGap != null && Math.abs(r.euNaGap) >= 1.5);
    } else if (filter === "universal") {
      list = list.filter(
        (r) => r.sampled >= 2
          && [r.eu, r.na, r.cn].every((v) => v == null || v >= 50)
          && (r.eu ?? 0) >= 50,
      );
    }
    const key = (r: RegionRow) => {
      if (sortKey === "gap") return r.euNaGap == null ? -Infinity : Math.abs(r.euNaGap);
      if (sortKey === "name") return null;
      return num(r[sortKey]);
    };
    return [...list].sort((a, b) => {
      if (sortKey === "name") {
        const cmp = a.name.localeCompare(b.name);
        return dir === "asc" ? cmp : -cmp;
      }
      const cmp = (key(a) as number) - (key(b) as number);
      return dir === "asc" ? cmp : -cmp;
    });
  }, [rows, role, filter, sortKey, dir]);

  const toggleSort = (key: SortKey) => {
    if (key === sortKey) setDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setDir(key === "name" ? "asc" : "desc");
    }
  };

  const Th = ({ k, children, help }: { k: SortKey; children: React.ReactNode; help?: string }) => (
    <th
      onClick={() => toggleSort(k)}
      title={help}
      className={`cursor-pointer select-none px-3 py-2 text-right text-[0.65rem] font-bold uppercase tracking-wide transition hover:text-text ${
        sortKey === k ? "text-accent" : "text-faint"
      }`}
    >
      {children}
      {sortKey === k && <span className="ml-1">{dir === "asc" ? "▲" : "▼"}</span>}
    </th>
  );

  return (
    <div>
      <div className="mb-5 flex flex-wrap items-center gap-2">
        {(["diverging", "universal", "all"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition ${
              filter === f ? "bg-accent text-[#07121f]" : "glass glass-hover text-muted"
            }`}
          >
            {f === "diverging" ? "Region-specific" : f === "universal" ? "Strong everywhere" : "All champions"}
          </button>
        ))}
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        {["All roles", ...roles].map((o) => (
          <button
            key={o}
            onClick={() => setRole(o)}
            className={`rounded-full px-3 py-1.5 text-sm font-medium transition ${
              role === o ? "bg-accent text-[#07121f]" : "glass glass-hover text-muted"
            }`}
          >
            {o}
          </button>
        ))}
      </div>

      <p className="mb-3 text-sm text-faint">
        {view.length} champion{view.length === 1 ? "" : "s"}
        {filter === "diverging" && " with a 1.5-point or larger EU/NA difference"}
      </p>

      <div className="glass overflow-x-auto rounded-2xl">
        <table className="w-full min-w-[680px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-line">
              <th
                onClick={() => toggleSort("name")}
                className={`cursor-pointer select-none px-3 py-2 text-left text-[0.65rem] font-bold uppercase tracking-wide transition hover:text-text ${
                  sortKey === "name" ? "text-accent" : "text-faint"
                }`}
              >
                Champion
              </th>
              <Th k="eu" help="Top-50 players on the EU leaderboard">EU</Th>
              <Th k="na" help="Top-50 players on the NA leaderboard">NA</Th>
              <Th k="cn" help={`Tencent's published ${cnBracket} sample -- a different kind of measurement`}>
                CN*
              </Th>
              <Th k="gap" help="NA minus EU: the like-for-like regional difference">NA - EU</Th>
              <Th k="average" help="Mean of the servers that have measured this champion">Avg</Th>
            </tr>
          </thead>
          <tbody>
            {view.map((r) => (
              <tr key={r.slug} className="border-b border-line/40 transition hover:bg-white/[0.03]">
                <td className="px-3 py-2">
                  <Link href={`/champions/${r.slug}`} className="flex items-center gap-2.5 hover:text-accent">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={r.icon} alt="" width={30} height={30} className="rounded-md" loading="lazy" />
                    <span className="font-medium">{r.name}</span>
                    <span className="text-xs text-faint">{r.role}</span>
                  </Link>
                </td>
                <WrCell wr={r.eu} tier={r.euTier} />
                <WrCell wr={r.na} tier={r.naTier} />
                <WrCell wr={r.cn} tier={r.cnTier} />
                <GapCell gap={r.euNaGap} />
                <td className="px-3 py-2 text-right tabular-nums text-muted">
                  {r.average == null ? "--" : `${r.average.toFixed(1)}%`}
                  <span className="ml-1 text-[0.6rem] text-faint">{r.sampled}/3</span>
                </td>
              </tr>
            ))}
            {view.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-faint">
                  No champions match this filter yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
