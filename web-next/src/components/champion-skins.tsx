"use client";

import { useEffect, useState } from "react";
import type { ChampionSkin } from "@/lib/skins";

/**
 * The champion page's Skins tab: every Wild Rift skin from the official site,
 * with a community vote. Each player has one vote per champion and can move
 * it (api/skin-votes), so the bars are a share of real preferences.
 */
type VoteState = { counts: Record<string, number>; mine: string | null };

/** Riot's CMS resizes on request; 640px WebP keeps a card under ~40 KB. */
const sized = (url: string, width: number) => `${url}${url.includes("?") ? "&" : "?"}w=${width}&fm=webp`;

export function ChampionSkins({ champion, slug, skins }: { champion: string; slug: string; skins: ChampionSkin[] }) {
  const [votes, setVotes] = useState<VoteState | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetch(`/api/skin-votes?champion=${encodeURIComponent(slug)}`, { cache: "no-store" })
      .then((response) => (response.ok ? response.json() : null))
      .then((data: VoteState | null) => { if (!cancelled && data) setVotes(data); })
      .catch(() => { /* the gallery works without the vote counts */ });
    return () => { cancelled = true; };
  }, [slug]);

  async function vote(key: string) {
    setBusy(key);
    setError("");
    try {
      const response = await fetch("/api/skin-votes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ champion: slug, skin: key }),
      });
      const data = (await response.json()) as VoteState & { error?: string };
      if (!response.ok) throw new Error(data.error || "The vote did not go through.");
      setVotes(data);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The vote did not go through.");
    } finally {
      setBusy(null);
    }
  }

  if (!skins.length) {
    return <p className="glass rounded-2xl p-6 text-sm text-muted">No skins are listed for {champion} on the official site yet.</p>;
  }

  const total = votes ? Object.values(votes.counts).reduce((sum, count) => sum + count, 0) : 0;
  const leader = votes && total > 0
    ? Object.entries(votes.counts).sort((a, b) => b[1] - a[1])[0]?.[0] ?? null
    : null;

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">{champion} skins</h2>
          <p className="mt-1 max-w-2xl text-sm text-muted">
            {`All ${skins.length} ${champion} skins in Wild Rift, from the official site. Vote for your favourite: one vote per player, and you can change it any time.`}
          </p>
        </div>
        <p className="text-xs text-faint">{votes ? `${total.toLocaleString("en-US")} ${total === 1 ? "vote" : "votes"} so far` : "Loading votes..."}</p>
      </div>
      {error && <p className="mt-3 rounded-lg border border-bad/25 bg-bad/10 px-3 py-2 text-sm text-bad">{error}</p>}

      <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {skins.map((skin) => {
          const count = votes?.counts[skin.key] ?? 0;
          const share = total ? Math.round((count / total) * 100) : 0;
          const mine = votes?.mine === skin.key;
          return (
            <article key={skin.key} className={`overflow-hidden rounded-2xl border bg-black/20 ${mine ? "border-accent/50" : "border-white/[0.08]"}`}>
              <div className="relative aspect-video bg-black/40">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={sized(skin.image, 640)} alt={skin.name} loading="lazy" className="h-full w-full object-cover object-top" />
                {leader === skin.key && (
                  <span className="absolute left-2 top-2 rounded-md bg-gold/90 px-2 py-0.5 text-[0.62rem] font-bold uppercase tracking-wide text-black">
                    Community favourite
                  </span>
                )}
              </div>
              <div className="p-3">
                <p className="truncate text-sm font-semibold text-text" title={skin.name}>{skin.name}</p>
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
                  <div className="h-full rounded-full bg-accent/70 transition-all" style={{ width: `${share}%` }} />
                </div>
                <div className="mt-2 flex items-center justify-between gap-2">
                  <span className="text-xs tabular-nums text-faint">
                    {votes ? `${share}% · ${count.toLocaleString("en-US")} ${count === 1 ? "vote" : "votes"}` : " "}
                  </span>
                  <button type="button" onClick={() => void vote(skin.key)} disabled={busy !== null || !votes}
                    aria-pressed={mine}
                    title={mine ? "Your pick. Click again to take your vote back." : `Vote for ${skin.name}`}
                    className={`rounded-full px-3 py-1 text-xs font-semibold transition disabled:opacity-50 ${mine ? "bg-accent text-black" : "border border-white/[0.12] text-muted hover:border-accent/40 hover:text-text"}`}>
                    {busy === skin.key ? "..." : mine ? "Your pick" : "Vote"}
                  </button>
                </div>
              </div>
            </article>
          );
        })}
      </div>
      <p className="mt-4 text-xs text-faint">
        Skin names and art from wildrift.leagueoflegends.com. Wild Rift and its skins belong to Riot Games.
      </p>
    </div>
  );
}
