"use client";

import Link from "next/link";
import { useState } from "react";
import type { ChinaThisWeek as Data, Lane5, Ranked } from "@/lib/china-meta";

/* eslint-disable @next/next/no-img-element */

/**
 * The meta page's "China this week": rising cores, the items and keystones
 * China's Legendary players build most, spells by lane, and what the latest
 * patch moved. Everything comes from the pooled weekly loadout captures, so
 * it changes when a new capture lands, not on every page load.
 */
const LANES: Lane5[] = ["baron", "jungle", "mid", "dragon", "support"];
const LANE_NAME: Record<Lane5, string> = { baron: "Baron", jungle: "Jungle", mid: "Mid", dragon: "Dragon", support: "Support" };
const TABS = [
  { key: "rising", label: "Rising" },
  { key: "duos", label: "Duos" },
  { key: "items", label: "Top items" },
  { key: "keystones", label: "Keystones" },
  { key: "spells", label: "Spells" },
  { key: "patch", label: "Patch impact" },
] as const;
type TabKey = (typeof TABS)[number]["key"];

const day = (mmdd: string) => {
  const [m, d] = mmdd.split("-").map(Number);
  return `${d} ${["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][m - 1]}`;
};

function Pills<T extends string>({ value, options, onChange, label }: { value: T; options: [T, string][]; onChange: (value: T) => void; label: string }) {
  return (
    <div role="tablist" aria-label={label} className="flex max-w-full gap-1 overflow-x-auto rounded-xl border border-white/[0.08] bg-black/15 p-1">
      {options.map(([key, text]) => (
        <button key={key} type="button" role="tab" aria-selected={value === key} onClick={() => onChange(key)}
          className={`shrink-0 rounded-lg px-3 py-1.5 text-xs font-semibold transition ${value === key ? "bg-sky-300/15 text-sky-200 ring-1 ring-sky-300/20" : "text-muted hover:bg-white/[0.04] hover:text-text"}`}>
          {text}
        </button>
      ))}
    </div>
  );
}

