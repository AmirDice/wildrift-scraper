"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { Card } from "@/components/ui";
import { AskAgent } from "@/components/site-agent";
import type { ChampionLoadoutLane, LoadoutEntity, LoadoutRow, LoadoutTab } from "@/lib/cn-loadouts";

/* eslint-disable @next/next/no-img-element */

type TabKey = "items" | "runes" | "boots" | "spells" | "versus";

/** The agent question beside each tab. Every one is answered from this same
 *  China data by the agent's fast path, so asking costs no AI answer. */
const TAB_QUESTION: Partial<Record<TabKey, (champion: string) => string>> = {
  items: (champion) => `What do Chinese players build on ${champion}?`,
  runes: (champion) => `What runes do top players use on ${champion}?`,
  boots: (champion) => `What boots do players buy on ${champion}?`,
  versus: (champion) => `What is ${champion}'s best matchup in China?`,
};

const BASE_TABS: { key: TabKey; label: string; short: string }[] = [
  { key: "items", label: "Core items", short: "Cores" },
  { key: "runes", label: "Rune pages", short: "Runes" },
  { key: "boots", label: "Boots", short: "Boots" },
  { key: "spells", label: "Summoner spells", short: "Spells" },
  { key: "versus", label: "Matchups", short: "Matchups" },
];

const LANE_LABEL: Record<string, string> = {
  baron: "Baron",
  jungle: "Jungle",
  mid: "Mid",
  dragon: "Dragon",
  support: "Support",
};

const TAB_COPY: Record<Exclude<TabKey, "versus">, string> = {
  items: "The most common three-item cores recorded in CN Legendary ranked.",
  runes: "Complete five-rune pages, shown as players actually selected them.",
  boots: "Tier 2 boot choices. This tab can refresh on a different date from item cores.",
  spells: "Summoner-spell pairs used for this champion and lane.",
};

function parseDataDate(value: string | null): Date | null {
  if (!value || !/^\d{8}$/.test(value)) return null;
  const year = Number(value.slice(0, 4));
  const month = Number(value.slice(4, 6)) - 1;
  const day = Number(value.slice(6, 8));
  const date = new Date(Date.UTC(year, month, day));
  return Number.isNaN(date.getTime()) ? null : date;
}

/**
 * When WE captured this lane, as "Oct 15, 2026".
 *
 * The chip used to print the visitor's own date, set in an effect on every
 * page load, so it read "Updated" today on every day whether or not anything
 * had been collected. This is the capture's own timestamp, which moves only
 * when the lane is collected again. Formatted in UTC from the stored string
 * rather than through the visitor's clock, so the server and the browser
 * render the same text.
 */
function formatCaptureDate(value: string | null | undefined): string | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(value ?? "");
  if (!m) return null;
  const date = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])));
  return date.toLocaleDateString("en", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
}

