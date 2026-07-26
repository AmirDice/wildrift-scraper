"use client";

import { useEffect, useState } from "react";
import engineData from "@/data/engine.json";

/* eslint-disable @next/next/no-img-element */

const ITEMS = (engineData as unknown as {
  items: Record<string, { name?: string; icon?: string }>;
}).items;

const itemName = (slug: string) => ITEMS?.[slug]?.name ?? slug;
const itemIcon = (slug: string) => ITEMS?.[slug]?.icon ?? `/items/${slug}.webp`;

interface BestBuild {
  championSlug: string;
  player: string;
  standing?: string;
  items: string[];
  boots?: string;
  runes: string[];
  note?: string;
  updatedAt: string;
}

/**
 * The hand-recorded build of the best player on a champion.
 *
 * Renders nothing at all when none has been recorded: an empty "no build yet"
 * panel on 130 champions would be worse than silence, and this is meant to feel
 * like a bonus where it exists rather than a gap where it does not.
 */
export function BestPlayerBuild({ slug, championName }: { slug: string; championName?: string }) {
  // The champion this result belongs to is stored WITH it rather than cleared
  // on every slug change: switching champions must not show the previous
  // champion's build for a frame, and a mismatch is easier to render around
  // than to race against.
  const [result, setResult] = useState<{ slug: string; build: BestBuild | null } | null>(null);

  useEffect(() => {
    if (!slug) return;
    let cancelled = false;
    void (async () => {
      try {
        const res = await fetch(`/api/best-builds?slug=${encodeURIComponent(slug)}`);
        if (!res.ok || cancelled) return;
        const data = (await res.json()) as { build: BestBuild | null };
        if (!cancelled) setResult({ slug, build: data.build });
      } catch {
        /* stay hidden */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [slug]);

  const build = result?.slug === slug ? result.build : null;
  if (!build) return null;

  const items = [...build.items, ...(build.boots ? [build.boots] : [])];

  return (
    <div className="glass mt-4 rounded-2xl p-4">
      <div className="flex flex-wrap items-baseline gap-2">
        <p className="text-[0.65rem] font-bold uppercase tracking-wide text-gold">
          What the best {championName ?? ""} player actually builds
        </p>
        <span className="text-xs text-faint">recorded by hand, not generated</span>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-text">{build.player}</span>
        {build.standing && (
          <span className="rounded-md bg-gold/15 px-2 py-0.5 text-[0.65rem] font-semibold text-gold">
            {build.standing}
          </span>
        )}
      </div>

      {items.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {items.map((itemSlug, index) => (
            <span key={`${itemSlug}-${index}`} className="relative">
              <img
                src={itemIcon(itemSlug)}
                alt={itemName(itemSlug)}
                title={itemName(itemSlug)}
                width={42}
                height={42}
                className="rounded-lg ring-1 ring-white/10"
              />
              <span className="absolute -left-1.5 -top-1.5 grid h-[18px] w-[18px] place-items-center rounded-full bg-[#0e1322] text-[0.6rem] font-bold text-gold ring-1 ring-line">
                {index + 1}
              </span>
            </span>
          ))}
        </div>
      )}

      {build.runes.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5 border-t border-line/60 pt-3">
          {build.runes.map((rune, index) => (
            <span
              key={`${rune}-${index}`}
              className={`rounded-md px-2 py-0.5 text-xs ${index === 0 ? "bg-accent/15 font-semibold text-accent" : "bg-white/[0.06] text-muted"}`}
            >
              {rune}
            </span>
          ))}
        </div>
      )}

      {build.note && <p className="mt-3 text-sm leading-relaxed text-muted">{build.note}</p>}
    </div>
  );
}
