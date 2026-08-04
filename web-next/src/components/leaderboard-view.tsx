"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { TierChip } from "@/components/ui";
import { ChampionCombobox } from "@/components/champion-combobox";
import { BestPlayerBuild } from "@/components/best-player-build";
import { Glyph, GLYPHS, Laurel } from "@/components/insignia";
import { TierBadge, tierParts } from "@/components/tier-badge";
import { QueuePanel } from "@/components/queue-panel";
import type { QueueStats } from "@/lib/player-index";
import { RegionToggle, RegionComingSoon, type Region } from "@/components/region-toggle";

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

type EnrichedPlayer = Row & {
  tag: string | null;
  tier: string | null;
  level: number | null;
  /** Boosting advert: row kept, name and detail withheld. */
  hidden?: boolean | null;
  build: {
    items: { slug: string | null; name: string }[];
    runes: string[];
    spells: string[];
  } | null;
  stats: { ranked?: QueueStats; legendary?: QueueStats } | null;
};

type EnrichedPayload = { champion: string; slug: string; capturedAt: string; players: EnrichedPlayer[] };

type SortKey = "r" | "w" | "g" | "s";

const num = (v: number | null | undefined) => (v == null ? -Infinity : v);

/* The enriched row for the champion's best player, or null.
 *
 * Rank alone is NOT enough to join these two sources. `bestPlayer` comes from
 * site.json (built from winrates.csv) while the enriched rows come from the
 * per-champion capture export, and the two are refreshed independently -- so
 * during a collection they routinely describe different ladders. Joining on
 * rank put "247 games" beside a name belonging to somebody else entirely.
 *
 * The name has to agree too. When it does not, the spotlight simply shows
 * less, which is the correct amount to show about a player we cannot identify.
 */
function matchBestPlayer(
  champ: SlimChampion,
  enriched: EnrichedPayload | null,
): EnrichedPlayer | null {
  const bp = champ.bestPlayer;
  if (!bp || bp.rank == null || !enriched) return null;
  const row = enriched.players.find((p) => p.r === bp.rank);
  if (!row || row.hidden) return null;
  const norm = (s: string | null | undefined) =>
    (s ?? "").toLowerCase().replace(/\s+/g, "");
  return norm(row.p) && norm(row.p) === norm(bp.player) ? row : null;
}

/* The champion header, and the crowning of its best player.
 *
 * The old version put the champion and the player side by side in the same
 * visual weight, both on top of a triple-stacked scrim that turned the splash
 * to mud. Nothing looked like the subject. This gives the two jobs different
 * treatments: the champion identifies the page, quietly; the best player is
 * the thing being celebrated, so it gets the gold, the crown, the laurels and
 * the only large number on the card.
 *
 * The splash is cropped to 25% from the top because champion art puts the
 * character's head in the upper third, and bg-center reliably decapitated
 * them.
 */
