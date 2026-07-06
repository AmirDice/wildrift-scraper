"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { TierChip } from "@/components/ui";

/* eslint-disable @next/next/no-img-element */

export type Row = {
  slug: string;
  name: string;
  icon: string;
  role: string;
  isHard: boolean;
  euWr: number;
  euTier: string;
  cnWr: number;
  cnTier: string;
};

type SortKey = "global" | "euWr" | "cnWr" | "gap";

const avg = (r: Row) => (r.euWr + r.cnWr) / 2;
const gap = (r: Row) => Math.abs(r.euWr - r.cnWr);
const bothStrong = (r: Row) => r.euWr >= 50 && r.cnWr >= 50;

function Check({ className = "" }: { className?: string }) {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      <path d="M5 13l4 4L19 7" />
    </svg>
  );
}

export function CrossServerTable({ rows, roles }: { rows: Row[]; roles: string[] }) {
  const [role, setRole] = useState("All roles");
  const [onlyBoth, setOnlyBoth] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>("global");
  const [dir, setDir] = useState<"asc" | "desc">("desc");

  const options = ["All roles", ...roles];

  const view = useMemo(() => {
    let list = rows;
    if (role !== "All roles") list = list.filter((r) => r.role === role);
    if (onlyBoth) list = list.filter(bothStrong);
    const val = (r: Row) =>
      sortKey === "global" ? avg(r) : sortKey === "gap" ? gap(r) : r[sortKey];
    return [...list].sort((a, b) => {
      const cmp = val(a) - val(b);
      return dir === "asc" ? cmp : -cmp;
    });
  }, [rows, role, onlyBoth, sortKey, dir]);

  const toggleSort = (key: SortKey) => {
    if (key === sortKey) setDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setDir("desc");
    }
  };

  return (
    <div>
      {/* Filters */}
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2">
          {options.map((o) => (
            <button
              key={o}
              onClick={() => setRole(o)}
              className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition ${
                role === o ? "bg-accent text-[#07121f]" : "glass glass-hover text-muted"
              }`}
            >
              {o}
            </button>
          ))}
        </div>
        <button
          onClick={() => setOnlyBoth((v) => !v)}
          className={`inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-sm font-medium transition ${
            onlyBoth ? "bg-emerald-400/20 text-emerald-300" : "glass glass-hover text-muted"
          }`}
        >
          <Check /> Strong on both
        </button>
      </div>

      <div className="mb-2 flex items-center justify-between">
        <p className="text-sm text-faint">{view.length} champions</p>
        <p className="text-xs text-faint sm:hidden">swipe table →</p>
      </div>

      <div className="glass overflow-x-auto rounded-2xl">
        <table className="w-full min-w-[640px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
              <Th className="w-12 text-center">#</Th>
              <Th>Champion</Th>
              <Th>Role</Th>
              <Th onClick={() => toggleSort("euWr")} active={sortKey === "euWr"} dir={dir} right>
                EU
              </Th>
              <Th onClick={() => toggleSort("cnWr")} active={sortKey === "cnWr"} dir={dir} right>
                CN
              </Th>
              <Th onClick={() => toggleSort("global")} active={sortKey === "global"} dir={dir} right>
                Global
              </Th>
              <Th onClick={() => toggleSort("gap")} active={sortKey === "gap"} dir={dir} right>
                Gap
              </Th>
            </tr>
          </thead>
          <tbody>
            {view.map((r, i) => {
              const both = bothStrong(r);
              return (
                <tr
                  key={r.slug}
                  className={`border-b border-line/60 transition last:border-0 hover:bg-white/[0.03] ${
                    both ? "bg-emerald-400/[0.04]" : ""
                  }`}
                >
                  <td className="px-3 py-2.5 text-center text-faint">{i + 1}</td>
                  <td className="px-3 py-2.5">
                    <Link
                      href={`/champions/${r.slug}`}
                      className="flex items-center gap-2.5 transition hover:text-accent"
                    >
                      <img
                        src={r.icon}
                        alt=""
                        width={32}
                        height={32}
                        loading="lazy"
                        className={`h-8 w-8 rounded-full object-cover ${r.isHard ? "ring-2 ring-bad/70" : "ring-1 ring-white/10"}`}
                      />
                      <span className="font-medium">{r.name}</span>
                      {both && (
                        <span className="text-emerald-300" title="Strong on both servers">
                          <Check />
                        </span>
                      )}
                    </Link>
                  </td>
                  <td className="px-3 py-2.5 text-muted">{r.role}</td>
                  <td className="px-3 py-2.5 text-right">
                    <span className="inline-flex items-center gap-1.5">
                      <TierChip tier={r.euTier} />
                      <span className={`font-semibold ${r.euWr >= 50 ? "text-accent" : "text-muted"}`}>
                        {r.euWr.toFixed(1)}
                      </span>
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <span className="inline-flex items-center gap-1.5">
                      <TierChip tier={r.cnTier} />
                      <span className={`font-semibold ${r.cnWr >= 50 ? "text-accent" : "text-muted"}`}>
                        {r.cnWr.toFixed(1)}
                      </span>
                    </span>
                  </td>
                  <td className={`px-3 py-2.5 text-right font-bold ${avg(r) >= 50 ? "text-gold" : "text-muted"}`}>
                    {avg(r).toFixed(1)}
                  </td>
                  <td className="px-3 py-2.5 text-right text-faint">{gap(r).toFixed(1)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Th({
  children,
  onClick,
  active,
  dir,
  right,
  className = "",
}: {
  children: React.ReactNode;
  onClick?: () => void;
  active?: boolean;
  dir?: "asc" | "desc";
  right?: boolean;
  className?: string;
}) {
  const base = `px-3 py-3 font-semibold ${right ? "text-right" : "text-left"} ${className}`;
  if (!onClick) return <th className={base}>{children}</th>;
  return (
    <th className={base}>
      <button
        onClick={onClick}
        className={`inline-flex items-center gap-1 transition hover:text-text ${active ? "text-accent" : ""} ${right ? "flex-row-reverse" : ""}`}
      >
        {children}
        {active && <span className="text-[0.6rem]">{dir === "asc" ? "▲" : "▼"}</span>}
      </button>
    </th>
  );
}
