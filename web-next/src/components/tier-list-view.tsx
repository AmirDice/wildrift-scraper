"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { Champion } from "@/lib/data";
import type { CnBracketKey } from "@/lib/cn";
import { TIER_ORDER, tierClass, tierLabel, site, siteNa } from "@/lib/data";
import { ChampionAvatar } from "@/components/ui";
import { RegionToggle, RegionComingSoon, type Region } from "@/components/region-toggle";
import { CURRENT_PATCH } from "@/lib/patch";
import { moverBySlug } from "@/lib/movers";
import { RegionUpdated } from "@/components/tierlist-updated";

export function TierListView({
  champions,
  roles,
  naChampions,
  naRoles,
  naUpdated,
  cnChampionsByBracket,
  cnRolesByBracket,
  cnMeta,
  globalChampions,
  globalRoles,
  initialRegion = "CN",
  initialCnBracket,
}: {
  champions: Champion[];
  roles: string[];
  naChampions: Champion[];
  naRoles: string[];
  naUpdated?: string | null;
  cnChampionsByBracket: Record<CnBracketKey, Champion[]>;
  cnRolesByBracket: Record<CnBracketKey, string[]>;
  cnMeta: {
    source: string;
    date: string | null;
    bracket: string;
    defaultBracket: CnBracketKey;
    brackets: readonly {
      key: CnBracketKey;
      label: string;
      short: string;
      kind: "regular" | "legendary";
    }[];
  };
  globalChampions: Champion[];
  globalRoles: string[];
  initialCnBracket?: CnBracketKey;
  /** Which region the list opens on. The region tabs are client state, so this
   *  is what decides which ranking ends up in the server-rendered HTML -- and
   *  therefore which one a crawler can read. See /tier-list/china. */
  initialRegion?: Region;
}) {
  const [role, setRole] = useState<string>("All roles");
  const [region, setRegion] = useState<Region>(initialRegion);
  // Pool depth: how many of each champion's top players feed the number.
  // EU and NA, which are both our own top-50 scrape and both export the same
  // depth slices. CN offers no slider because its figures are Tencent's own
  // bracket aggregates -- there are no per-player rows to re-slice. Global is
  // excluded for a different reason: the blend carries only EU's pool slices,
  // so re-slicing would rank a 5-deep EU number against a full-pool NA one.
  const [poolDepth, setPoolDepth] = useState<"all" | "25" | "10" | "5">("all");
  const [cnBracket, setCnBracket] = useState<CnBracketKey>(initialCnBracket ?? cnMeta.defaultBracket);
  // Win rates ship centred so 50% reads as "the average champion". The raw
  // number is what the players actually posted, and people keep asking for it,
  // so it is a toggle rather than a rewrite of the scale.
  const [showRaw, setShowRaw] = useState(false);

  const isCN = region === "CN";
  const isGlobal = region === "Global";
  const isNA = region === "NA";
  const activeCnChampions = cnChampionsByBracket[cnBracket];
  const activeCnRoles = cnRolesByBracket[cnBracket];
  const activeChampions = isCN ? activeCnChampions
    : isGlobal ? globalChampions
    : isNA ? naChampions
    : champions;
  const activeRoles = isCN ? activeCnRoles
    : isGlobal ? globalRoles
    : isNA ? naRoles
    : roles;
  const depthActive = (region === "EU" || region === "NA") && poolDepth !== "all";

  // Undoing the centring needs the offset that was APPLIED, and that differs by
  // region and by pool depth: a shallower pool is the best players of the best
  // players, so it was centred harder (-9.5 at full board, -12.0 at top 5).
  // Each depth therefore carries its own offset in the data.
  const offsetFor = (c: Champion): number => {
    if (isCN) return 0;                       // Tencent publishes raw already
    if (depthActive) return c.pools?.[poolDepth]?.wrOffset ?? 0;
    if (isGlobal) return ((site.wrOffset ?? 0) + (siteNa.wrOffset ?? 0)) / 2;
    return (isNA ? siteNa.wrOffset : site.wrOffset) ?? 0;
  };
  const shownWr = (c: Champion): number => (showRaw ? c.wr - offsetFor(c) : c.wr);

  const activeCnBracket = cnMeta.brackets.find((option) => option.key === cnBracket)
    ?? cnMeta.brackets.find((option) => option.key === cnMeta.defaultBracket)!;
  const options = useMemo(() => ["All roles", ...activeRoles], [activeRoles]);

  // The whole EU field drifted up between the June and August collections: the
  // median wrDelta is +1.20 and 104 of 138 champions are positive. Left raw,
  // three quarters of the Global list would wear an up arrow, which says
  // nothing about any of them. Subtracting the median makes movement mean
  // "moved relative to the field", the same correction wrOffset applies to the
  // win rates themselves. Computed from the data so it tracks each refresh.
  const euDrift = useMemo(() => {
    const deltas = champions
      .map((c) => c.wrDelta)
      .filter((d): d is number => typeof d === "number")
      .sort((a, b) => a - b);
    if (!deltas.length) return 0;
    const mid = Math.floor(deltas.length / 2);
    return deltas.length % 2 ? deltas[mid] : (deltas[mid - 1] + deltas[mid]) / 2;
  }, [champions]);

  const buckets = useMemo(() => {
    const inRole = options.includes(role) ? role : "All roles";
    const pool =
      inRole === "All roles" ? activeChampions : activeChampions.filter((c) => c.role === inRole);
    // At a shallower depth every champion is re-read through its pools slice:
    // wr, tier and role-tier all come from that depth, so the toggle changes
    // the RANKING, not just the printed number. A champion with no slice at
    // this depth (fewer counted players than the depth asks for) keeps its
    // full-pool values rather than vanishing.
    const view = (c: Champion) => {
      if (!depthActive) return c;
      const slice = c.pools?.[poolDepth];
      return slice && slice.wr != null
        ? { ...c, wr: slice.wr, tier: slice.tier, tierCss: slice.tierCss,
            tierRole: slice.tierRole, tierRoleCss: slice.tierRoleCss }
        : c;
    };
    const seen = pool.map(view);
    const tierOf = (c: Champion) => (inRole === "All roles" ? c.tier : c.tierRole);
    const map: Record<string, Champion[]> = {};
    for (const t of TIER_ORDER) map[t] = [];
    for (const c of [...seen].sort((a, b) => b.wr - a.wr)) {
      (map[tierOf(c)] ??= []).push(c);
    }
    return map;
  }, [role, activeChampions, options, region, poolDepth, depthActive]);

  return (
    <div>
      {/* Region */}
      <div className="mb-5">
        <RegionToggle region={region} onChange={(next) => { setRegion(next); setRole("All roles"); }} regions={["CN", "EU", "NA", "Global"]} />
      </div>

      <div className="mb-5 flex flex-wrap items-center gap-3">
        <RegionUpdated region={region} euDate={site.collectedOn} cnDate={cnMeta.date} naDate={naUpdated} />
        {/* CN is excluded: Tencent publishes raw rates, so there is no centring
            to undo and the button would be a no-op that implies otherwise. */}
        {!isCN && (
          <button
            type="button"
            aria-pressed={showRaw}
            onClick={() => setShowRaw((v) => !v)}
            className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${
              showRaw ? "bg-accent text-[#07121f]" : "glass glass-hover text-muted"
            }`}
          >
            {showRaw ? "Showing raw win rates" : "Show raw win rates"}
          </button>
        )}
      </div>
      {showRaw && !isCN && (
        <p className="mb-5 text-xs leading-relaxed text-faint">
          Raw numbers: what these players actually posted, un-centred. A champion&rsquo;s top mains
          win far more than half their games, so the whole field sits high and the tiers below still
          come from the centred scale. Order and tier are unchanged either way.
        </p>
      )}

      {activeChampions.length === 0 ? (
        <RegionComingSoon region={region} />
      ) : (
        <>
          {isCN && (
            <div className="mb-5">
              {/* The region tabs are client state, not separate URLs, so this
                  heading is what tells a reader (and a crawler reading the
                  page) which tier list they are looking at and for which patch. */}
              <h2 className="text-lg font-semibold tracking-tight">
                Wild Rift China server tier list
                {CURRENT_PATCH && <span className="text-muted"> · Patch {CURRENT_PATCH}</span>}
              </h2>
              <p className="mt-1 text-sm text-muted">
                Official China server win rates from{" "}
                <span className="text-text">{activeCnBracket.label}</span>
                {activeCnBracket.kind === "legendary"
                  ? ", a separate high-elo solo queue"
                  : activeCnBracket.key === "3"
                    ? ", Tencent's top regular-ranked sample"
                    : ", a cumulative regular-ranked sample"}
                . Source: lolm.qq.com. China usually plays the patch ahead of the West, so this list is the
                earliest read on where the meta is going.
              </p>
              <div className="mt-4 flex flex-wrap gap-2" role="tablist" aria-label="China skill bracket">
                {cnMeta.brackets.map((option) => (
                  <button
                    key={option.key}
                    type="button"
                    role="tab"
                    aria-selected={cnBracket === option.key}
                    onClick={() => { setCnBracket(option.key); setRole("All roles"); }}
                    className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition ${
                      cnBracket === option.key
                        ? "bg-accent text-[#07121f]"
                        : "glass glass-hover text-muted"
                    }`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>
          )}
          {isGlobal && (
            <p className="mb-5 text-sm text-muted">
              Combined <span className="text-text">EU + NA</span> ranking of the champions strongest
              across both western servers. China measures a whole bracket rather than a champion&rsquo;s
              best players, so it is kept separate. See the{" "}
              <Link href="/global" className="text-accent hover:underline">
                side-by-side comparison
              </Link>
              .
            </p>
          )}

          {(region === "EU" || region === "NA") && (
            <div className="mb-5">
              <div className="flex flex-wrap items-center gap-2" role="tablist" aria-label="Player pool depth">
                <span className="text-xs font-bold uppercase tracking-wide text-faint">Player pool</span>
                {([["all", "All players"], ["25", "Top 25"], ["10", "Top 10"], ["5", "Top 5"]] as const).map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    role="tab"
                    aria-selected={poolDepth === key}
                    onClick={() => setPoolDepth(key)}
                    className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition ${
                      poolDepth === key ? "bg-accent text-[#07121f]" : "glass glass-hover text-muted"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <p className="mt-1.5 text-xs text-muted">
                {poolDepth === "all"
                  ? "Win rates from each champion's full top-50 board."
                  : `Win rates from each champion's top ${poolDepth} players only. A champion that is strong here but weak on "All players" is carried by its elite, not its player base.`}
              </p>
            </div>
          )}

          {/* Role filter */}
          <div className="mb-6 flex flex-wrap gap-2">
            {options.map((o) => (
              <button
                key={o}
                onClick={() => setRole(o)}
                className={`rounded-full px-4 py-1.5 text-sm font-medium transition ${
                  role === o ? "bg-accent text-[#07121f]" : "glass glass-hover text-muted"
                }`}
              >
                {o}
              </button>
            ))}
          </div>

          {/* Tiers */}
          <div className="flex flex-col gap-2.5">
            {TIER_ORDER.map((t) => {
              const champs = buckets[t] ?? [];
              // An empty tier keeps its row. Hiding it made the ladder look
              // like it simply had no L tier -- spotted on Global/Baron, where
              // nobody is bad enough to land there -- and a missing band reads
              // as broken rendering rather than as the (interesting) fact that
              // the band is genuinely unoccupied.
              if (champs.length === 0) {
                return (
                  <div key={t} className="flex items-stretch gap-1.5 opacity-45 sm:gap-2.5">
                    <div
                      className={`grid w-11 shrink-0 place-items-center rounded-xl text-lg font-black sm:w-20 sm:text-2xl ${tierClass[t]}`}
                    >
                      {tierLabel(t)}
                    </div>
                    <div className="glass flex flex-1 items-center rounded-xl p-2 text-sm text-faint sm:p-4">
                      No champions in this tier
                    </div>
                  </div>
                );
              }
              return (
                <div key={t} className="flex items-stretch gap-1.5 sm:gap-2.5">
                  <div
                    className={`grid w-11 shrink-0 place-items-center rounded-xl text-lg font-black sm:w-20 sm:text-2xl ${tierClass[t]}`}
                  >
                    {tierLabel(t)}
                  </div>
                  <div className="glass flex flex-1 flex-wrap content-center gap-x-1.5 gap-y-2 rounded-xl p-2 sm:gap-4 sm:p-4">
                    {champs.map((c) => {
                      const cnMovement = isCN ? moverBySlug(c.slug, cnBracket) : null;
                      // Global movement comes from EU alone, halved because EU
                      // is half of the EU + NA average. NA is deliberately not
                      // blended in: its baseline is 2026-08-08 against EU's
                      // 2026-06-13, and it carries a delta for only 74 of 140
                      // champions, so averaging a three-day window with a
                      // two-month one would produce a number measuring nothing.
                      // Revisit once NA has a second collection behind it.
                      // Deltas are computed raw-vs-raw at export, so the display
                      // centering never leaks into them.
                      const share = c.globalParts ?? 2;
                      const globalDelta = c.wrDelta != null
                        ? Math.round(((c.wrDelta - euDrift) / share) * 100) / 100
                        : null;
                      const mv = isGlobal
                        ? globalDelta != null
                          ? {
                              oldWr: Math.round((c.wr - globalDelta) * 100) / 100,
                              newWr: c.wr,
                              delta: globalDelta,
                            }
                          : null
                        : isCN
                          ? cnMovement
                          : c.wrDelta != null
                            ? {
                                oldWr: Math.round((c.wr - c.wrDelta) * 10) / 10,
                                newWr: c.wr,
                                delta: c.wrDelta,
                              }
                            : null;
                      // The EU arrow means "crossed a tier boundary", nothing
                      // less: a tier is what this list ranks, so half a point
                      // of wobble inside GOD is fine print (the small +/-
                      // under the win rate), not a badge. CN keeps its
                      // delta-based badge: its brackets re-rank week to week
                      // and tier labels are not comparable across them.
                      const euTierMove = !isCN && !isGlobal ? c.tierMoved : null;
                      const up = isCN || isGlobal ? Boolean(mv && mv.delta > 0) : euTierMove === "up";
                      const changed = isCN || isGlobal
                        ? Boolean(mv && Math.abs(mv.delta) >= 0.05)
                        : Boolean(euTierMove);
                      return (
                        <Link
                          key={c.slug}
                          href={`/champions/${c.slug}`}
                          className="group flex w-[46px] flex-col items-center text-center transition sm:w-[68px]"
                          title={changed && mv
                            ? `${c.name} · ${shownWr(c).toFixed(1)}% WR · ${isGlobal ? "CN update impact on Global" : isCN ? "previous CN scrape" : `since ${site.movementSince ?? "the previous collection"}`}${!isCN && !isGlobal && c.prevTier ? ` ${c.prevTier} → ${c.tier},` : ""} ${mv.oldWr}% → ${mv.newWr}% (${mv.delta > 0 ? "+" : ""}${mv.delta})`
                            : `${c.name} · ${shownWr(c).toFixed(1)}% WR`}
                        >
                          <span className="relative transition group-hover:-translate-y-0.5">
                            <ChampionAvatar champion={c} size={52} mobileSize={38} />
                            {/* top-LEFT, because the OTP badge owns the
                                top-right corner of the avatar and an OTP
                                riser was showing exactly one of the two. */}
                            {changed && mv && (
                              <span className={`absolute -left-1.5 -top-1 rounded-full px-1 text-[0.55rem] font-bold text-white ring-1 ring-black/30 ${up ? "bg-emerald-500" : "bg-bad"}`}>
                                {up ? "▲" : "▼"}
                              </span>
                            )}
                          </span>
                          <span className="mt-1.5 w-full truncate text-[0.7rem] font-medium leading-tight">
                            {c.name}
                          </span>
                          <span className="text-[0.7rem] font-semibold text-accent">
                            {shownWr(c).toFixed(1)}%
                            {mv && (changed || (!isCN && !isGlobal && Math.abs(mv.delta) >= 0.5)) && (
                              <span className={`ml-1 ${mv.delta > 0 ? "text-emerald-400" : "text-bad"}`}>
                                {mv.delta > 0 ? "+" : ""}{mv.delta}
                              </span>
                            )}
                          </span>
                        </Link>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Legend */}
          <div className="glass mt-6 rounded-xl p-4 text-sm text-muted">
            {isCN ? (
              <p>
                <span className="font-medium text-text">CN tier cutoffs</span>: official CN win
                rates centre on 50%, so tiers use a China-specific scale. GOD 53.5%+ · S 52–53.5% ·
                A 50.8–52% · B 49.5–50.8% · C 48–49.5% · L under 48%.
              </p>
            ) : isGlobal ? (
              <p>
                <span className="font-medium text-text">Global cutoffs</span>: the average of the
                EU and NA win rates (both 50%-centred). GOD 53.5%+ · S 52–53.5% · A 50.8–52% · B
                49.5–50.8% · C 48–49.5% · L under 48%.
              </p>
            ) : role === "All roles" ? (
              (() => {
                const o = site.wrOffset ?? 0;
                const c = (n: number) => (n + o).toFixed(1);
                return (
                  <p>
                    <span className="font-medium text-text">Win rate shown relative to average</span>:{" "}
                    every champion here is carried by its top-50 mains, so the pool naturally sits
                    high; we centre it so 50% = the average champion and you can read the gap at a
                    glance. Tier cutoffs: GOD {c(63)}%+ · S {c(61)}–{c(63)}% · A {c(59)}–{c(61)}% · B{" "}
                    {c(57)}–{c(59)}% · C {c(56)}–{c(57)}% · L under {c(56)}%.
                  </p>
                );
              })()
            ) : (
              <p>
                <span className="font-medium text-text">Percentile cutoffs within {role}</span>: a
                single role&rsquo;s win-rate range is narrower than the whole pool, so tiers adapt to
                keep every tier populated.
              </p>
            )}
          </div>
        </>
      )}
    </div>
  );
}
