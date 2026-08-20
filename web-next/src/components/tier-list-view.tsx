"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { Champion } from "@/lib/data";
import { cnTier, globalTier, type CnBracketKey } from "@/lib/cn";
import { TIER_ORDER, tierClass, tierLabel, site, siteNa } from "@/lib/data";
import { ChampionAvatar } from "@/components/ui";
import { RegionToggle, RegionComingSoon, type Region } from "@/components/region-toggle";
import { CURRENT_PATCH } from "@/lib/patch";
import { moverBySlug } from "@/lib/movers";

/** "up" / "down" if two tier labels differ, else null.
 *
 *  TIER_ORDER runs best-first, so a SMALLER index is a better tier and moving
 *  to a smaller index is moving up. An unknown label yields null rather than a
 *  wrong arrow.
 */
/** "+1.2" / "-0.4" / "0.0". A measured no-change is shown as 0.0 rather than
 *  "+0", which reads as a bug, and rather than being hidden, which reads as
 *  missing data. */
function deltaText(delta: number): string {
  // Always one decimal. JSON drops the trailing zero, so a champion that moved
  // a whole point printed "+1" in a row of "+0.3"s and read like a different
  // kind of number.
  return `${delta > 0 ? "+" : delta < 0 ? "−" : ""}${Math.abs(delta).toFixed(1)}`;
}

/** Green up, red down, muted for no change -- a grey zero does not claim a
 *  direction it does not have. */
function deltaClass(delta: number): string {
  if (delta === 0) return "text-faint";
  return delta > 0 ? "text-emerald-400" : "text-bad";
}

function crossing(before: string, after: string): "up" | "down" | null {
  if (before === after) return null;
  const a = (TIER_ORDER as readonly string[]).indexOf(before);
  const b = (TIER_ORDER as readonly string[]).indexOf(after);
  if (a < 0 || b < 0) return null;
  return b < a ? "up" : "down";
}
import { RegionUpdated } from "@/components/tierlist-updated";
import { PatchLagNotice } from "@/components/patch-lag-notice";
import { BuildTour, type TourStep } from "@/components/build-tour";
import type { Freshness } from "@/lib/patch-freshness";

/** First-run tour. The page grew four regions, a depth slider, a raw toggle
 *  and CN brackets faster than anyone could be expected to notice them, and
 *  the toggles explain themselves only if you already know they exist. */
const TIER_LIST_TOUR: TourStep[] = [
  {
    target: "tl-regions",
    title: "Four boards, one list",
    body: "EU and NA are our own scrape of each champion's 50 best players. CN is Tencent's official bracket data with its own rank picker. Global, the default, averages EU and NA.",
  },
  {
    target: "tl-updated",
    title: "Dates, and raw numbers",
    body: "Every board says when it was collected, and a notice appears whenever a patch has landed since. Win rates are centred so 50% reads as the average champion; the raw toggle shows what the players actually posted.",
  },
  {
    target: "tl-pool",
    title: "Player pool depth",
    optional: true,
    body: "Re-rank by each champion's top 25, 10 or 5 players instead of the full board. A champion strong at top 5 but weak on all players is carried by its elite. EU, NA and Global only; CN has no per-player rows.",
  },
  {
    target: "tl-roles",
    title: "Role tiers",
    body: "Pick a lane and the tiers become percentiles within that role, so a strong support is measured against supports rather than the whole roster.",
  },
  {
    target: "tl-tiers",
    title: "Reading the tiles",
    body: "Arrows mark win-rate movement since the previous collection, the OTP badge marks one-trick champions, and every tile opens that champion's full page.",
  },
];

