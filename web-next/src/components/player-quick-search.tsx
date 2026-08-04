"use client";

import { useCallback, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { TierBadge } from "@/components/tier-badge";
import { loadPlayerIndex, matchPlayers, fold, type IndexPlayer } from "@/lib/player-index";

/* Find a player from the leaderboard page.
 *
 * The leaderboard answers "who is on this champion's board". People arriving
 * there often want the other direction -- a specific player -- and having to
 * discover a separate page first is the kind of friction that leaves a
 * feature unused.
 *
 * This is a finder, not a viewer: picking a result navigates to /player, which
 * owns the profile. Two places rendering the same profile would be two places
 * to keep correct.
 *
 * Tags are never shown here either; they can be typed to disambiguate.
 */
export function PlayerQuickSearch() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState<IndexPlayer[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState(false);

  const load = useCallback(async () => {
    if (index) return;
    try {
      setIndex(await loadPlayerIndex());
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, [index]);

  const results = useMemo(
    () => (index ? matchPlayers(index, query, 8) : []),
    [index, query],
  );
  const typedName = fold(query.split("#")[0] ?? "");

  const go = (p: IndexPlayer) => {
    setOpen(false);
    router.push(`/player?p=${encodeURIComponent(p.n)}`);
  };

  return (
    <div className="relative">
      <label className="block">
        <span className="sr-only">Search a player by name</span>
        <input
          value={query}
          onFocus={() => {
            setOpen(true);
            void load();
          }}
          onBlur={() => window.setTimeout(() => setOpen(false), 150)}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
            void load();
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && results[0]) go(results[0]);
            if (e.key === "Escape") setOpen(false);
          }}
          placeholder="Search a player…"
          className="w-full rounded-xl border border-line bg-white/[0.04] px-4 py-2.5 text-sm outline-none transition placeholder:text-faint focus:border-accent/50"
          autoComplete="off"
          spellCheck={false}
        />
      </label>

      {open && (failed || typedName.length >= 2) && (
        <div className="absolute left-0 right-0 top-full z-20 mt-1.5">
          <div className="glass-menu overflow-hidden rounded-xl p-1">
            {failed ? (
              <p className="px-3 py-2 text-xs text-bad">Player index unavailable.</p>
            ) : results.length === 0 ? (
              <p className="px-3 py-2 text-xs text-muted">
                Nobody by that name is on a top-50 board.
              </p>
            ) : (
              results.map((p) => (
                <button
                  key={p.n}
                  type="button"
                  // onMouseDown, not onClick: blur fires first on a click and
                  // would close the list before the handler ever ran.
                  onMouseDown={(e) => {
                    e.preventDefault();
                    go(p);
                  }}
                  className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left transition hover:bg-white/[0.06]"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{p.n}</span>
                    <span className="block text-[0.7rem] text-faint">
                      {p.c.length} champion{p.c.length === 1 ? "" : "s"}
                    </span>
                  </span>
                  {p.tier && <TierBadge tier={p.tier} size={18} />}
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