function ChampionSpotlight({
  champ,
  best,
}: {
  champ: SlimChampion;
  best: EnrichedPlayer | null;
}) {
  const bp = champ.bestPlayer;
  return (
    <div className="relative mb-6 overflow-hidden rounded-2xl border border-line">
      <div
        className="absolute inset-0 bg-cover"
        style={{ backgroundImage: `url(${champ.splash})`, backgroundPosition: "center 25%" }}
      />
      {/* One horizontal scrim, not three: text sits on solid ground at the
          left while the art stays legible on the right. */}
      <div className="absolute inset-0 bg-gradient-to-r from-bg via-bg/92 to-bg/25" />
      <div className="absolute inset-0 bg-gradient-to-t from-bg via-transparent to-transparent" />
      {/* A warm glow under the spotlight panel, so the celebration reads
          before any of the words do. */}
      {bp && (
        <div
          aria-hidden
          className="pointer-events-none absolute -right-16 top-1/2 hidden h-72 w-72 -translate-y-1/2 rounded-full sm:block"
          style={{ background: "radial-gradient(circle, rgb(234 179 8 / 0.16), transparent 68%)" }}
        />
      )}

      <div className="relative flex flex-col gap-6 p-6 sm:flex-row sm:items-center sm:justify-between sm:gap-8">
        <div className="min-w-0">
          <Link
            href={`/champions/${champ.slug}`}
            className="group inline-flex items-center gap-3.5 transition hover:opacity-95"
          >
            <span
              className={`h-16 w-16 shrink-0 overflow-hidden rounded-full ${
                champ.isHard ? "ring-2 ring-bad/70" : "ring-1 ring-white/20"
              }`}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={champ.icon}
                alt=""
                width={64}
                height={64}
                className="h-full w-full scale-[1.12] object-cover"
              />
            </span>
            <span className="min-w-0">
              <span className="block truncate text-2xl font-semibold leading-tight tracking-tight">
                {champ.name}
              </span>
              <span className="block text-xs uppercase tracking-[0.16em] text-muted">
                {champ.role} · {champ.class}
              </span>
            </span>
          </Link>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <TierChip tier={champ.tier} />
            <span className="rounded-md border border-line bg-white/[0.04] px-2 py-0.5 text-sm font-semibold tabular-nums text-accent">
              {champ.wr.toFixed(1)}% win rate
            </span>
          </div>
        </div>

        {bp && (
          <div className="relative w-full shrink-0 overflow-hidden rounded-xl border border-gold/35 bg-black/35 px-5 py-4 backdrop-blur-sm sm:w-auto sm:min-w-[17rem]">
            <div className="flex items-center gap-2 text-gold">
              <Glyph d={GLYPHS.crown} className="text-gold" size={18} />
              <span className="text-[0.65rem] font-bold uppercase tracking-[0.2em]">
                Best {champ.name}
              </span>
            </div>
            <div className="mt-2 flex items-center gap-2.5">
              <Laurel size={26} />
              <p className="min-w-0 flex-1 truncate text-2xl font-semibold leading-tight text-gold">
                {bp.player}
              </p>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-gold/20 pt-3 text-xs text-muted">
              {bp.rank != null && (
                <span className="font-semibold text-text">#{bp.rank} on the board</span>
              )}
              {bp.confidence_wr != null && (
                <span className="tabular-nums">{bp.confidence_wr.toFixed(1)}% adjusted</span>
              )}
              {best?.g != null && <span className="tabular-nums">{best.g} games</span>}
              {best?.tier && <TierBadge tier={best.tier} size={18} />}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* One ladder's worth of "emblem xN". The Ranked and Legendary Ranked queues
   each get their own, because they are separate ladders: a Legendary Master
   listed between Master and Grandmaster reads as one continuous ranking, and
   it is not one. */
function TierSpread({ label, rows }: { label: string; rows: [string, number][] }) {
  return (
    <div>
      <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted">{label}</p>
      <div className="mt-1.5 flex items-center gap-2">
        {rows.map(([family, n]) => (
          <span key={family} className="inline-flex items-center gap-0.5 text-xs text-muted">
            <TierBadge tier={family} size={22} />
            ×{n}
          </span>
        ))}
      </div>
    </div>
  );
}

/* Runes and summoner spells render as art, like items: a rune page reads as
   a row of icons far faster than five names separated by dots.

   A name with no art is a name the build extractor invented -- the vision
   model substitutes League PC rune names when it cannot read an icon, and
   17 such names were confirmed as runes that do not exist in the game. Those
   are dropped rather than rendered, so the page never shows a rune nobody
   can equip. data/rune_extraction_report.txt tracks them for the rework. */
function ArtIcon({ src, name, size }: { src?: string; name: string; size: number }) {
  if (!src) return null;
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt={name}
      title={name}
      width={size}
      height={size}
      loading="lazy"
      className="shrink-0 rounded-md bg-black/30 object-contain ring-1 ring-white/10"
      style={{ width: size, height: size }}
    />
  );
}

function ItemIcon({ slug, name, icons, size = 26, className = "" }: {
  slug: string | null; name: string; icons: Record<string, string>; size?: number;
  className?: string;
}) {
  const src = slug ? icons[slug] : undefined;
  if (!src) {
    return (
      <span
        title={name}
        className={`grid shrink-0 place-items-center rounded-md border border-line bg-white/5 text-[0.55rem] text-faint ${className}`}
        style={{ width: size, height: size }}
      >
        ?
      </span>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt={name}
      title={name}
      width={size}
      height={size}
      loading="lazy"
      className={`shrink-0 rounded-md border border-line/70 bg-black/30 object-cover ${className}`}
      style={{ width: size, height: size }}
    />
  );
}

/* What the whole top 50 agrees on: item pick rates, tier spread, averages. */
function ChampionPulse({ payload, icons, runeIcons, spellIcons }: {
  payload: EnrichedPayload; icons: Record<string, string>;
  runeIcons: Record<string, string>; spellIcons: Record<string, string>;
}) {
  const pulse = useMemo(() => {
    const players = payload.players;
    const withBuild = players.filter((p) => p.build?.items?.length);
    const freq = new Map<string, { name: string; slug: string; n: number }>();
    for (const p of withBuild) {
      for (const it of p.build!.items) {
        if (!it.slug) continue;
        const cur = freq.get(it.slug) ?? { name: it.name, slug: it.slug, n: 0 };
        cur.n += 1;
        freq.set(it.slug, cur);
      }
    }
    const topItems = [...freq.values()].sort((a, b) => b.n - a.n).slice(0, 6);

    const tiers = new Map<string, number>();
    for (const p of players) {
      if (!p.tier) continue;
      // Group by the SAME family the badge draws. Taking the first word
      // collapsed the whole Legendary Ranked ladder -- Master, Grandmaster,
      // Challenger and Commander -- into one bucket called "Legendary",
      // which is four different tiers counted as one and drawn with no
      // emblem, since "legendary" alone owns no art.
      const { family } = tierParts(p.tier);
      tiers.set(family, (tiers.get(family) ?? 0) + 1);
    }
    // Two ladders, two rows. Legendary Ranked is a separate queue with its
    // own tiers, so a Legendary Master sitting between Master and Grandmaster
    // reads as if it were part of one ordered ladder, which it is not. Each
    // player holds exactly one tier, so the split partitions them cleanly.
    const byCount = (a: [string, number], b: [string, number]) => b[1] - a[1];
    const entries = [...tiers.entries()];
    const tierSpread = entries.filter(([f]) => !f.startsWith("legendary")).sort(byCount);
    const legendarySpread = entries.filter(([f]) => f.startsWith("legendary")).sort(byCount);

    const kdas = players.map((p) => p.stats?.ranked?.kda).filter((v): v is number => v != null);
    const avgKda = kdas.length ? kdas.reduce((a, b) => a + b, 0) / kdas.length : null;

    const keystones = new Map<string, number>();
    const spellPairs = new Map<string, number>();
    const cores = new Map<string, number>();
    for (const p of withBuild) {
      const ks = p.build!.runes?.[0];
      if (ks) keystones.set(ks, (keystones.get(ks) ?? 0) + 1);
      const spells = p.build!.spells;
      if (spells?.length) {
        const pair = [...spells].sort().join(" + ");
        spellPairs.set(pair, (spellPairs.get(pair) ?? 0) + 1);
      }
      const core = p.build!.items.map((i) => i.slug).filter(Boolean).sort().join("|");
      if (core.split("|").length >= 5) cores.set(core, (cores.get(core) ?? 0) + 1);
    }
    const topKeystone = [...keystones.entries()].sort((a, b) => b[1] - a[1])[0];
    const topSpells = [...spellPairs.entries()].sort((a, b) => b[1] - a[1])[0];
    const conformity = Math.max(0, ...cores.values());

    // Legendary tax: how much win rate the same players give up in the
    // sweatier queue (players with 10+ legendary games).
    const rankedWr = players.map((p) => p.stats?.ranked?.wr).filter((v): v is number => v != null);
    const legendWr = players
      .filter((p) => (p.stats?.legendary?.games ?? 0) >= 10)
      .map((p) => p.stats!.legendary!.wr)
      .filter((v): v is number => v != null);
    const mean = (a: number[]) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : null);
    const mRanked = mean(rankedWr);
    const mLegend = mean(legendWr);
    const legendaryTax = mRanked != null && mLegend != null ? mLegend - mRanked : null;

    const fbRates = players
      .map((p) => p.stats?.ranked)
      .filter((r): r is QueueStats => r != null && (r.games ?? 0) > 0 && r.firstBlood != null)
      .map((r) => (r.firstBlood! / r.games!) * 100);
    const firstBlood = mean(fbRates);
    const pentas = players.reduce((acc, p) => acc + (p.stats?.ranked?.penta ?? 0), 0);

    return { topItems, tierSpread, legendarySpread, avgKda, topKeystone, topSpells, conformity,
             legendaryTax, firstBlood, pentas, nBuilds: withBuild.length };
  }, [payload]);

  if (!pulse.nBuilds) return null;
  return (
    <div className="glass mb-4 flex flex-wrap items-center gap-x-5 gap-y-3 rounded-2xl px-4 py-3.5 sm:gap-x-8 sm:px-5 sm:py-4">
      <div>
        <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted">
          Core items across the top 50
        </p>
        <div className="mt-1.5 flex items-center gap-1.5">
          {pulse.topItems.map((it) => (
            <span key={it.slug} className="flex flex-col items-center gap-0.5">
              <ItemIcon slug={it.slug} name={it.name} icons={icons} size={30} />
              <span className="text-[0.6rem] tabular-nums text-faint">
                {Math.round((it.n / pulse.nBuilds) * 100)}%
              </span>
            </span>
          ))}
        </div>
      </div>
      {pulse.tierSpread.length > 0 && (
        <TierSpread label="Ranked tiers" rows={pulse.tierSpread} />
      )}
      {pulse.legendarySpread.length > 0 && (
        <TierSpread label="Legendary Ranked" rows={pulse.legendarySpread} />
      )}
      {pulse.avgKda != null && (
        <div>
          <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted">Avg ranked KDA</p>
          <p className="mt-1.5 text-lg font-semibold text-accent">{pulse.avgKda.toFixed(1)}</p>
        </div>
      )}
      {pulse.topKeystone && (
        <div>
          <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted">Top keystone</p>
          <p className="mt-1.5 flex items-center gap-1.5 text-sm font-medium">
            <ArtIcon src={runeIcons[pulse.topKeystone[0]]} name={pulse.topKeystone[0]} size={22} />
            {pulse.topKeystone[0]}
            <span className="text-xs text-faint">
              {Math.round((pulse.topKeystone[1] / pulse.nBuilds) * 100)}%
            </span>
          </p>
        </div>
      )}
      {pulse.topSpells && (
        <div>
          <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted">Spells</p>
          <p className="mt-1.5 flex items-center gap-1.5 text-sm font-medium">
            {pulse.topSpells[0].split(" + ").map((sp) => (
              <ArtIcon key={sp} src={spellIcons[sp]} name={sp} size={22} />
            ))}
            <span className="text-xs text-faint">
              {Math.round((pulse.topSpells[1] / pulse.nBuilds) * 100)}%
            </span>
          </p>
        </div>
      )}
      {pulse.conformity >= 2 && (
        <div title="Players running the exact same item core">
          <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted">Same core</p>
          <p className="mt-1.5 text-sm font-medium tabular-nums">
            {pulse.conformity}<span className="text-xs text-faint">/{pulse.nBuilds}</span>
          </p>
        </div>
      )}
      {pulse.legendaryTax != null && (
        <div title="Win rate change for these players in Legendary Ranked">
          <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted">Legendary tax</p>
          <p className={`mt-1.5 text-sm font-semibold tabular-nums ${pulse.legendaryTax >= 0 ? "text-accent" : "text-bad"}`}>
            {pulse.legendaryTax >= 0 ? "+" : ""}{pulse.legendaryTax.toFixed(1)}pp
          </p>
        </div>
      )}
      {pulse.firstBlood != null && (
        <div title="Share of ranked games with first blood">
          <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted">First blood</p>
          <p className="mt-1.5 text-sm font-medium tabular-nums">{pulse.firstBlood.toFixed(1)}%</p>
        </div>
      )}
      {pulse.pentas > 0 && (
        <div title="Pentakills across the top 50, ranked queue">
          <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted">Pentakills</p>
          <p className="mt-1.5 text-sm font-semibold text-gold tabular-nums">{pulse.pentas}</p>
        </div>
      )}
    </div>
  );
}

function ExpandedRow({ p, icons, runeIcons, spellIcons }: {
  p: EnrichedPlayer;
  icons: Record<string, string>;
  runeIcons: Record<string, string>;
  spellIcons: Record<string, string>;
}) {
  const runes = (p.build?.runes ?? []).filter((r) => runeIcons[r]);
  const spells = (p.build?.spells ?? []).filter((s) => spellIcons[s]);
  return (
    <td colSpan={7} className="px-4 pb-4 pt-1">
      <div className="flex flex-col gap-3">
        {p.build && (
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
            <div className="flex items-center gap-1.5">
              {p.build.items.map((it, i) => (
                <ItemIcon key={`${it.slug}-${i}`} slug={it.slug} name={it.name} icons={icons} size={32} />
              ))}
            </div>
            {runes.length > 0 && (
              <span className="flex items-center gap-1.5" title={runes.join(" · ")}>
                {runes.map((r, i) => (
                  /* keystone first and larger: it is the page's identity */
                  <ArtIcon key={`${r}-${i}`} src={runeIcons[r]} name={r} size={i === 0 ? 30 : 24} />
                ))}
              </span>
            )}
            {spells.length > 0 && (
              <span className="flex items-center gap-1.5" title={spells.join(" + ")}>
                {spells.map((s, i) => (
                  <ArtIcon key={`${s}-${i}`} src={spellIcons[s]} name={s} size={24} />
                ))}
              </span>
            )}
          </div>
        )}
        <div className="grid gap-3 lg:grid-cols-2">
          {p.stats?.ranked && <QueuePanel title="Ranked" s={p.stats.ranked} />}
          {p.stats?.legendary && <QueuePanel title="Legendary Ranked" s={p.stats.legendary} />}
        </div>
        {!p.build && !p.stats && (
          <p className="text-sm text-faint">No detail captured for this player.</p>
        )}
      </div>
    </td>
  );
}

export function LeaderboardView({ champions, itemIcons, runeIcons, spellIcons }: {
  champions: SlimChampion[];
  itemIcons: Record<string, string>;
  runeIcons: Record<string, string>;
  spellIcons: Record<string, string>;
}) {
  const byName = useMemo(
    () => [...champions].sort((a, b) => a.name.localeCompare(b.name)),
    [champions]
  );
  const [slug, setSlug] = useState(champions[0]?.slug ?? "");
  const [data, setData] = useState<Record<string, Row[]> | null>(null);
  const [enriched, setEnriched] = useState<EnrichedPayload | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("r");
  const [dir, setDir] = useState<"asc" | "desc">("asc");
  const [region, setRegion] = useState<Region>("EU");
  // one champion's enriched file is ~50 KB; keep what was already fetched
  const enrichedCache = useRef<Map<string, EnrichedPayload | null>>(new Map());

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

  // The per-champion enriched file exists only once that champion has been
  // recaptured with the extended pipeline; 404 simply means the thin table.
  useEffect(() => {
    setExpanded(null);
    const cached = enrichedCache.current.get(slug);
    if (cached !== undefined) {
      setEnriched(cached);
      return;
    }
    let cancelled = false;
    setEnriched(null);
    fetch(`/players/${slug}.json`)
      .then((r) => (r.ok ? r.json() : null))
      .then((payload: EnrichedPayload | null) => {
        enrichedCache.current.set(slug, payload);
        if (!cancelled) setEnriched(payload);
      })
      .catch(() => {
        enrichedCache.current.set(slug, null);
        if (!cancelled) setEnriched(null);
      });
    return () => {
      cancelled = true;
    };
  }, [slug]);

  const champ = champions.find((c) => c.slug === slug);
  const rows: (Row | EnrichedPlayer)[] = useMemo(() => {
    const base: (Row | EnrichedPlayer)[] = enriched?.players ?? data?.[slug] ?? [];
    return [...base].sort((a, b) => {
      const cmp = num(a[sortKey]) - num(b[sortKey]);
      return dir === "asc" ? cmp : -cmp;
    });
  }, [data, enriched, slug, sortKey, dir]);
  const hasDetail = enriched != null && enriched.players.length > 0;

  const toggleSort = (key: SortKey) => {
    if (key === sortKey) setDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setDir(key === "r" ? "asc" : "desc");
    }
  };

  return (
    <div>
      {/* Region: CN has no per-player leaderboard data, so only EU / NA here */}
      <div className="mb-5">
        <RegionToggle region={region} onChange={setRegion} regions={["EU", "NA"] as const} />
      </div>

      {region !== "EU" ? (
        <RegionComingSoon region={region} />
      ) : (
      <>
      {/* Champion search */}
      <div className="mb-5 sm:max-w-sm">
        <ChampionCombobox
          champions={byName.map((c) => ({ name: c.name, slug: c.slug, icon: c.icon }))}
          placeholder="Search a champion…"
          onSelect={(s) => setSlug(s)}
        />
      </div>

      {champ && (
        <ChampionSpotlight champ={champ} best={matchBestPlayer(champ, enriched)} />
      )}

      {/* The hand-recorded build for this champion's best player, when one has
          been entered in the admin console. Silent when it has not. */}
      <BestPlayerBuild slug={slug} championName={champ?.name} />

      {/* What the whole top 50 agrees on, from the freshly captured data */}
      {hasDetail && <ChampionPulse payload={enriched} icons={itemIcons} runeIcons={runeIcons} spellIcons={spellIcons} />}

      {/* Player table */}
      {data === null && !hasDetail ? (
        <div className="glass rounded-2xl p-10 text-center text-muted">Loading players…</div>
      ) : rows.length === 0 ? (
        <div className="glass rounded-2xl p-10 text-center text-muted">
          No player data for this champion yet.
        </div>
      ) : (
        <div className="glass overflow-x-auto rounded-2xl">
          {/* On a phone the enriched table drops Games and Mastery (still
              sortable from sm up) rather than forcing a sideways scroll:
              rank, player, build and win rate are the columns people came
              for, and they fit a 360px screen with room for the chevron. */}
          <table className="w-full border-collapse text-sm sm:min-w-[560px]">
            <thead>
              <tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
                <Th onClick={() => toggleSort("r")} active={sortKey === "r"} dir={dir} className="w-10 text-center sm:w-16">
                  <span className="hidden sm:inline">Rank</span>
                  <span className="sm:hidden">#</span>
                </Th>
                <Th>Player</Th>
                {hasDetail && <Th>Build</Th>}
                <Th onClick={() => toggleSort("w")} active={sortKey === "w"} dir={dir} right>
                  <span className="hidden sm:inline">Win rate</span>
                  <span className="sm:hidden">WR</span>
                </Th>
                <Th onClick={() => toggleSort("g")} active={sortKey === "g"} dir={dir} right className="hidden sm:table-cell">
                  Games
                </Th>
                <Th onClick={() => toggleSort("s")} active={sortKey === "s"} dir={dir} right className="hidden md:table-cell">
                  Mastery
                </Th>
                {hasDetail && <Th className="w-6 sm:w-10"> </Th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => {
                const e = hasDetail ? (row as EnrichedPlayer) : null;
                const open = e != null && expanded === row.r;
                const clickable = e != null && (e.build != null || e.stats != null);
                return (
                  <FragmentRow key={`${row.r}-${i}`}>
                    <tr
                      onClick={clickable ? () => setExpanded(open ? null : row.r) : undefined}
                      className={`border-b border-line/60 transition last:border-0 hover:bg-white/[0.03] ${clickable ? "cursor-pointer" : ""} ${open ? "bg-white/[0.03]" : ""}`}
                    >
                      <td className="px-1.5 py-2.5 text-center sm:px-3">
                        <span className={row.r <= 3 ? "font-bold text-accent" : "text-faint"}>
                          {row.r}
                        </span>
                      </td>
                      <td className="max-w-[98px] px-1.5 py-2.5 sm:max-w-[240px] sm:px-3">
                        <span
                          className={`block truncate font-medium ${e?.hidden ? "italic text-faint" : ""}`}
                          title={e?.hidden
                            ? "This account advertises a boosting service. Its name is hidden and its games are excluded from champion win rates and records."
                            : undefined}
                        >
                          {row.p}
                        </span>
                        {e?.tier && (
                          <span className="mt-0.5 flex items-center">
                            <TierBadge tier={e.tier} />
                          </span>
                        )}
                      </td>
                      {hasDetail && (
                        <td className="px-1.5 py-2.5 sm:px-3">
                          {e?.build ? (
                            <span className="flex items-center gap-0.5 sm:gap-1">
                              {e.build.items.slice(0, 6).map((it, j) => (
                                <ItemIcon
                                  key={`${it.slug}-${j}`}
                                  slug={it.slug}
                                  name={it.name}
                                  icons={itemIcons}
                                  size={22}
                                  className={j >= 4 ? "hidden sm:block" : ""}
                                />
                              ))}
                            </span>
                          ) : (
                            <span className="text-xs text-faint">-</span>
                          )}
                        </td>
                      )}
                      <td className="px-2 py-2.5 text-right font-semibold text-accent sm:px-3">
                        {row.w != null ? `${row.w.toFixed(1)}%` : "-"}
                      </td>
                      <td className="hidden px-3 py-2.5 text-right text-muted sm:table-cell">
                        {row.g != null ? row.g.toLocaleString() : "-"}
                      </td>
                      <td className="hidden px-3 py-2.5 text-right text-muted md:table-cell">
                        {row.s != null ? row.s.toLocaleString() : "-"}
                      </td>
                      {hasDetail && (
                        <td className="px-2 py-2.5 text-center text-faint">
                          {clickable ? (open ? "▾" : "▸") : ""}
                        </td>
                      )}
                    </tr>
                    {open && e && (
                      <tr className="border-b border-line/60 last:border-0">
                        <ExpandedRow p={e} icons={itemIcons} runeIcons={runeIcons} spellIcons={spellIcons} />
                      </tr>
                    )}
                  </FragmentRow>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {hasDetail && (
        <p className="mt-2 text-xs text-faint">
          Click a player row for their full build, runes and per-queue stats. Captured {enriched.capturedAt}.
        </p>
      )}
      </>
      )}
    </div>
  );
}

/* React fragments cannot carry keys through .map inside <tbody> without a
   wrapper; this keeps the expanded row adjacent to its player row. */
function FragmentRow({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
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
