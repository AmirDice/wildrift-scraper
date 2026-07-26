"use client";

import { useMemo, useState } from "react";
import Link from "next/link";

/* eslint-disable @next/next/no-img-element */

export interface ChampionChangeListEntry {
  name: string;
  slug: string;
  icon: string;
  role: string;
  patch: string | null;
  changedAt: string | null;
  days: number | null;
  href?: string;
  note?: string;
}

function formatDate(value: string | null) {
  if (!value) return "No standard change recorded";
  return new Intl.DateTimeFormat("en", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(new Date(value));
}

export function ChampionChangeList({ entries }: { entries: ChampionChangeListEntry[] }) {
  const [query, setQuery] = useState("");
  const [role, setRole] = useState("All");
  const roles = useMemo(() => ["All", ...new Set(entries.map((entry) => entry.role).sort())], [entries]);
  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return entries.filter((entry) => (role === "All" || entry.role === role) && (!normalized || entry.name.toLowerCase().includes(normalized)));
  }, [entries, query, role]);

  return (
    <div>
      <div className="glass grid gap-3 rounded-2xl p-4 sm:grid-cols-[1fr_180px]">
        <label className="sr-only" htmlFor="change-search">Search champions</label>
        <input id="change-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search champions…" className="rounded-xl border border-line bg-black/20 px-4 py-3 text-sm outline-none transition placeholder:text-faint focus:border-accent/50" />
        <label className="sr-only" htmlFor="change-role">Filter by role</label>
        <select id="change-role" value={role} onChange={(event) => setRole(event.target.value)} className="rounded-xl border border-line bg-[#111827] px-4 py-3 text-sm outline-none focus:border-accent/50">
          {roles.map((value) => <option key={value} value={value}>{value === "All" ? "All roles" : value}</option>)}
        </select>
      </div>

      <div className="mt-3 flex items-center justify-between px-1 text-xs text-muted">
        <span>{filtered.length} champion{filtered.length === 1 ? "" : "s"}</span>
        <span>Longest unchanged first</span>
      </div>

      <div className="glass mt-3 overflow-hidden rounded-2xl border border-line">
        <div className="hidden grid-cols-[3rem_1fr_9rem_8rem] gap-3 border-b border-line px-5 py-3 text-[0.65rem] font-semibold uppercase tracking-wide text-faint sm:grid">
          <span>Rank</span><span>Champion</span><span>Last change</span><span className="text-right">Time unchanged</span>
        </div>
        <div className="divide-y divide-line/60">
          {filtered.map((entry) => {
            const rank = entries.findIndex((candidate) => candidate.slug === entry.slug) + 1;
            return (
              <div key={entry.slug} className="relative">
                {entry.href && <Link href={entry.href} aria-label={`Open ${entry.name}`} className="absolute inset-0 z-10 transition hover:bg-white/[0.04]" />}
                <div className="grid grid-cols-[2rem_2.75rem_1fr_auto] items-center gap-3 px-4 py-3 sm:grid-cols-[3rem_2.75rem_1fr_9rem_8rem] sm:px-5">
                <span className="text-center text-sm font-semibold text-faint">{rank}</span>
                <span className="h-11 w-11 overflow-hidden rounded-full ring-1 ring-white/10"><img src={entry.icon} alt="" width={44} height={44} className="h-full w-full scale-[1.12] object-cover" /></span>
                <span className="min-w-0"><strong className="block truncate text-sm">{entry.name}</strong><span className="block truncate text-xs text-muted">{entry.note ?? `${entry.role}${entry.patch ? ` · Patch ${entry.patch}` : " · No tracked standard change"}`}</span></span>
                <span className="hidden text-xs text-muted sm:block">{formatDate(entry.changedAt)}</span>
                <span className={`text-right text-sm font-semibold ${entry.days == null ? "text-muted" : "text-gold"}`}>{entry.days == null ? "Unknown" : `${entry.days.toLocaleString()} days`}</span>
                </div>
              </div>
            );
          })}
          {filtered.length === 0 && <p className="px-5 py-12 text-center text-sm text-muted">No champions match that search.</p>}
        </div>
      </div>
    </div>
  );
}
