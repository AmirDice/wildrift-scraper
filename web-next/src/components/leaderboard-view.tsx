"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { TierChip } from "@/components/ui";
import { ChampionCombobox } from "@/components/champion-combobox";

export type SlimChampion = {
  name: string;
  slug: string;
  icon: string;
  splash: string;
  role: string;
  class: string;
  tier: string;
  wr: number;
  isHard: boolean;
  bestPlayer: { player: string; rank: number | null; confidence_wr: number | null } | null;
};

type Row = { r: number; p: string; w: number | null; g: number | null; s: number | null };
type SortKey = "r" | "w" | "g" | "s";

const num = (v: number | null | undefined) => (v == null ? -Infinity : v);

export function LeaderboardView({ champions }: { champions: SlimChampion[] }) {
  const byName = useMemo(
    () => [...champions].sort((a, b) => a.name.localeCompare(b.name)),
    [champions]
  );
  const [slug, setSlug] = useState(champions[0]?.slug ?? "");
  const [data, setData] = useState<Record<string, Row[]> | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("r");
  const [dir, setDir] = useState<"asc" | "desc">("asc");

  useEffect(() => {
    const param = new URLSearchParams(window.location.search).get("champion");
    if (param) {
      const norm = param.trim().toLowerCase();
      const match = champions.find(
        (c) => c.slug === norm || c.name.toLowerCase() === norm
      );
      if (match) setSlug(match.slug);
    }
    fetch("/players.json")
      .then((r) => r.json())
      .then(setData)
      .catch(() => setData({}));
  }, [champions]);

  const champ = champions.find((c) => c.slug === slug);
  const rows = useMemo(() => {
    const base = data?.[slug] ?? [];
    return [...base].sort((a, b) => {
      const cmp = num(a[sortKey]) - num(b[sortKey]);
      return dir === "asc" ? cmp : -cmp;
    });
  }, [data, slug, sortKey, dir]);

  const toggleSort = (key: SortKey) => {
    if (key === sortKey) setDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setDir(key === "r" ? "asc" : "desc");
    }
  };

  return (
    <div>
      {/* Champion search */}
      <div className="mb-5 sm:max-w-sm">
        <ChampionCombobox
          champions={byName.map((c) => ({ name: c.name, slug: c.slug, icon: c.icon }))}
          placeholder="Search a champion…"
          onSelect={(s) => setSlug(s)}
        />
      </div>

      {/* Best-player splash highlight */}
      {champ && (
        <div className="relative mb-6 overflow-hidden rounded-2xl border border-line">
          <div
            className="absolute inset-0 bg-cover bg-center"
            style={{ backgroundImage: `url(${champ.splash})` }}
          />
          <div className="absolute inset-0 bg-gradient-to-r from-bg via-bg/85 to-bg/30" />
          <div className="absolute inset-0 bg-gradient-to-t from-bg/90 to-transparent" />
          <div className="relative flex flex-col gap-5 p-6 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <Link
                href={`/champions/${champ.slug}`}
                className="inline-flex items-center gap-3 transition hover:opacity-90"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={champ.icon}
                  alt=""
                  width={44}
                  height={44}
                  className={`h-11 w-11 rounded-full ${champ.isHard ? "ring-2 ring-bad/70" : "ring-1 ring-white/15"}`}
                />
                <span>
                  <span className="block text-xl font-semibold leading-tight">{champ.name}</span>
                  <span className="block text-xs text-muted">
                    {champ.role} · {champ.class}
                  </span>
                </span>
              </Link>
              <div className="mt-3 flex items-center gap-2">
                <TierChip tier={champ.tier} />
                <span className="text-sm font-semibold text-accent">{champ.wr.toFixed(1)}% win rate</span>
              </div>
            </div>

            {champ.bestPlayer && (
              <div className="glass rounded-xl px-5 py-4 sm:text-right">
                <p className="text-xs font-semibold uppercase tracking-wide text-accent">
                  Best {champ.name} player
                </p>
                <p className="mt-1.5 truncate text-2xl font-semibold">{champ.bestPlayer.player}</p>
                <p className="mt-0.5 text-sm text-muted">
                  {champ.bestPlayer.rank ? `Rank #${champ.bestPlayer.rank} · ` : ""}
                  {champ.bestPlayer.confidence_wr != null
                    ? `${champ.bestPlayer.confidence_wr.toFixed(1)}% adjusted`
                    : ""}
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Player table */}
      {data === null ? (
        <div className="glass rounded-2xl p-10 text-center text-muted">Loading players…</div>
      ) : rows.length === 0 ? (
        <div className="glass rounded-2xl p-10 text-center text-muted">
          No player data for this champion yet.
        </div>
      ) : (
        <div className="glass overflow-x-auto rounded-2xl">
          <table className="w-full min-w-[560px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
                <Th onClick={() => toggleSort("r")} active={sortKey === "r"} dir={dir} className="w-16 text-center">
                  Rank
                </Th>
                <Th>Player</Th>
                <Th onClick={() => toggleSort("w")} active={sortKey === "w"} dir={dir} right>
                  Win rate
                </Th>
                <Th onClick={() => toggleSort("g")} active={sortKey === "g"} dir={dir} right>
                  Games
                </Th>
                <Th onClick={() => toggleSort("s")} active={sortKey === "s"} dir={dir} right>
                  Mastery
                </Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr
                  key={`${row.r}-${i}`}
                  className="border-b border-line/60 transition last:border-0 hover:bg-white/[0.03]"
                >
                  <td className="px-3 py-2.5 text-center">
                    <span className={row.r <= 3 ? "font-bold text-accent" : "text-faint"}>
                      {row.r}
                    </span>
                  </td>
                  <td className="max-w-[220px] truncate px-3 py-2.5 font-medium">{row.p}</td>
                  <td className="px-3 py-2.5 text-right font-semibold text-accent">
                    {row.w != null ? `${row.w.toFixed(1)}%` : "—"}
                  </td>
                  <td className="px-3 py-2.5 text-right text-muted">
                    {row.g != null ? row.g.toLocaleString() : "—"}
                  </td>
                  <td className="px-3 py-2.5 text-right text-muted">
                    {row.s != null ? row.s.toLocaleString() : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
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
