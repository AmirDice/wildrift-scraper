"use client";

import { useEffect, useState } from "react";
import runeIconsData from "@/data/rune_icons.json";
import { BUILD_SERVERS, SERVER_GAP, SERVER_LABEL, type BuildServer, type ServerBuild, type ServerBuildStats } from "@/lib/server-build";

/** Rune name to picture. 2.4KB for 53 runes, and it covers every rune name the
 *  ladder records contain (checked across all 141), so the items in this card
 *  are no longer the only things in it with a face. */
const RUNE_ICONS = runeIconsData as Record<string, string>;

/* eslint-disable @next/next/no-img-element */

/**
 * What the top 50 build, per server.
 *
 * The site already splits win rates by board -- EU, NA and China disagree
 * about who is strong -- and they disagree about what to buy for the same
 * reason. One merged "most common build" hides exactly the thing worth
 * knowing, so each server answers for itself here.
 *
 * A server with nothing to show says WHY, in its own words. That matters most
 * for China: Tencent publishes win, pick and ban rates and no item data at
 * all, so that tab is not "loading" or "coming soon", it is a wall. Saying so
 * costs one line and stops it reading as a bug.
 *
 * The data is per-champion and passed in from the server component: the full
 * per-server records are ~100KB each, and no champion page needs 141 of them
 * in the browser.
 */

/** The six to draw, left to right: the purchase order with the boots slotted
 *  in where they are bought, or most-built first with the boots last when no
 *  order was recorded. */
function sequenceOf(build: ServerBuild): { slug: string; name: string; icon: string }[] {
  const boots = build.boots ?? null;
  if (!boots) return build.items;
  if (build.ordered && build.bootsAt != null) {
    const at = Math.max(0, Math.min(build.bootsAt, build.items.length));
    return [...build.items.slice(0, at), boots, ...build.items.slice(at)];
  }
  return [...build.items, boots];
}

function compactNumber(value: number | undefined, digits = 0): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return value.toLocaleString(undefined, { maximumFractionDigits: digits });
}

function joinedLabels(servers: BuildServer[]): string {
  return servers.map((s) => SERVER_LABEL[s]).join(" + ");
}

/** Small, defensible comparisons for the collapsed card. These compare the
 * same engine estimate across server builds; they never imply a server's
 * observed win rate came from the item build. */
function comparisonPills(
  server: BuildServer,
  builds: Partial<Record<BuildServer, ServerBuild | null>>,
): string[] {
  const current = builds[server]?.stats;
  if (!current) return [];
  const others = BUILD_SERVERS.filter((s) => s !== server && builds[s]?.stats);
  const pills: string[] = [];
  const higherThan = (key: keyof ServerBuildStats, margin = 1.01) =>
    others.filter((s) => {
      const value = builds[s]?.stats?.[key];
      const ours = current[key];
      return typeof ours === "number" && typeof value === "number" && ours > value * margin;
    });

  const dps = higherThan("dps8", 1.015);
  if (dps.length) pills.push(`Higher engine DPS than ${joinedLabels(dps)}`);
  const burst = higherThan("burst3", 1.015);
  if (burst.length) pills.push(`Higher burst than ${joinedLabels(burst)}`);
  const ehp = higherThan("ehp", 1.015);
  if (ehp.length) pills.push(`Tougher profile than ${joinedLabels(ehp)}`);

  const lowerCost = others.filter((s) => {
    const value = builds[s]?.stats?.cost;
    return typeof value === "number" && current.cost + 150 < value;
  });
  if (lowerCost.length) pills.push(`Costs less than ${joinedLabels(lowerCost)}`);

  const sample = builds[server]?.sample;
  if (sample && sample.of > 0 && sample.count / sample.of >= 0.5) {
    pills.push(`Strong consensus · ${sample.count}/${sample.of}`);
  }
  return pills.slice(0, 4);
}

function StatCell({ label, value, suffix = "", digits = 0 }: {
  label: string;
  value: number | undefined | null;
  suffix?: string;
  digits?: number;
}) {
  return (
    <div className="rounded-lg bg-white/[0.035] px-2.5 py-2">
      <p className="text-[10px] uppercase tracking-wide text-faint">{label}</p>
      <p className="mt-0.5 text-sm font-semibold text-text">
        {typeof value === "number" ? `${compactNumber(value, digits)}${suffix}` : "—"}
      </p>
    </div>
  );
}