function RankedList({ rows, unit }: { rows: Ranked[]; unit: string }) {
  const max = Math.max(...rows.map((row) => row.presence), 1);
  return (
    <ol className="grid gap-2 sm:grid-cols-2">
      {rows.map((row, index) => (
        <li key={row.name} className="flex items-center gap-3 rounded-xl border border-white/[0.07] bg-black/15 p-2.5">
          <span className="w-5 shrink-0 text-right text-xs font-semibold tabular-nums text-faint">{index + 1}</span>
          <img src={row.icon} alt="" className="h-9 w-9 shrink-0 rounded-lg border border-white/10 bg-black/25" loading="lazy" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold">{row.href ? <Link href={row.href} className="hover:text-accent">{row.name}</Link> : row.name}</p>
            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
              <div className="h-full rounded-full bg-sky-300/70" style={{ width: `${(row.presence / max) * 100}%` }} />
            </div>
          </div>
          <div className="shrink-0 text-right">
            <p className="text-sm font-semibold tabular-nums">{row.presence.toFixed(1)}%</p>
            <p className="text-[0.62rem] text-faint">{`${row.winRate.toFixed(1)}% WR · ${row.lanes} ${row.lanes === 1 ? "lane" : "lanes"} ${unit}`}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}

export function ChinaThisWeek({ data }: { data: Data }) {
  const [tab, setTab] = useState<TabKey>("rising");
  const [lane, setLane] = useState<Lane5 | "all">("all");
  const [queueId, setQueueId] = useState(data.duos[0]?.id ?? "");
  const queue = data.duos.find((q) => q.id === queueId) ?? data.duos[0];
  const laneOptions: [Lane5 | "all", string][] = [["all", "All lanes"], ...LANES.map((l): [Lane5, string] => [l, LANE_NAME[l]])];
  const span = data.window ? `${data.window.captures} captures, ${day(data.window.from.slice(5))} to ${day(data.window.to.slice(5))}` : "latest capture";

  return (
    <section id="china-this-week" className="mt-10 scroll-mt-24">
      <div className="glass rounded-[1.5rem] border border-white/[0.09] p-5 sm:p-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-[0.65rem] font-bold uppercase tracking-[0.16em] text-sky-200">China Legendary · this week</p>
            <h2 className="mt-1 text-xl font-semibold tracking-tight">What China&rsquo;s top players are building</h2>
            <p className="mt-1 max-w-2xl text-sm text-muted">{`Every champion's loadouts in China's Legendary queue, pooled over the ${span}. Shares are of each lane's games; China gives no game counts, so every lane counts once.`}</p>
          </div>
          <Pills value={tab} options={TABS.filter((t) => t.key !== "duos" || data.duos.length).map((t): [TabKey, string] => [t.key, t.label])} onChange={setTab} label="China this week" />
        </div>

        {(tab === "items" || tab === "keystones") && (
          <div className="mt-4"><Pills value={lane} options={laneOptions} onChange={setLane} label="Lane" /></div>
        )}
        {tab === "duos" && data.duos.length > 1 && queue && (
          <div className="mt-4"><Pills value={queue.id} options={data.duos.map((q): [string, string] => [q.id, q.label])} onChange={setQueueId} label="Queue" /></div>
        )}

        <div className="mt-4">
          {tab === "rising" && (
            data.rising.length ? (
              <>
                <p className="mb-3 text-xs text-faint">Cores and rune pages at 3%+ of a lane&rsquo;s games that at least doubled their share since the first capture we hold.</p>
                <div className="grid gap-2 lg:grid-cols-2">
                  {data.rising.map((row) => (
                    <Link key={`${row.slug}-${row.lane}-${row.kind}-${row.entities.map((e) => e.name).join()}`} href={`/champions/${row.slug}`}
                      className="flex items-center gap-3 rounded-xl border border-white/[0.07] bg-black/15 p-2.5 transition hover:border-accent/30">
                      <img src={row.icon} alt="" className="h-10 w-10 shrink-0 rounded-full border border-white/10" loading="lazy" />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-semibold">{`${row.champion} · ${LANE_NAME[row.lane as Lane5] ?? row.lane}`}<span className="ml-1.5 text-[0.62rem] font-semibold uppercase tracking-wide text-faint">{row.kind === "items" ? "core" : "rune page"}</span></p>
                        <div className="mt-1 flex -space-x-1">
                          {row.entities.map((entity, i) => <img key={`${entity.name}-${i}`} src={entity.icon} alt={entity.name} title={entity.name} className="h-6 w-6 rounded-md border border-black/40 bg-black/30" loading="lazy" />)}
                        </div>
                      </div>
                      <div className="shrink-0 text-right">
                        <p className="text-sm font-semibold tabular-nums text-emerald-300">{`${row.from.toFixed(1)}% → ${row.to.toFixed(1)}%`}</p>
                        <p className="text-[0.62rem] text-faint">{`of games since ${day(row.since)} · ${row.winRate.toFixed(1)}% WR`}</p>
                      </div>
                    </Link>
                  ))}
                </div>
              </>
            ) : <p className="text-sm text-muted">Nothing has clearly taken off in the captures we hold yet.</p>
          )}
          {tab === "items" && <><p className="mb-3 text-xs text-faint">Share of games whose three-item core includes the item, averaged over lanes; the small number counts lanes where it is in 20%+ of cores.</p><RankedList rows={data.items[lane] ?? []} unit="as a core item" /></>}
          {tab === "keystones" && <><p className="mb-3 text-xs text-faint">Share of games on each keystone, averaged over lanes; the small number counts lanes where it is run 20%+ of the time.</p><RankedList rows={data.keystones[lane] ?? []} unit="as a main pick" /></>}
          {tab === "duos" && (
            <>
              <p className="mb-3 text-xs text-faint">The best pairs for each lane pairing, from China&rsquo;s best-partner lists. Win rates are pulled toward each list&rsquo;s average by how rarely the pair is seen.</p>
              <div className="grid gap-3 lg:grid-cols-2">
                {(queue?.groups ?? []).map((group) => (
                  <div key={group.lanes.join("+")} className="rounded-xl border border-white/[0.07] bg-black/15 p-3">
                    <p className="text-xs font-semibold uppercase tracking-wide text-faint">{group.lanes.map((l) => LANE_NAME[l as Lane5] ?? l).join(" + ")}</p>
                    <ul className="mt-2 space-y-1.5">
                      {group.duos.map((duo) => (
                        <li key={`${duo.a.slug}-${duo.b.slug}`} className="flex items-center gap-2 text-sm">
                          <Link href={`/champions/${duo.a.slug}`} className="flex min-w-0 items-center gap-1.5 hover:text-accent"><img src={duo.a.icon} alt="" className="h-7 w-7 rounded-full" loading="lazy" /><span className="truncate">{duo.a.name}</span></Link>
                          <span className="text-faint">+</span>
                          <Link href={`/champions/${duo.b.slug}`} className="flex min-w-0 flex-1 items-center gap-1.5 hover:text-accent"><img src={duo.b.icon} alt="" className="h-7 w-7 rounded-full" loading="lazy" /><span className="truncate">{duo.b.name}</span></Link>
                          <span className="shrink-0 text-right text-xs"><span className="font-semibold tabular-nums text-emerald-300">{`${duo.winRate.toFixed(1)}%`}</span><span className="block text-[0.6rem] text-faint">{`${duo.pickRate.toFixed(2)}% of games`}</span></span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </>
          )}
          {tab === "spells" && (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              {LANES.map((l) => (
                <div key={l} className="rounded-xl border border-white/[0.07] bg-black/15 p-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-faint">{LANE_NAME[l]}</p>
                  <ul className="mt-2 space-y-2">
                    {data.spells[l].map((pair) => (
                      <li key={pair.pair} className="flex items-center gap-2" title={`${pair.pair}: ${pair.share.toFixed(1)}% of games, ${pair.winRate.toFixed(1)}% WR`}>
                        <span className="flex -space-x-1">{pair.icons.map((icon, i) => <img key={i} src={icon} alt="" className="h-6 w-6 rounded-md border border-black/40" loading="lazy" />)}</span>
                        <span className="min-w-0 flex-1 truncate text-xs">{pair.pair}</span>
                        <span className="text-xs font-semibold tabular-nums">{pair.share.toFixed(0)}%</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}
          {tab === "patch" && (
            data.patch?.shifts.length ? (
              <>
                <Link href={`/patch-impact/${data.patch.patch}`}
                  className="mb-4 flex items-center justify-between gap-3 rounded-xl border border-sky-300/25 bg-sky-300/[0.06] px-4 py-3 text-sm transition hover:border-sky-300/45">
                  <span><span className="font-semibold text-sky-200">{`Patch ${data.patch.patch} impact:`}</span> <span className="text-muted">every changed item and rune before and after, by role, and who moved most.</span></span>
                  <span className="shrink-0 font-semibold text-sky-200">Read it →</span>
                </Link>
                <p className="mb-3 text-xs text-faint">{`For the champions patch ${data.patch.patch} changed: the core that gained the most share of games since the ${day(data.patch.before)} capture, before the patch, and the one that lost the most. Moves under 2 points are left out.`}</p>
                <div className="grid gap-2 lg:grid-cols-2">
                  {data.patch.shifts.map((shift) => (
                    <div key={`${shift.slug}-${shift.lane}`} className="rounded-xl border border-white/[0.07] bg-black/15 p-3">
                      <Link href={`/champions/${shift.slug}`} className="flex items-center gap-2 text-sm font-semibold hover:text-accent">
                        <img src={shift.icon} alt="" className="h-7 w-7 rounded-full" loading="lazy" />{`${shift.champion} · ${LANE_NAME[shift.lane as Lane5] ?? shift.lane}`}
                      </Link>
                      {shift.gained && <p className="mt-2 text-xs"><span className="font-semibold text-emerald-300">{`▲ ${shift.gained.from.toFixed(1)}% → ${shift.gained.to.toFixed(1)}%`}</span> <span className="text-muted">{shift.gained.entities.join(" · ")}</span></p>}
                      {shift.lost && <p className="mt-1 text-xs"><span className="font-semibold text-rose-300">{`▼ ${shift.lost.from.toFixed(1)}% → ${shift.lost.to.toFixed(1)}%`}</span> <span className="text-muted">{shift.lost.entities.join(" · ")}</span></p>}
                    </div>
                  ))}
                </div>
              </>
            ) : <p className="text-sm text-muted">No capture from before the latest patch to compare against yet.</p>
          )}
        </div>
      </div>
    </section>
  );
}
