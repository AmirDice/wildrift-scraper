"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { TierBadge } from "@/components/tier-badge";
import { Glyph, GLYPHS } from "@/components/insignia";
import { QueuePanel } from "@/components/queue-panel";
import {
  fetchAccountStats, fold, loadPlayerIndex, matchPlayers,
  type IndexPlayer, type PlayerQueues,
} from "@/lib/player-index";

/* Search a player across every champion board.
 *
 * The per-champion files answer "who is best at Vayne". This answers the
 * other direction: given a name, which boards is this person on, and how do
 * they play on each.
 *
 * TAGS ARE NEVER SHOWN. They can be typed to disambiguate two players sharing
 * a name, and the index stores only a hash of them, so neither the page nor
 * the JSON behind it hands anybody a tag they did not already know.
 */

export type ChampionRef = { slug: string; name: string; icon: string; splash: string };

export function PlayerSearch({ champions }: { champions: ChampionRef[] }) {
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState<IndexPlayer[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const [picked, setPicked] = useState<IndexPlayer | null>(null);

  const champBySlug = useMemo(() => {
    const m = new Map<string, ChampionRef>();
    for (const c of champions) m.set(c.slug, c);
    return m;
  }, [champions]);

  const load = useCallback(async () => {
    if (index) return index;
    setLoading(true);
    try {
      const players = await loadPlayerIndex();
      setIndex(players);
      setFailed(false);
      return players;
    } catch {
      setFailed(true);
      return null;
    } finally {
      setLoading(false);
    }
  }, [index]);

  // Deep link: /player?p=Name restores a result, so a profile can be shared
  // without minting a route (and a static page) for every player on the ladder.
  useEffect(() => {
    const p = new URLSearchParams(window.location.search).get("p");
    if (!p) return;
    setQuery(p);
    load().then((players) => {
      const hit = players?.find((x) => fold(x.n) === fold(p));
      if (hit) setPicked(hit);
    });
  }, [load]);

  const results = useMemo(
    () => (index ? matchPlayers(index, query) : []),
    [index, query],
  );
  const typedName = fold(query.split("#")[0] ?? "");

  const choose = (p: IndexPlayer) => {
    setPicked(p);
    const url = new URL(window.location.href);
    url.searchParams.set("p", p.n);
    window.history.replaceState(null, "", url);
  };

  return (
    <div>
      <label className="block">
        <span className="sr-only">Search a player by name</span>
        <input
          value={query}
          onFocus={() => void load()}
          onChange={(e) => {
            setQuery(e.target.value);
            setPicked(null);
            void load();
          }}
          placeholder="Search a player, with or without #tag…"
          className="w-full rounded-xl border border-line bg-white/[0.04] px-4 py-3 text-base outline-none transition placeholder:text-faint focus:border-accent/50"
          autoComplete="off"
          spellCheck={false}
        />
      </label>

      {failed && (
        <p className="mt-3 text-sm text-bad">
          The player index could not be loaded. Try again in a moment.
        </p>
      )}
      {!failed && loading && !index && (
        <p className="mt-3 text-sm text-faint">Loading the ladder…</p>
      )}
      {index && typedName.length > 0 && typedName.length < 2 && (
        <p className="mt-3 text-sm text-faint">Keep typing: two characters minimum.</p>
      )}
      {index && typedName.length >= 2 && results.length === 0 && !picked && (
        <p className="mt-3 text-sm text-muted">
          Nobody by that name is on a top-50 board. Only the top 50 of each champion
          is collected, so most players will not appear. If you added a #tag, check it.
        </p>
      )}

      {!picked && results.length > 0 && (
        <ul className="mt-3 divide-y divide-line/60 overflow-hidden rounded-xl border border-line">
          {results.map((p) => (
            <li key={p.n}>
              <button
                type="button"
                onClick={() => choose(p)}
                className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition hover:bg-white/[0.04]"
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">{p.n}</span>
                  <span className="block text-xs text-muted">
                    {p.c.length} champion{p.c.length === 1 ? "" : "s"} on the board
                  </span>
                </span>
                {p.tier && <TierBadge tier={p.tier} size={20} />}
              </button>
            </li>
          ))}
        </ul>
      )}

      {picked && (
        <PlayerProfile
          player={picked}
          champBySlug={champBySlug}
          onBack={() => setPicked(null)}
        />
      )}
    </div>
  );
}

/* Where a player sits on a board, as a badge rather than a line of text.
 *
 * Three bands, because the ladder is not linear in what it means: the podium
 * is a different achievement from the top ten, which is a different thing
 * again from being on the board at all. The styling escalates with it, so a
 * card reads before any of the numbers do.
 */
function RankBadge({ rank }: { rank: number | null }) {
  if (rank == null) return null;
  const band = rank <= 3 ? "podium" : rank <= 10 ? "top10" : "board";
  const tone = {
    podium: "border-gold/60 bg-gold/15 text-gold shadow-[0_0_20px_-4px_rgba(234,179,8,0.75)]",
    top10: "border-slate-200/45 bg-slate-200/[0.12] text-slate-100",
    board: "border-white/15 bg-black/50 text-muted",
  }[band];
  const glyph = band === "podium" ? GLYPHS.crown : band === "top10" ? GLYPHS.medal : null;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-bold tabular-nums backdrop-blur-sm ${tone}`}
      title={`Rank ${rank} on this board`}
    >
      {glyph && <Glyph d={glyph} size={13} />}
      #{rank}
    </span>
  );
}

function PlayerProfile({
  player,
  champBySlug,
  onBack,
}: {
  player: IndexPlayer;
  champBySlug: Map<string, ChampionRef>;
  onBack: () => void;
}) {
  const [account, setAccount] = useState<PlayerQueues>(null);
  const [loadingStats, setLoadingStats] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoadingStats(true);
    setAccount(null);
    fetchAccountStats(player)
      .then((q) => !cancelled && setAccount(q))
      .finally(() => !cancelled && setLoadingStats(false));
    return () => {
      cancelled = true;
    };
  }, [player]);

  const best = player.c.reduce<number | null>(
    (acc, e) => (e.r != null && (acc == null || e.r < acc) ? e.r : acc), null);

  return (
    <div className="mt-4">
      <button type="button" onClick={onBack} className="text-sm text-accent transition hover:opacity-80">
        ← Back to results
      </button>

      <div className="glass mt-3 rounded-2xl p-5 sm:p-6">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <h2 className="text-2xl font-semibold tracking-tight">{player.n}</h2>
          {player.tier && (
            <span className="inline-flex items-center gap-1.5 rounded-md border border-line bg-white/[0.04] px-2 py-1 text-xs font-medium">
              <TierBadge tier={player.tier} size={18} />
              {player.tier}
            </span>
          )}
          {player.lv != null && <span className="text-xs text-muted">Level {player.lv}</span>}
        </div>
        <p className="mt-2 flex items-center gap-1.5 text-sm text-muted">
          <Glyph d={GLYPHS.crown} className="text-gold" size={16} />
          On {player.c.length} champion board{player.c.length === 1 ? "" : "s"}
          {best != null && `, best rank #${best}`}
        </p>

        {/* ACCOUNT-WIDE, not per champion. The game's stats page reports the
            whole account for a queue, so this belongs to the player and is
            shown once -- attaching it to each champion card implied it was
            that champion's, which it never was. */}
        {(account?.ranked || account?.legendary) && (
          <div className="mt-5">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted">
              Account performance
            </p>
            <p className="mt-0.5 text-xs text-faint">
              Across every champion they play, not just the boards below
            </p>
            <div className="mt-3 grid gap-3 lg:grid-cols-2">
              {account.ranked && <QueuePanel title="Ranked" s={account.ranked} />}
              {account.legendary && <QueuePanel title="Legendary Ranked" s={account.legendary} />}
            </div>
          </div>
        )}
        {loadingStats && !account && (
          <p className="mt-4 text-xs text-faint">Loading account stats…</p>
        )}
      </div>

      <p className="mt-6 text-xs font-semibold uppercase tracking-wide text-muted">
        Champion boards
      </p>
      {/* A GRID, not a stack of wide rows. Champion art is portrait (308x560)
          and a full-width row is ~1048x90, so covering it showed a 4.7% slice
          of the artwork -- an unreadable smear. A card near the art's own
          aspect shows roughly a third of it, which is the character. */}
      <div className="mt-2 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {player.c.map((e) => {
          const champ = champBySlug.get(e.s);
          return (
            <Link
              key={e.s}
              href={`/champions/${e.s}`}
              className="group relative flex min-h-[16.5rem] flex-col justify-end overflow-hidden rounded-2xl border border-line transition hover:border-accent/40"
            >
              {/* A real <img>, not a CSS background, so it lazy-loads: a
                  player can sit on a dozen boards and these are large files. */}
              {champ && (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={champ.splash}
                  alt=""
                  loading="lazy"
                  aria-hidden
                  className="absolute inset-0 h-full w-full object-cover transition duration-500 group-hover:scale-[1.04]"
                  style={{ objectPosition: "center 18%" }}
                />
              )}
              <div className="absolute inset-0 bg-gradient-to-t from-bg via-bg/70 to-transparent" />

              {/* Top right, over the art: the rank is the headline of the
                  card, and the podium treatment should be visible before you
                  read a single word. */}
              <div className="absolute right-3 top-3 z-10">
                <RankBadge rank={e.r} />
              </div>

              <div className="relative p-4">
                <div className="flex items-center gap-2.5">
                  {champ && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={champ.icon}
                      alt=""
                      width={36}
                      height={36}
                      loading="lazy"
                      className="h-9 w-9 shrink-0 rounded-full object-cover ring-1 ring-white/20"
                    />
                  )}
                  <span className="min-w-0">
                    <span className="block truncate font-semibold leading-tight">
                      {champ?.name ?? e.s}
                    </span>
                    <span className="block text-xs text-muted">Champion board</span>
                  </span>
                </div>
                <div className="mt-3 flex items-center justify-between border-t border-white/10 pt-2.5 text-xs">
                  <span className="text-sm font-semibold tabular-nums text-accent">
                    {e.w != null ? `${e.w.toFixed(1)}%` : "--"}
                  </span>
                  <span className="tabular-nums text-muted">{e.g ?? "--"} games</span>
                  <span className="tabular-nums text-muted">
                    {e.sc != null ? e.sc.toLocaleString() : "--"} mastery
                  </span>
                </div>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