export function TierListView({
  champions,
  roles,
  naChampions,
  naRoles,
  naUpdated,
  euFreshness = null,
  naFreshness = null,
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
  /** Whether each board was collected before the current patch. Computed on
   *  the server so the 38KB change summary never reaches the client. */
  euFreshness?: Freshness | null;
  naFreshness?: Freshness | null;
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
  // EU, NA and Global. The first two are our own top-50 scrape and export the
  // same depth slices; Global blends those two slices per depth (see
  // blendPools in lib/cn.ts), so its toggle compares like with like rather
  // than a 5-deep EU number against a full-pool NA one. CN offers no slider:
  // its figures are Tencent's bracket aggregates, with no per-player rows to
  // re-slice at all.
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
  const depthActive = !isCN && poolDepth !== "all";

  // CN is excluded: those are Tencent's own daily figures on China's own
  // patch cycle. Global reports the STALER of its two halves, because a
  // blend is only as current as the oldest board in it.
  const activeFreshness = isCN ? null
    : isNA ? naFreshness
    : isGlobal
      ? [euFreshness, naFreshness].filter((f): f is Freshness => Boolean(f?.stale))
          .sort((a, b) => b.daysBefore - a.daysBefore)[0] ?? null
      : euFreshness;

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

  // A role filter changes which BAND a champion is shown in -- buckets sort by
  // tierRole, not tier -- so it has to change which movement is reported too.
  const roleActive = options.includes(role) && role !== "All roles";

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
      <BuildTour storageKey="tour:tier-list:v1" steps={TIER_LIST_TOUR} label="Tour" />
      {/* Region */}
      <div className="mb-5" data-tour="tl-regions">
        <RegionToggle region={region} onChange={(next) => { setRegion(next); setRole("All roles"); }} regions={["CN", "EU", "NA", "Global"]} />
      </div>

      <div className="mb-5 flex flex-wrap items-center gap-3" data-tour="tl-updated">
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
        <a
          href={`/api/tier-card?region=${region}${role !== "All roles" ? `&role=${encodeURIComponent(role)}` : ""}`}
          download={`wr-tier-list-${region.toLowerCase()}${role !== "All roles" ? `-${role.toLowerCase()}` : ""}.png`}
          title="Download this board as a 1200x630 card, made for Discord and Reddit"
          className="glass glass-hover inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold text-muted transition hover:text-text"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               strokeWidth="2" strokeLinecap="round" aria-hidden>
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <circle cx="8.5" cy="8.5" r="1.5" />
            <path d="M21 15l-5-5L5 21" />
          </svg>
          Share as image
        </a>
      </div>
      {showRaw && !isCN && (
        <p className="mb-5 text-xs leading-relaxed text-faint">
          Raw numbers: what these players actually posted, un-centred. A champion&rsquo;s top mains
          win far more than half their games, so the whole field sits high and the tiers below still
          come from the centred scale. Order and tier are unchanged either way.
        </p>
      )}

      {activeFreshness?.stale && (
        <PatchLagNotice freshness={activeFreshness} className="mb-5" />
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

          {!isCN && (
            <div className="mb-5" data-tour="tl-pool">
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
          <div className="mb-6 flex flex-wrap gap-2" data-tour="tl-roles">
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
          <div className="flex flex-col gap-2.5" data-tour="tl-tiers">
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
                      // The arrow means "crossed a tier boundary", in EVERY
                      // view, and nothing less. A tier is what this list ranks,
                      // so movement inside a tier is fine print -- the small
                      // +/- under the win rate -- not a badge.
                      //
                      // Global and CN used to badge on the delta alone, at a
                      // threshold of 0.05. That put an arrow on Skarner for
                      // five hundredths of a point and on 17 champions at once,
                      // which tells the reader a champion moved without telling
                      // them it moved anywhere. Both now cross their OWN bands:
                      // Global reads the blended win rate through globalTier,
                      // CN reads its bracket win rate through cnTier, and the
                      // before/after numbers are the same pair already shown in
                      // the tooltip, so the badge and the text cannot disagree.
                      const tierMove = mv
                        ? isGlobal
                          ? crossing(globalTier(mv.oldWr), globalTier(mv.newWr))
                          : isCN
                            ? crossing(cnTier(mv.oldWr), cnTier(mv.newWr))
                            : ((roleActive ? c.tierRoleMoved : c.tierMoved) as
                                "up" | "down" | null) ?? null
                        : null;
                      const up = tierMove === "up";
                      const changed = Boolean(tierMove);
                      // The tier pair to name in the tooltip, from whichever
                      // band set this view ranks by, so the words match the
                      // arrow rather than restating EU's crossing everywhere.
                      const bandsBefore = !mv ? null
                        : isGlobal ? globalTier(mv.oldWr)
                        : isCN ? cnTier(mv.oldWr)
                        : (roleActive ? c.prevTierRole : c.prevTier) ?? null;
                      const bandsAfter = !mv ? null
                        : isGlobal ? globalTier(mv.newWr)
                        : isCN ? cnTier(mv.newWr)
                        : roleActive ? c.tierRole : c.tier;
                      return (
                        <Link
                          key={c.slug}
                          href={`/champions/${c.slug}`}
                          className="group flex w-[46px] flex-col items-center text-center transition sm:w-[68px]"
                          title={changed && mv
                            ? `${c.name} · ${shownWr(c).toFixed(1)}% WR · ${isGlobal ? "CN update impact on Global" : isCN ? "previous CN scrape" : `since ${site.movementSince ?? "the previous collection"}`}${bandsBefore && bandsAfter ? ` ${tierLabel(bandsBefore)} → ${tierLabel(bandsAfter)},` : ""} ${mv.oldWr}% → ${mv.newWr}% (${mv.delta > 0 ? "+" : ""}${mv.delta})`
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
                          {/* EVERY champion with a measurement shows it.
                              There used to be a |delta| >= 0.5 threshold, on
                              the reasoning that smaller movement is noise. It
                              is not noise once the delta is measured in the
                              units on the page -- and the threshold hid 27
                              champions, including every one that moved a
                              tenth. Under a role filter it hid them even when
                              they had crossed a band, because the tier-change
                              escape hatch reads the ROLE crossing there.

                              Width was the other reason: the tile is 46px on
                              mobile and win rate plus delta measured 54-64px,
                              so it spilled into the next champion. Stacking
                              the delta on its own line costs height, which
                              this layout has, instead of width, which it does
                              not -- so mobile keeps the number now too. */}
                          <span className="w-full truncate text-[0.7rem] font-semibold text-accent">
                            {shownWr(c).toFixed(1)}%
                            {mv && (
                              <span className={`ml-1 hidden sm:inline ${deltaClass(mv.delta)}`}>
                                {deltaText(mv.delta)}
                              </span>
                            )}
                          </span>
                          {mv && (
                            <span className={`w-full truncate text-[0.6rem] font-semibold leading-tight sm:hidden ${deltaClass(mv.delta)}`}>
                              {deltaText(mv.delta)}
                            </span>
                          )}
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
            {/* What the two movement marks mean, and why they can disagree.
                A reader seeing a green arrow above a red -0.4 has found a real
                thing, not a bug: role tiers are PERCENTILE ranks, so a champion
                can lose win rate and still rise a band because the rest of its
                role lost more. Saying so here is cheaper than being asked. */}
            <p className="mt-3 border-t border-line pt-3">
              <span className="font-medium text-text">The marks on each champion</span>: the{" "}
              <span className="font-semibold text-emerald-400">&#9650;</span>/
              <span className="font-semibold text-bad">&#9660;</span> badge means the champion{" "}
              <span className="font-medium text-text">changed tier</span> since{" "}
              {isCN ? "the previous China scrape"
                : isGlobal ? "the previous collection"
                : site.movementSince ?? "the previous collection"}
              {role === "All roles" ? "" : ` (within ${role})`}. The small{" "}
              <span className="font-semibold text-emerald-400">+</span>/
              <span className="font-semibold text-bad">&minus;</span> after the win rate is how much
              that win rate moved. They answer different questions, so they can disagree: a champion
              can lose win rate and still gain a tier when the rest of its role lost more, and it can
              gain win rate without moving band at all. Hover a champion for the exact before and
              after.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