function formatDataDate(value: string | null): string {
  const date = parseDataDate(value);
  return date
    ? date.toLocaleDateString("en", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" })
    : "Date unavailable";
}

function EntityIcon({ entity, large = false }: { entity: LoadoutEntity; large?: boolean }) {
  const image = (
    <img
      src={entity.icon}
      alt={entity.name}
      loading="lazy"
      className={`${large ? "h-11 w-11" : "h-9 w-9"} rounded-xl border border-white/10 bg-black/25 object-cover shadow-md shadow-black/20`}
    />
  );
  return entity.href ? (
    <Link href={entity.href} title={entity.name} className="rounded-xl outline-none transition hover:-translate-y-0.5 focus-visible:ring-2 focus-visible:ring-accent/60">
      {image}
    </Link>
  ) : (
    <span title={entity.name}>{image}</span>
  );
}

function Rate({ label, value, accent = false, move }: { label: string; value: number; accent?: boolean; move?: React.ReactNode }) {
  return (
    <div className="text-right">
      <p className={`text-sm font-bold tabular-nums ${accent ? "text-accent" : "text-text"}`}>{value.toFixed(1)}%{move}</p>
      <p className="text-[0.57rem] font-semibold uppercase tracking-[0.12em] text-faint">{label}</p>
    </div>
  );
}

/**
 * Movement since the previous capture, shown only when it clears the noise.
 * Measured on the Oct 11 -> Oct 15 captures: Legendary win rates swing hard
 * between captures (a third of rows above 5% pick rate moved 3+ points in
 * four days), so a win-rate arrow needs 5 points on a 5%+ row. Pick rate is
 * the steadier signal, what players are switching to: an arrow at 2+ points
 * and 40%+ relative, on rows played 3%+, marks about 6% of rows. Rank is
 * ordered by win rate, so a position arrow would only repeat that noise.
 */
const PICK_MIN = 3;
const PICK_MIN_ABS = 2;
const PICK_MIN_REL = 0.4;
const WR_MIN_PICK = 5;
const WR_MIN_DELTA = 5;
const NEW_MIN_PICK = 5;

function movementNote(row: LoadoutRow, since: string | null): string | undefined {
  if (!row.prev || !since) return undefined;
  return `Since ${since}: pick rate ${row.prev.pickRate.toFixed(1)}% → ${row.pickRate.toFixed(1)}%, `
    + `win rate ${row.prev.winRate.toFixed(1)}% → ${row.winRate.toFixed(1)}%`;
}

function NewTag({ row, since }: { row: LoadoutRow; since: string | null }) {
  if (!since || !row.new || row.pickRate < NEW_MIN_PICK) return null;
  return <span title={`Not in the ${since} capture`} className="rounded-md bg-accent/15 px-1.5 py-0.5 text-[0.58rem] font-bold uppercase tracking-wide text-accent">New</span>;
}

function Move({ delta, note }: { delta: number; note?: string }) {
  return (
    <span title={note} className={`ml-1 text-[0.6rem] font-bold ${delta > 0 ? "text-emerald-300" : "text-rose-300"}`}>
      {delta > 0 ? "▲" : "▼"}{Math.abs(delta).toFixed(1)}
    </span>
  );
}

function PickRateMove({ row, since }: { row: LoadoutRow; since: string | null }) {
  if (!since || !row.prev) return null;
  const delta = row.pickRate - row.prev.pickRate;
  if (Math.max(row.pickRate, row.prev.pickRate) < PICK_MIN || Math.abs(delta) < PICK_MIN_ABS
      || Math.abs(delta) / Math.max(row.prev.pickRate, 0.1) < PICK_MIN_REL) return null;
  return <Move delta={delta} note={movementNote(row, since)} />;
}

function WinRateMove({ row, since }: { row: LoadoutRow; since: string | null }) {
  if (!since || !row.prev || row.pickRate < WR_MIN_PICK) return null;
  const delta = row.winRate - row.prev.winRate;
  if (Math.abs(delta) < WR_MIN_DELTA) return null;
  return <Move delta={delta} note={movementNote(row, since)} />;
}

function StandardRow({ row, kind, since }: { row: LoadoutRow; kind: TabKey; since: string | null }) {
  const names = row.entities.map((entity) => entity.name).join(" · ");
  return (
    <article className="group relative overflow-hidden rounded-2xl border border-white/[0.075] bg-black/[0.16] p-3 transition hover:border-accent/25 hover:bg-white/[0.035]">
      <div className="pointer-events-none absolute inset-y-0 left-0 w-px bg-gradient-to-b from-transparent via-accent/50 to-transparent opacity-0 transition group-hover:opacity-100" />
      <div className="flex min-w-0 items-center gap-2.5 sm:gap-3">
        <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg border border-white/10 bg-white/[0.045] text-[0.65rem] font-bold text-faint">
          {row.rank}
        </span>
        <div className="flex shrink-0 -space-x-1.5">
          {row.entities.map((entity, index) => (
            <span key={`${entity.name}-${index}`} className="relative" style={{ zIndex: row.entities.length - index }}>
              <EntityIcon entity={entity} large={kind === "versus"} />
            </span>
          ))}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-semibold text-text" title={names}>{names}</p>
          <p className="mt-0.5 flex items-center gap-1.5 text-[0.64rem] text-faint">
            {kind === "items" ? "Three-item core" : kind === "runes" ? "Full rune page" : kind === "boots" ? "Tier 2 boots" : kind === "spells" ? "Spell pair" : "Opponent"}
            <NewTag row={row} since={since} />
          </p>
        </div>
        <div className="hidden shrink-0 grid-cols-2 gap-3 border-l border-white/[0.07] pl-3 sm:grid">
          <Rate label="WR" value={row.winRate} accent move={<WinRateMove row={row} since={since} />} />
          <Rate label="Pick" value={row.pickRate} move={<PickRateMove row={row} since={since} />} />
        </div>
      </div>
      <div className="mt-2.5 grid grid-cols-2 gap-3 border-t border-white/[0.07] pt-2.5 sm:hidden">
        <Rate label="WR" value={row.winRate} accent move={<WinRateMove row={row} since={since} />} />
        <Rate label="Pick rate" value={row.pickRate} move={<PickRateMove row={row} since={since} />} />
      </div>
    </article>
  );
}

function MatchupPanel({ title, tone, rows, since }: { title: string; tone: "good" | "bad"; rows: LoadoutRow[]; since: string | null }) {
  return (
    <section className="rounded-2xl border border-white/[0.075] bg-black/[0.12] p-3.5">
      <div className="flex items-center justify-between gap-3">
        <h4 className="text-sm font-semibold text-text">{title}</h4>
        <span className={`h-2 w-2 rounded-full ${tone === "good" ? "bg-emerald-300 shadow-[0_0_12px_rgba(110,231,199,.75)]" : "bg-rose-300 shadow-[0_0_12px_rgba(251,113,133,.7)]"}`} />
      </div>
      <div className="mt-3 space-y-2">
        {rows.map((row) => (
          <div key={`${title}-${row.rank}-${row.entities[0]?.name}`} className="flex items-center gap-2.5 rounded-xl bg-white/[0.035] p-2.5">
            {row.entities[0] && <EntityIcon entity={row.entities[0]} />}
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-semibold text-text">{row.entities[0]?.name}</p>
              <p className="mt-0.5 text-[0.62rem] text-faint">{row.pickRate.toFixed(1)}% of listed matchups</p>
            </div>
            <span className={`text-sm font-bold tabular-nums ${tone === "good" ? "text-emerald-300" : "text-rose-300"}`}>{row.winRate.toFixed(1)}%<WinRateMove row={row} since={since} /></span>
          </div>
        ))}
      </div>
    </section>
  );
}

function EmptyState({ champion }: { champion: string }) {
  return (
    <Card className="relative overflow-hidden p-5 sm:p-6">
      <div className="pointer-events-none absolute -right-16 -top-20 h-52 w-52 rounded-full bg-accent/10 blur-3xl" />
      <div className="relative flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded-full border border-amber-300/20 bg-amber-300/10 px-2.5 py-1 text-[0.62rem] font-bold uppercase tracking-[0.14em] text-amber-200">Collection pending</span>
            <span className="text-[0.65rem] font-semibold uppercase tracking-[0.14em] text-faint">CN Legendary</span>
          </div>
          <h2 className="mt-3 text-lg font-semibold">Player loadouts for {champion}</h2>
          <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-muted">
            This champion’s lane-by-lane item cores, runes, boots, spells and matchups are still being processed. The section will fill automatically with the next data refresh.
          </p>
        </div>
        <div className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl border border-white/10 bg-white/[0.04] text-xl text-faint" aria-hidden="true">⌛</div>
      </div>
    </Card>
  );
}

export function ChampionLoadouts({ champion, loadouts }: { champion: string; loadouts: ChampionLoadoutLane[] }) {
  const [laneIndex, setLaneIndex] = useState(0);
  const [activeTab, setActiveTab] = useState<TabKey>("items");
  const [expanded, setExpanded] = useState(false);
  const lane = loadouts[Math.min(laneIndex, Math.max(loadouts.length - 1, 0))];
  const tabs = useMemo(() => BASE_TABS.map((tab) => tab.key === "versus"
    ? { ...tab, label: lane?.versusKind === "partners" ? "Best partners" : "Matchups", short: lane?.versusKind === "partners" ? "Partners" : "Matchups" }
    : tab), [lane?.versusKind]);

  if (!lane) return <EmptyState champion={champion} />;

  const tab = lane.tabs[activeTab];
  const since = formatCaptureDate(lane.previousCapturedAt);
  const rows = tab.rows;
  const visibleRows = expanded ? rows : rows.slice(0, 6);
  const favorable = [...lane.tabs.versus.rows].sort((a, b) => b.winRate - a.winRate).slice(0, 5);
  const difficult = [...lane.tabs.versus.rows].sort((a, b) => a.winRate - b.winRate).slice(0, 5);
  const versusCopy = lane.versusKind === "partners"
    ? "Lane partners with the strongest results alongside this champion."
    : "Matchup win rates from the strongest to the most difficult opponents.";

  return (
    <Card className="relative overflow-hidden border border-sky-300/[0.12] p-0">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-sky-300/70 to-transparent" />
      <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-sky-400/[0.08] blur-3xl" />
      <div className="relative border-b border-white/[0.075] px-4 pb-4 pt-5 sm:px-5 sm:pt-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full border border-sky-300/20 bg-sky-300/10 px-2.5 py-1 text-[0.62rem] font-bold uppercase tracking-[0.16em] text-sky-200">CN server</span>
              <span className="rounded-full border border-white/[0.08] bg-white/[0.035] px-2.5 py-1 text-[0.62rem] font-semibold uppercase tracking-[0.14em] text-faint">Legendary ranked</span>
            </div>
            <h2 className="mt-3 text-xl font-semibold tracking-tight">What top {champion} players are running</h2>
            <p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted">Lane-specific loadouts from the CN server, with win rate and popularity kept side by side.</p>
          </div>
          {loadouts.length > 1 ? (
            <div className="flex max-w-full gap-1 overflow-x-auto rounded-xl border border-white/[0.08] bg-black/15 p-1" role="tablist" aria-label="Loadout lane">
              {loadouts.map((entry, index) => (
                <button
                  key={entry.lane}
                  type="button"
                  role="tab"
                  aria-selected={index === laneIndex}
                  onClick={() => { setLaneIndex(index); setExpanded(false); }}
                  className={`shrink-0 rounded-lg px-3 py-2 text-xs font-semibold transition ${index === laneIndex ? "bg-sky-300/15 text-sky-200 ring-1 ring-sky-300/20" : "text-muted hover:bg-white/[0.04] hover:text-text"}`}
                >
                  {LANE_LABEL[entry.lane] ?? entry.lane}
                </button>
              ))}
            </div>
          ) : (
            <span className="self-start rounded-lg border border-white/[0.08] bg-black/15 px-3 py-2 text-xs font-semibold text-sky-200">{LANE_LABEL[lane.lane] ?? lane.lane}</span>
          )}
        </div>
      </div>

      <div className="relative px-4 pb-5 pt-4 sm:px-5 sm:pb-6">
        <div className="overflow-x-auto pb-1" role="tablist" aria-label="Loadout category">
          <div className="flex min-w-max gap-1 rounded-xl border border-white/[0.07] bg-black/15 p-1">
            {tabs.map((item) => (
              <button
                key={item.key}
                type="button"
                role="tab"
                aria-selected={activeTab === item.key}
                onClick={() => { setActiveTab(item.key); setExpanded(false); }}
                className={`rounded-lg px-3 py-2 text-xs font-semibold transition sm:px-4 ${activeTab === item.key ? "bg-white/[0.09] text-text shadow-sm ring-1 ring-white/[0.08]" : "text-muted hover:bg-white/[0.04] hover:text-text"}`}
              >
                <span className="sm:hidden">{item.short}</span><span className="hidden sm:inline">{item.label}</span>
              </button>
            ))}
          </div>
        </div>
        {TAB_QUESTION[activeTab] && (
          <div className="mt-3">
            <AskAgent question={TAB_QUESTION[activeTab]!(champion)} />
          </div>
        )}

        <div className="mt-4 flex flex-col gap-3 border-b border-white/[0.07] pb-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h3 className="text-sm font-semibold text-text">{tabs.find((item) => item.key === activeTab)?.label}</h3>
            <p className="mt-1 max-w-2xl text-xs leading-relaxed text-muted">{activeTab === "versus" ? versusCopy : TAB_COPY[activeTab]}</p>
          </div>
          <div className="flex flex-wrap items-center gap-1.5 text-[0.62rem] font-semibold">
            <span className="rounded-full bg-white/[0.05] px-2.5 py-1 text-muted">{tab.recognizedRows}/{tab.sourceRows} rows verified</span>
            {tab.visibleCoverage > 0 && <span className="rounded-full bg-white/[0.05] px-2.5 py-1 text-muted">{Math.min(tab.visibleCoverage, 100).toFixed(1)}% visible pick share</span>}
            <span className="rounded-full bg-emerald-300/10 px-2.5 py-1 text-emerald-200">Updated {formatCaptureDate(lane.capturedAt) ?? formatDataDate(tab.date)}</span>
          </div>
        </div>

        {rows.length ? (
          activeTab === "versus" && lane.versusKind === "matchup" ? (
            <div className="mt-4 grid gap-3 lg:grid-cols-2">
              <MatchupPanel title="Best observed matchups" tone="good" rows={favorable} since={since} />
              <MatchupPanel title="Most difficult matchups" tone="bad" rows={difficult} since={since} />
            </div>
          ) : (
            <>
              <div className="mt-4 grid gap-2.5 lg:grid-cols-2">
                {visibleRows.map((row) => <StandardRow key={`${activeTab}-${row.rank}-${row.entities.map((entity) => entity.name).join("-")}`} row={row} kind={activeTab} since={since} />)}
              </div>
              {rows.length > 6 && (
                <div className="mt-4 flex justify-center">
                  <button type="button" onClick={() => setExpanded((value) => !value)} className="rounded-full border border-white/[0.09] bg-white/[0.035] px-4 py-2 text-xs font-semibold text-muted transition hover:border-accent/25 hover:bg-accent/10 hover:text-accent">
                    {expanded ? "Show fewer" : `Show all ${rows.length}`}
                  </button>
                </div>
              )}
            </>
          )
        ) : (
          <div className="mt-4 rounded-2xl border border-dashed border-white/10 bg-black/10 px-4 py-8 text-center text-sm text-muted">No verified rows are available for this tab yet.</div>
        )}

        <div className="mt-4 flex flex-col gap-2 border-t border-white/[0.07] pt-3 text-[0.65rem] leading-relaxed text-faint sm:flex-row sm:items-center sm:justify-between">
          <p>A higher row win rate does not prove the loadout caused the wins.</p>
          {since && (
            <p className="shrink-0">
              {`Arrows: change since the ${since} capture, shown only for clear moves. Hover one for the numbers.`}
            </p>
          )}
        </div>
      </div>
    </Card>
  );
}
