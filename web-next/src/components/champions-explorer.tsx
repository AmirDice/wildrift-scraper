"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { Champion } from "@/lib/data";
import type { CnChampion } from "@/lib/cn";
import { TierChip, ChampionAvatar } from "@/components/ui";
import { RegionToggle, RegionComingSoon, type Region } from "@/components/region-toggle";
import { RegionUpdated } from "@/components/tierlist-updated";
import { BOARD_DEPTH } from "@/lib/regions";

type SortKey =
  | "name" | "wr" | "maxWr" | "difficulty" | "totalGames" | "maxScore"
  | "pickRate" | "banRate";

const num = (v: number | null | undefined) => (v == null ? -Infinity : v);
const cnv = (c: Champion, k: "pickRate" | "banRate") =>
  k === "pickRate" ? (c as CnChampion).cnPickRate : (c as CnChampion).cnBanRate;

export function ChampionsExplorer({
  champions,
  roles,
  cnChampions,
  cnRoles,
  naChampions,
  naRoles,
  naUpdated,
  cnMeta,
  euUpdated,
  absent,
  rosterSize,
}: {
  champions: Champion[];
  roles: string[];
  cnChampions: CnChampion[];
  cnRoles: string[];
  naChampions: Champion[];
  naRoles: string[];
  naUpdated?: string | null;
  cnMeta: { source: string; date: string | null; bracket: string };
  euUpdated?: string | null;
  /** Roster champions each region has no numbers for, so the page can say so. */
  absent?: { CN: string[]; EU: string[] };
  rosterSize?: number;
}) {
  const [query, setQuery] = useState("");
  const [role, setRole] = useState("All roles");
  const [cls, setCls] = useState("All classes");
  const [sortKey, setSortKey] = useState<SortKey>("wr");
  const [dir, setDir] = useState<"asc" | "desc">("desc");
  const [region, setRegion] = useState<Region>("EU");
  const [view, setView] = useState<"grid" | "list">("grid");

  const isCN = region === "CN";
  const isNA = region === "NA";
  const activeChampions: Champion[] = isCN ? cnChampions : isNA ? naChampions : champions;
  const activeRoles = isCN ? cnRoles : isNA ? naRoles : roles;
  // NA's collection is still running, so the champions it has no board for
  // are listed as not-yet-collected rather than silently missing.
  const naAbsent = champions
    .filter((c) => !naChampions.some((n) => n.slug === c.slug))
    .map((c) => c.name);
  const missing = (isCN ? absent?.CN : isNA ? naAbsent : absent?.EU) ?? [];

  const classes = useMemo(
    () => ["All classes", ...Array.from(new Set(activeChampions.map((c) => c.class))).sort()],
    [activeChampions]
  );
  const roleOptions = ["All roles", ...activeRoles];

  const rows = useMemo(() => {
    let list = activeChampions;
    if (role !== "All roles") list = list.filter((c) => c.role === role);
    if (cls !== "All classes") list = list.filter((c) => c.class === cls);
    const q = query.trim().toLowerCase();
    if (q) list = list.filter((c) => c.name.toLowerCase().includes(q));

    return [...list].sort((a, b) => {
      let cmp: number;
      if (sortKey === "name") cmp = a.name.localeCompare(b.name);
      else if (sortKey === "pickRate" || sortKey === "banRate") cmp = cnv(a, sortKey) - cnv(b, sortKey);
      else cmp = num(a[sortKey] as number) - num(b[sortKey] as number);
      return dir === "asc" ? cmp : -cmp;
    });
  }, [activeChampions, role, cls, query, sortKey, dir]);

  const snapshot = useMemo(() => {
    const topWin = [...activeChampions].sort((a, b) => b.wr - a.wr)[0];
    const ceiling = isCN
      ? [...activeChampions].sort((a, b) => cnv(b, "pickRate") - cnv(a, "pickRate"))[0]
      : [...activeChampions].filter((c) => c.maxWr != null).sort((a, b) => num(b.maxWr) - num(a.maxWr))[0];
    const depth = isCN
      ? [...activeChampions].sort((a, b) => cnv(b, "banRate") - cnv(a, "banRate"))[0]
      : [...activeChampions].filter((c) => c.totalGames != null).sort((a, b) => num(b.totalGames) - num(a.totalGames))[0];
    return { topWin, ceiling, depth };
  }, [activeChampions, isCN]);

  const toggleSort = (key: SortKey) => {
    if (key === sortKey) setDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setDir(key === "name" ? "asc" : "desc");
    }
  };

  const changeRegion = (r: Region) => {
    setRegion(r);
    setRole("All roles");
    setCls("All classes");
    setSortKey(r === "CN" ? "wr" : "wr");
  };

  return (
    <div className="champions-atlas">
      <div className="mb-5 flex justify-start sm:justify-end">
        <div className="liquid-glass inline-flex items-center rounded-2xl p-2">
          <RegionToggle region={region} onChange={changeRegion} regions={["CN", "EU", "NA"]} />
        </div>
      </div>

      <div className="champion-snapshot mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <SnapshotCard label="Tracked" value={activeChampions.length.toLocaleString()} sub="champions with data" tone="cyan" />
        <SnapshotCard label="Top win rate" value={snapshot.topWin ? `${snapshot.topWin.name} · ${snapshot.topWin.wr.toFixed(1)}%` : "–"} sub={isCN ? cnMeta.bracket : `Top ${region === "EU" ? BOARD_DEPTH.EU : BOARD_DEPTH.NA} players`} tone="violet" />
        <SnapshotCard
          label={isCN ? "Most picked" : "Highest ceiling"}
          value={snapshot.ceiling ? `${snapshot.ceiling.name} · ${isCN ? `${cnv(snapshot.ceiling, "pickRate").toFixed(1)}%` : `${snapshot.ceiling.maxWr?.toFixed(1)}%`}` : "–"}
          sub={isCN ? "official pick rate" : "elite mastery signal"}
          tone="blue"
        />
        <SnapshotCard
          label={isCN ? "Most banned" : "Deepest sample"}
          value={snapshot.depth ? `${snapshot.depth.name} · ${isCN ? `${cnv(snapshot.depth, "banRate").toFixed(1)}%` : `${snapshot.depth.totalGames?.toLocaleString()} games`}` : "–"}
          sub={isCN ? "official ban rate" : "across top players"}
          tone="gold"
        />
      </div>

      <div className="champion-explorer-shell glass rounded-[1.75rem] p-3 sm:p-4">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3 px-1">
      {region === "EU" && (
        <p className="max-w-2xl text-sm text-muted">
          Every champion tracked on EU, ranked by the win rates of each
          champion&apos;s top {BOARD_DEPTH.EU} players.
        </p>
      )}

      {isNA && (
        <p className="max-w-2xl text-sm text-muted">
          Every champion tracked on NA, ranked by the win rates of each
          champion&apos;s top {BOARD_DEPTH.NA} players.
        </p>
      )}

      <div>
        <RegionUpdated region={region} euDate={euUpdated} cnDate={cnMeta.date} naDate={naUpdated} />
      </div>
      </div>

      {activeChampions.length === 0 ? (
        <RegionComingSoon region={region} />
      ) : (
        <>
          {isCN && (
            <p className="mb-4 text-sm text-muted">
              Official China server data ({cnMeta.bracket}, top regular-ranked sample): win, pick &amp; ban
              rates.
            </p>
          )}

          {/* Filters */}
          <div className="champion-filter-deck mb-5 flex flex-col gap-4 rounded-2xl border border-white/[0.065] bg-[#060c17]/55 p-3 sm:p-4">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search champion…"
              className="liquid-glass w-full rounded-xl px-4 py-2.5 text-sm outline-none transition placeholder:text-faint focus:border-accent/50"
            />
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap gap-2">
                {roleOptions.map((o) => (
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
              <select
                value={sortKey}
                onChange={(e) => {
                  const key = e.target.value as SortKey;
                  setSortKey(key);
                  setDir(key === "name" ? "asc" : "desc");
                }}
                aria-label="Sort champions"
                className="glass rounded-lg px-3 py-1.5 text-sm text-muted outline-none focus:border-accent/50"
              >
                <option value="wr" className="bg-surface-2 text-text">Win rate</option>
                <option value="name" className="bg-surface-2 text-text">Name</option>
                {isCN ? (
                  <>
                    <option value="pickRate" className="bg-surface-2 text-text">Pick rate</option>
                    <option value="banRate" className="bg-surface-2 text-text">Ban rate</option>
                  </>
                ) : (
                  <>
                    <option value="maxWr" className="bg-surface-2 text-text">Skill ceiling</option>
                    <option value="totalGames" className="bg-surface-2 text-text">Games</option>
                    <option value="maxScore" className="bg-surface-2 text-text">Top mastery</option>
                  </>
                )}
              </select>
            </div>
          </div>

          <div className="mb-2 flex items-center justify-between gap-3">
            <p className="text-sm text-faint">{rows.length} champions</p>
            <div className="glass-thin flex items-center gap-1 rounded-lg p-1" aria-label="Champion view">
              <button type="button" onClick={() => setView("grid")} aria-label="Grid view" aria-pressed={view === "grid"}
                className={`grid h-8 w-8 place-items-center rounded-md transition ${view === "grid" ? "bg-white/[0.1] text-text" : "text-muted hover:text-text"}`}>
                <ViewGlyph view="grid" />
              </button>
              <button type="button" onClick={() => setView("list")} aria-label="List view" aria-pressed={view === "list"}
                className={`grid h-8 w-8 place-items-center rounded-md transition ${view === "list" ? "bg-white/[0.1] text-text" : "text-muted hover:text-text"}`}>
                <ViewGlyph view="list" />
              </button>
            </div>
          </div>

          {/* A count lower than the roster used to be unexplained, which reads
              as missing champions rather than missing GAMES. Naming them is the
              only honest option: there is no win rate to show for a champion
              nobody has played in this dataset. */}
          {missing.length > 0 && (
            <p className="mb-3 text-xs leading-relaxed text-faint">
              {rosterSize ? `${rosterSize} champions are in the game. ` : ""}
              {isCN
                ? `${missing.length} ${missing.length === 1 ? "has" : "have"} no recorded games at ${cnMeta.bracket} and ${missing.length === 1 ? "is" : "are"} not listed above: `
                : `${missing.length} ${missing.length === 1 ? "has" : "have"} no ranked sample in this dataset yet and ${missing.length === 1 ? "is" : "are"} not listed above: `}
              <span className="text-muted">{missing.join(", ")}</span>
              {isCN ? ". They are usually present at other ranks." : "."}
            </p>
          )}

          {/* Grid / list */}
          {view === "grid" ? (
            <ChampionGrid rows={rows} isCN={isCN} />
          ) : (
          <div className="glass overflow-x-auto rounded-2xl">
            <table className="w-full min-w-[720px] border-collapse text-sm">
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
                  {isCN ? (
                    <>
                      <Th onClick={() => toggleSort("pickRate")} active={sortKey === "pickRate"} dir={dir} right>
                        Pick rate
                      </Th>
                      <Th onClick={() => toggleSort("banRate")} active={sortKey === "banRate"} dir={dir} right>
                        Ban rate
                      </Th>
                    </>
                  ) : (
                    <>
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
                    </>
                  )}
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
                    {isCN ? (
                      <>
                        <td className="px-3 py-2.5 text-right text-muted">
                          {cnv(c, "pickRate").toFixed(1)}%
                        </td>
                        <td className="px-3 py-2.5 text-right text-muted">
                          {cnv(c, "banRate").toFixed(1)}%
                        </td>
                      </>
                    ) : (
                      <>
                        <td className="px-3 py-2.5 text-right text-gold">
                          {c.maxWr != null ? `${c.maxWr.toFixed(1)}%` : "-"}
                        </td>
                        <td className="px-3 py-2.5 text-right text-muted">
                          {c.totalGames != null ? c.totalGames.toLocaleString() : "-"}
                        </td>
                        <td className="px-3 py-2.5 text-right text-muted">
                          {c.maxScore != null ? c.maxScore.toLocaleString() : "-"}
                        </td>
                        <td className="max-w-[160px] truncate px-3 py-2.5 text-muted">
                          {c.topPlayer ?? "-"}
                        </td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          )}
        </>
      )}
      </div>
    </div>
  );
}

function SnapshotCard({ label, value, sub, tone }: { label: string; value: string; sub: string; tone: "cyan" | "violet" | "blue" | "gold" }) {
  const tones = {
    cyan: "text-emerald-300",
    violet: "text-violet-300",
    blue: "text-accent",
    gold: "text-gold",
  } as const;
  return (
    <div className={`champion-snapshot-card champion-snapshot-${tone} glass glass-card rounded-2xl p-4 sm:p-5 ${tones[tone]}`}>
      <div className="flex items-start justify-between gap-3">
        <p className="text-[0.65rem] font-semibold uppercase tracking-[0.14em] text-faint">{label}</p>
        <svg viewBox="0 0 72 24" className="h-6 w-[4.5rem]" aria-hidden>
          <path d="M2 20 C10 18 14 11 21 14 S33 21 40 11 S52 14 60 7 S68 6 70 3" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
      </div>
      <p className="mt-3 truncate text-base font-semibold text-text sm:text-lg">{value}</p>
      <p className="mt-0.5 text-xs text-muted">{sub}</p>
    </div>
  );
}

function ChampionGrid({ rows, isCN }: { rows: Champion[]; isCN: boolean }) {
  return (
    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {rows.map((c, i) => (
        <Link key={c.slug} href={`/champions/${c.slug}`}
          className="champion-grid-card glass glass-hover group rounded-2xl p-3.5">
          <div className="flex items-center gap-3">
            <ChampionAvatar champion={c} size={48} />
            <div className="min-w-0 flex-1">
              <p className="truncate font-semibold text-text group-hover:text-accent">{c.name}</p>
              <p className="mt-0.5 truncate text-xs text-muted">{c.role} · {c.class}</p>
            </div>
            <TierChip tier={c.tier} />
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2">
            <GridMetric label="Win rate" value={`${c.wr.toFixed(1)}%`} accent />
            {isCN ? (
              <GridMetric label="Pick rate" value={`${cnv(c, "pickRate").toFixed(1)}%`} />
            ) : (
              <GridMetric label="Ceiling" value={c.maxWr != null ? `${c.maxWr.toFixed(1)}%` : "–"} />
            )}
          </div>
          <div className="mt-3 h-1 overflow-hidden rounded-full bg-white/[0.055]">
            <span className="block h-full rounded-full bg-gradient-to-r from-accent/65 to-accent"
              style={{ width: `${Math.max(12, Math.min(100, 46 + (c.wr - 50) * 10))}%` }} />
          </div>
          <span className="absolute bottom-3.5 right-3.5 text-[0.65rem] text-faint">#{String(i + 1).padStart(2, "0")}</span>
        </Link>
      ))}
    </div>
  );
}

function GridMetric({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  return (
    <span className="rounded-xl border border-line/60 bg-black/15 px-2.5 py-2">
      <span className="block text-[0.6rem] font-semibold uppercase tracking-wide text-faint">{label}</span>
      <span className={`mt-0.5 block text-sm font-semibold ${accent ? "text-accent" : "text-text"}`}>{value}</span>
    </span>
  );
}

function ViewGlyph({ view }: { view: "grid" | "list" }) {
  if (view === "grid") return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="currentColor" aria-hidden>
      <rect x="1" y="1" width="6" height="6" rx="1"/><rect x="9" y="1" width="6" height="6" rx="1"/>
      <rect x="1" y="9" width="6" height="6" rx="1"/><rect x="9" y="9" width="6" height="6" rx="1"/>
    </svg>
  );
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="currentColor" aria-hidden>
      <rect x="1" y="2" width="14" height="3" rx="1"/><rect x="1" y="7" width="14" height="3" rx="1"/>
      <rect x="1" y="12" width="14" height="3" rx="1"/>
    </svg>
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
