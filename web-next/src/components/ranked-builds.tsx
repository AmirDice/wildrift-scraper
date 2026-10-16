"use client";

import { useEffect, useState } from "react";
import type { ChampionLoadoutLane } from "@/lib/cn-loadouts";
import { ChampionLoadouts } from "@/components/champion-loadouts";
import { ServerBuildsPanel } from "@/components/server-builds";

/**
 * The Build Studio's "Ranked Builds" tab: what players actually build, beside
 * the tools that suggest a build. Each server's top-player build first (it
 * used to sit under the generator), then China's Legendary loadouts: every
 * core, rune page, boots and spell pair with win and pick rates, sorted by
 * the best balance of the two.
 */
export function RankedBuilds({ champion, slug }: { champion: string; slug: string }) {
  const [loaded, setLoaded] = useState<{ slug: string; lanes: ChampionLoadoutLane[] } | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetch(`/api/cn-loadouts?champion=${encodeURIComponent(slug)}`)
      .then((response) => (response.ok ? response.json() : { lanes: [] }))
      .then((data: { lanes?: ChampionLoadoutLane[] }) => { if (!cancelled) setLoaded({ slug, lanes: data.lanes ?? [] }); })
      .catch(() => { if (!cancelled) setLoaded({ slug, lanes: [] }); });
    return () => { cancelled = true; };
  }, [slug]);
  const lanes = loaded?.slug === slug ? loaded.lanes : null;
  return (
    <div className="space-y-4">
      {/* Most built by server first: no other Wild Rift site has each
          server's top players side by side (owner's call, 2026-10-16). */}
      <div data-tour="ranked-servers">
        <ServerBuildsPanel champion={champion} />
      </div>
      <div data-tour="ranked-loadouts">
        {lanes == null ? (
          <div className="glass rounded-2xl p-6 text-sm text-muted">Loading {champion}&rsquo;s ranked builds...</div>
        ) : (
          // Keyed by champion so its lane and tab reset with the champion.
          <ChampionLoadouts key={slug} champion={champion} loadouts={lanes} />
        )}
      </div>
    </div>
  );
}