function ServerStats({ stats }: { stats: ServerBuildStats }) {
  return (
    <div className="mt-3 rounded-xl border border-line/60 bg-black/10 p-3">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <StatCell label="8s DPS" value={stats.dps8} />
        <StatCell label="3s burst" value={stats.burst3} />
        <StatCell label="TTK · squishy" value={stats.ttk} suffix="s" />
        <StatCell label="Effective HP" value={stats.ehp} />
        <StatCell label="Attack damage" value={stats.ad} />
        <StatCell label="Ability power" value={stats.ap} />
        <StatCell label="Attack speed" value={stats.attackSpeed} digits={2} />
        <StatCell label="Crit" value={stats.crit} suffix="%" />
        <StatCell label="Health" value={stats.hp} />
        <StatCell label="Armor / MR" value={stats.armor != null && stats.mr != null ? stats.armor : undefined}
          suffix={stats.armor != null && stats.mr != null ? ` / ${compactNumber(stats.mr)}` : ""} />
        <StatCell label="Ability haste" value={stats.haste} />
        <StatCell label="Build cost" value={stats.cost} suffix="g" />
        <StatCell label="Sustain · 8s" value={stats.sustain} />
        <StatCell label="Move speed" value={stats.moveSpeed} />
        <StatCell label="Armor pen" value={stats.physicalPenFlat} suffix={stats.physicalPen ? ` + ${compactNumber(stats.physicalPen)}%` : ""} />
        <StatCell label="Mana" value={stats.mana} />
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {stats.profile.map((label) => (
          <span key={label} className="rounded-full bg-accent/10 px-2 py-0.5 text-[10px] font-semibold text-accent">
            {label}
          </span>
        ))}
        {stats.lifesteal != null && stats.lifesteal > 0 && (
          <span className="rounded-full bg-white/[0.06] px-2 py-0.5 text-[10px] text-muted">
            {compactNumber(stats.lifesteal)}% lifesteal
          </span>
        )}
        {stats.physicalPenFlat != null && stats.physicalPenFlat > 0 && (
          <span className="rounded-full bg-white/[0.06] px-2 py-0.5 text-[10px] text-muted">
            {compactNumber(stats.physicalPenFlat)} flat pen
          </span>
        )}
      </div>
      <p className="mt-3 text-[10px] leading-relaxed text-faint">
        Level 15 engine profile against standard reference targets. DPS, burst, TTK and effective HP are estimates for comparing these loadouts, not observed server performance.
      </p>
    </div>
  );
}

