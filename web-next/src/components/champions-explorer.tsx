"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { Champion } from "@/lib/data";
import { TierChip, ChampionAvatar } from "@/components/ui";

type SortKey = "name" | "wr" | "maxWr" | "difficulty" | "totalGames" | "maxScore";

const num = (v: number | null | undefined) => (v == null ? -Infinity : v);

export function ChampionsExplorer({
  champions,
  roles,
}: {
  champions: Champion[];
  roles: string[];
}) {
  const [query, setQuery] = useState("");
  const [role, setRole] = useState("All roles");
  const [cls, setCls] = useState("All classes");
  const [sortKey, setSortKey] = useState<SortKey>("wr");
  const [dir, setDir] = useState<"asc" | "desc">("desc");

  const classes = useMemo(
    () => ["All classes", ...Array.from(new Set(champions.map((c) => c.class))).sort()],
    [champions]
  );
  const roleOptions = ["All roles", ...roles];

  const rows = useMemo(() => {
    let list = champions;
    if (role !== "All roles") list = list.filter((c) => c.role === role);
    if (cls !== "All classes") list = list.filter((c) => c.class === cls);
    const q = query.trim().toLowerCase();
    if (q) list = list.filter((c) => c.name.toLowerCase().includes(q));

    const sorted = [...list].sort((a, b) => {
      let cmp: number;
      if (sortKey === "name") cmp = a.name.localeCompare(b.name);
      else cmp = num(a[sortKey] as number) - num(b[sortKey] as number);
      return dir === "asc" ? cmp : -cmp;
    });
    return sorted;
  }, [champions, role, cls, query, sortKey, dir]);

  const toggleSort = (key: SortKey) => {
    if (key === sortKey) setDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setDir(key === "name" ? "asc" : "desc");
    }
  };

  return (
    <div>
      {/* Filters */}
      <div className="mb-5 flex flex-col gap-4">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search champion…"
          className="glass w-full rounded-xl px-4 py-2.5 text-sm outline-none transition placeholder:text-faint focus:border-accent/50"
        />
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap gap-2">
            {roleOptions.map((o) => (
              <button
                key={o}
                onClick={() => setRole(o)}
                className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition ${
                  role === o
                    ? "bg-accent text-[#07121f]"
                    : "glass glass-hover text-muted"
                }`}
              >
                {o}
              </button>
            ))}
          </div>
          <select
            value={cls}
            onChange={(e) => setCls(e.target.value)}
            className="glass rounded-lg px-3 py-1.5 text-sm text-muted outline-none focus:border-accent/50"
          >
            {classes.map((c) => (
              <option key={c} value={c} className="bg-surface-2 text-text">
                {c}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="mb-2 flex items-center justify-between">
        <p className="text-sm text-faint">{rows.length} champions</p>
        <p className="text-xs text-faint sm:hidden">swipe table →</p>
      </div>

      {/* Table */}
      <div className="glass overflow-x-auto rounded-2xl">
        <table className="w-full min-w-[860px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
              <Th className="w-12 text-center">#</Th>
              <Th onClick={() => toggleSort("name")} active={sortKey === "name"} dir={dir}>
                Champion
              </Th>
              <Th>Role</Th>
              <Th>Class</Th>
              <Th onClick={() => toggleSort("difficulty")} active={sortKey === "difficulty"} dir={dir}>
                Difficulty
              </Th>
              <Th className="text-center">Tier</Th>
              <Th onClick={() => toggleSort("wr")} active={sortKey === "wr"} dir={dir} right>
                Win rate
              </Th>
              <Th onClick={() => toggleSort("maxWr")} active={sortKey === "maxWr"} dir={dir} right>
                Ceiling
              </Th>
              <Th onClick={() => toggleSort("totalGames")} active={sortKey === "totalGames"} dir={dir} right>
                Games
              </Th>
              <Th onClick={() => toggleSort("maxScore")} active={sortKey === "maxScore"} dir={dir} right>
                Top mastery
              </Th>
              <Th>Best player</Th>
            </tr>
          </thead>
          <tbody>
            {rows.map((c, i) => (
              <tr
                key={c.slug}
                className="border-b border-line/60 transition last:border-0 hover:bg-white/[0.03]"
              >
                <td className="px-3 py-2.5 text-center text-faint">{i + 1}</td>
                <td className="px-3 py-2.5">
                  <Link
                    href={`/champions/${c.slug}`}
                    className="flex items-center gap-2.5 transition hover:text-accent"
                  >
                    <ChampionAvatar champion={c} size={32} />
                    <span className="font-medium">{c.name}</span>
                  </Link>
                </td>
                <td className="px-3 py-2.5 text-muted">{c.role}</td>
                <td className="px-3 py-2.5 text-muted">{c.class}</td>
                <td className={`px-3 py-2.5 ${c.isHard ? "text-bad" : "text-muted"}`}>
                  {c.difficultyLabel}
                </td>
                <td className="px-3 py-2.5 text-center">
                  <TierChip tier={c.tier} />
                </td>
                <td className="px-3 py-2.5 text-right font-semibold text-accent">
                  {c.wr.toFixed(1)}%
                </td>
                <td className="px-3 py-2.5 text-right text-gold">
                  {c.maxWr != null ? `${c.maxWr.toFixed(1)}%` : "—"}
                </td>
                <td className="px-3 py-2.5 text-right text-muted">
                  {c.totalGames != null ? c.totalGames.toLocaleString() : "—"}
                </td>
                <td className="px-3 py-2.5 text-right text-muted">
                  {c.maxScore != null ? c.maxScore.toLocaleString() : "—"}
                </td>
                <td className="max-w-[160px] truncate px-3 py-2.5 text-muted">
                  {c.topPlayer ?? "—"}
                </td>
              </tr>
            ))}
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
        className={`inline-flex items-center gap-1 transition hover:text-text ${
          active ? "text-accent" : ""
        }`}
      >
        {children}
        {active && <span className="text-[0.6rem]">{dir === "asc" ? "▲" : "▼"}</span>}
      </button>
    </th>
  );
}
