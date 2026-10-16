"use client";

import { useEffect, useState } from "react";

/**
 * China's recommended loadout (the champion page's "Recommended" row) inside
 * the Build Studio: a reference card beside a generated build, and the seed
 * for the Lab's "Start from China's recommended build".
 *
 * It is a reference, deliberately NOT an input to the generator: the build
 * model is never told what is popular, and this is popularity-weighted.
 */
type Entity = { name: string; icon: string; slug?: string };
type Pick = { winRate: number; pickRate: number; entities: Entity[] } | null;
export type ChinaLane = { lane: string; capturedAt: string; core: Pick; runes: Pick; boots: Pick };

const ROLE_LANE: Record<string, string> = { Baron: "baron", Jungle: "jungle", Mid: "mid", Dragon: "dragon", Support: "support" };

/** The recommended China loadout for a champion, for the lane that matches
 *  the role when there is one. Null until loaded or when China has none. */
export function useChinaRecommended(slug: string | null | undefined, role?: string): ChinaLane | null {
  const [lanes, setLanes] = useState<{ slug: string; lanes: ChinaLane[] } | null>(null);
  useEffect(() => {
    if (!slug) return;
    let cancelled = false;
    fetch(`/api/cn-recommended?champion=${encodeURIComponent(slug)}`)
      .then((response) => (response.ok ? response.json() : { lanes: [] }))
      .then((data: { lanes?: ChinaLane[] }) => { if (!cancelled) setLanes({ slug, lanes: data.lanes ?? [] }); })
      .catch(() => { if (!cancelled) setLanes({ slug, lanes: [] }); });
    return () => { cancelled = true; };
  }, [slug]);
  if (!slug || lanes?.slug !== slug || !lanes.lanes.length) return null;
  const want = role ? ROLE_LANE[role] : undefined;
  return lanes.lanes.find((lane) => lane.lane === want) ?? lanes.lanes[0];
}

/** Item slugs and rune names, the flat shape the Lab's seed helper takes. */
export function chinaSeed(lane: ChinaLane): { items: string[]; runes: string[] } {
  const items = [...(lane.core?.entities ?? []), ...(lane.boots?.entities ?? [])]
    .map((entity) => entity.slug).filter((slug): slug is string => Boolean(slug));
  const runes = (lane.runes?.entities ?? []).map((entity) => entity.name);
  return { items, runes };
}

const LANE_LABEL: Record<string, string> = { baron: "Baron lane", jungle: "Jungle", mid: "Mid lane", dragon: "Dragon lane", support: "Support" };

function Icons({ entities, round = false }: { entities: Entity[]; round?: boolean }) {
  return (
    <span className="flex -space-x-1">
      {entities.map((entity, index) => (
        // eslint-disable-next-line @next/next/no-img-element
        <img key={`${entity.name}-${index}`} src={entity.icon} alt={entity.name} title={entity.name} width={28} height={28}
          className={`h-7 w-7 border border-black/40 bg-black/30 ${round ? "rounded-full" : "rounded-md"}`} />
      ))}
    </span>
  );
}

/** The reference card shown beside a generated build. */
export function ChinaRecommendedCard({ lane, champion }: { lane: ChinaLane; champion: string }) {
  const row = (label: string, pick: Pick, round = false) => pick && (
    <div className="flex items-center gap-3">
      <span className="w-16 shrink-0 text-[0.62rem] font-semibold uppercase tracking-wide text-faint">{label}</span>
      <Icons entities={pick.entities} round={round} />
      <span className="min-w-0 flex-1 truncate text-xs text-muted" title={pick.entities.map((entity) => entity.name).join(" · ")}>
        {pick.entities.map((entity) => entity.name).join(" · ")}
      </span>
      <span className="shrink-0 text-xs font-semibold tabular-nums text-text">
        {pick.winRate.toFixed(1)}%<span className="font-normal text-faint"> · {pick.pickRate.toFixed(1)}% of games</span>
      </span>
    </div>
  );
  return (
    <div className="rounded-2xl border border-gold/25 bg-gold/[0.05] p-4">
      <p className="text-[0.65rem] font-bold uppercase tracking-wide text-gold">
        What China&rsquo;s Legendary players run · {LANE_LABEL[lane.lane] ?? lane.lane}
      </p>
      <p className="mt-1 text-xs leading-relaxed text-faint">
        {`The best balance of win rate and pick rate among every ${champion} game in China's Legendary queue. A reference to compare with, not part of how the build above was chosen.`}
      </p>
      <div className="mt-3 space-y-2">
        {row("Core", lane.core)}
        {row("Runes", lane.runes, true)}
        {row("Boots", lane.boots)}
      </div>
    </div>
  );
}