function ServerComparison({ builds }: {
  builds: Partial<Record<BuildServer, ServerBuild | null>>;
}) {
  const available = BUILD_SERVERS.filter((s) => builds[s]?.stats);
  if (available.length < 2) return null;
  return (
    <div className="mt-3 rounded-xl border border-line/60 bg-black/10 p-3">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-faint">
        Compare available server profiles
      </p>
      <div className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {available.map((s) => {
          const stats = builds[s]?.stats;
          if (!stats) return null;
          return (
            <div key={s} className="rounded-lg bg-white/[0.035] p-2.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-bold text-text">{SERVER_LABEL[s]}</span>
                <span className="text-[10px] text-faint">{builds[s]?.sample
                  ? `${builds[s]?.sample?.count}/${builds[s]?.sample?.of} item consensus`
                  : "ladder build"}</span>
              </div>
              <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
                <span className="text-faint">8s DPS</span><span className="text-right font-semibold text-accent">{compactNumber(stats.dps8)}</span>
                <span className="text-faint">3s burst</span><span className="text-right font-semibold text-text">{compactNumber(stats.burst3)}</span>
                <span className="text-faint">Effective HP</span><span className="text-right font-semibold text-text">{compactNumber(stats.ehp)}</span>
                <span className="text-faint">Cost</span><span className="text-right font-semibold text-text">{compactNumber(stats.cost)}g</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function ServerBuilds({
  champion,
  builds,
  gaps,
  collected,
}: {
  champion: string;
  builds: Partial<Record<BuildServer, ServerBuild | null>>;
  /** Why a server is empty, when it is. */
  gaps: Record<BuildServer, string>;
  /** When each server's boards were collected, for the honesty line. */
  collected?: Partial<Record<BuildServer, string>>;
}) {
  // Open on a server that actually has something, so the card never greets
  // anyone with an empty tab when a filled one exists.
  const first = BUILD_SERVERS.find((s) => builds[s]) ?? "eu";
  const [server, setServer] = useState<BuildServer>(first);
  const [expanded, setExpanded] = useState(false);
  const build = builds[server] ?? null;
  const pills = comparisonPills(server, builds);

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        {BUILD_SERVERS.map((s) => (
          <button
            key={s}
            onClick={() => setServer(s)}
            className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
              server === s ? "bg-accent text-white"
                : builds[s] ? "glass text-muted hover:text-text"
                : "glass text-faint hover:text-muted"
            }`}
          >
            {SERVER_LABEL[s]}
            {!builds[s] && <span className="ml-1 opacity-60">·</span>}
          </button>
        ))}
      </div>

      {build ? (
        <>
          {/* Numbered ONLY when the numbers mean something. With a recorded
              purchase order the six are shown in the order the top players buy
              them, boots where they are actually bought -- 63% of players buy
              them first or second, so tacking them on at the end misstated
              the build. Without one, a number would read as an order that is
              really a popularity rank, so there is none. */}
          {build.ordered && (
            <p className="mt-3 text-[11px] font-semibold uppercase tracking-wide text-faint">
              In the order they buy them
            </p>
          )}
          <div className={`${build.ordered ? "mt-2" : "mt-4"} flex flex-wrap items-start gap-2.5`}>
            {sequenceOf(build).map((it, i) => (
              <span key={it.slug} className="w-16 text-center">
                <img src={it.icon} alt={it.name} loading="lazy"
                  className="mx-auto h-11 w-11 rounded-lg border border-line" />
                <span className="mt-1 block text-[10px] leading-tight text-muted">
                  {build.ordered ? `${i + 1}. ` : ""}{it.name}
                </span>
              </span>
            ))}
          </div>
          {build.runes.keystone && (
            <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 text-xs text-muted">
              {[
                { name: build.runes.keystone, keystone: true, flex: false },
                ...build.runes.minors.map((name) => ({ name, keystone: false, flex: false })),
                ...(build.runes.flex
                  ? [{ name: build.runes.flex, keystone: false, flex: true }]
                  : []),
              ].map((rune, i) => (
                <span key={`${rune.name}-${i}`} className="flex items-center gap-1.5">
                  {RUNE_ICONS[rune.name] && (
                    <img
                      src={RUNE_ICONS[rune.name]}
                      alt=""
                      loading="lazy"
                      className={`rounded-full ${rune.keystone ? "h-7 w-7" : "h-6 w-6"}`}
                    />
                  )}
                  <span className={rune.keystone ? "font-semibold text-text" : ""}>
                    {rune.name}
                    {rune.flex && <span className="ml-1 text-faint">(flex)</span>}
                  </span>
                </span>
              ))}
            </div>
          )}
          {(pills.length > 0 || build.stats?.profile) && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {build.stats?.profile.map((label) => (
                <span key={label} className="rounded-full bg-accent/10 px-2.5 py-1 text-[10px] font-semibold text-accent">
                  {label}
                </span>
              ))}
              {pills.map((pill) => (
                <span key={pill} className="rounded-full bg-white/[0.06] px-2.5 py-1 text-[10px] font-medium text-muted">
                  {pill}
                </span>
              ))}
            </div>
          )}
          <p className="mt-2 text-[11px] text-faint">
            {build.sample
              ? `${champion}'s most-built item on ${SERVER_LABEL[server]}: ${build.sample.count} of ${build.sample.of} top players`
              : `From the ${SERVER_LABEL[server]} boards`}
            {collected?.[server] ? ` · collected ${collected[server]}` : ""}
          </p>
          {build.stats && (
            <>
              <button
                type="button"
                onClick={() => setExpanded((value) => !value)}
                className={`mt-3 inline-flex items-center gap-2 rounded-lg border px-4 py-2 text-xs font-bold shadow-sm transition focus:outline-none focus:ring-2 focus:ring-accent/40 ${expanded
                  ? "border-line bg-white/[0.08] text-text hover:border-accent/50"
                  : "border-accent/50 bg-accent/15 text-accent hover:bg-accent/25"}`}
                aria-expanded={expanded}
              >
                <span>{expanded ? "Show less" : "Show more · build stats"}</span>
                <span aria-hidden="true" className={`text-sm leading-none transition-transform ${expanded ? "rotate-180" : ""}`}>⌄</span>
              </button>
              {expanded && (
                <>
                  <ServerStats stats={build.stats} />
                  <ServerComparison builds={builds} />
                </>
              )}
            </>
          )}
        </>
      ) : (
        <p className="mt-4 text-sm text-muted">{gaps[server]}</p>
      )}
    </div>
  );
}

/**
 * The same card, fetching its own champion.
 *
 * The Build Studio changes champion without navigating, so it cannot be
 * handed this from the server the way a champion page is; it asks
 * /api/ladder-build instead, which keeps the per-server records off the
 * browser bundle.
 */
export function ServerBuildsPanel({ champion }: { champion: string }) {
  const [data, setData] = useState<{
    builds: Partial<Record<BuildServer, ServerBuild | null>>;
    collected?: Partial<Record<BuildServer, string>>;
  } | null>(null);

  useEffect(() => {
    let live = true;
    setData(null);
    fetch(`/api/ladder-build?champion=${encodeURIComponent(champion)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (live && d) setData(d); })
      .catch(() => {});
    return () => { live = false; };
  }, [champion]);

  return (
    <div className="glass rounded-2xl p-4 sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-bold uppercase tracking-wide text-muted">
          Most-built by server
        </h3>
        <span className="text-[11px] text-faint">what the top players hold, not what we recommend</span>
      </div>
      <div className="mt-3">
        {data ? (
          <ServerBuilds
            champion={champion}
            builds={data.builds}
            gaps={SERVER_GAP}
            collected={data.collected}
          />
        ) : (
          <p className="text-sm text-faint">Reading the boards…</p>
        )}
      </div>
    </div>
  );
}
