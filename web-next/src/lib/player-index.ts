/* The cross-board player index: loading, matching, and the tag hash.
 *
 * Shared by the full search page and the leaderboard's quick search so both
 * behave identically -- one place decides what "matches" means, and the index
 * is fetched at most once per session however many components ask for it.
 */

export type IndexEntry = {
  s: string;
  r: number | null;
  w: number | null;
  g: number | null;
  sc: number | null;
};

export type IndexPlayer = {
  n: string;
  /** FNV-1a of the folded riot tag. There is no plaintext tag in the data. */
  th: string | null;
  tier: string | null;
  lv: number | null;
  c: IndexEntry[];
};

/** Fold case and spaces so "Alpha Rengo", "alpha rengo" and "ALPHARENGO" all
 *  reach the same record. Ladder names are styled in ways nobody types back. */
export const fold = (s: string) => s.toLowerCase().replace(/\s+/g, "");

/**
 * FNV-1a 32-bit, byte-for-byte the same as scripts/export_captures.tag_hash.
 *
 * The tag is a search key, never a published field: the index stores only
 * this hash, so the file cannot be mined for tags. Someone who already knows
 * a player's tag can still search with it, which is the whole point.
 *
 * Not a security boundary -- tags are short enough to enumerate. It stops the
 * index being a bulk tag directory, which is the real concern.
 */
export function tagHash(tag: string): string | null {
  const folded = tag.replace(/\s+/g, "").toLowerCase();
  if (!folded) return null;
  let h = 0x811c9dc5;
  for (const ch of folded) {
    h = Math.imul(h ^ ch.codePointAt(0)!, 0x01000193) >>> 0;
  }
  return h.toString(16).padStart(8, "0");
}

let cache: Promise<IndexPlayer[]> | null = null;

/** Fetched once per session, shared by every caller. */
export function loadPlayerIndex(): Promise<IndexPlayer[]> {
  if (!cache) {
    cache = fetch("/player-index.json")
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status));
        return r.json();
      })
      .then((d: { players: IndexPlayer[] }) => d.players)
      .catch((e) => {
        cache = null; // a failed load must not poison later attempts
        throw e;
      });
  }
  return cache;
}

/**
 * Players matching a query, best first.
 *
 * The query may carry a #tag. When it does, the tag must match as well --
 * that is what lets someone disambiguate two players sharing a name, without
 * the site ever having shown them a tag.
 */
export function matchPlayers(players: IndexPlayer[], query: string, limit = 40): IndexPlayer[] {
  const [rawName, rawTag = ""] = query.split("#");
  const q = fold(rawName);
  const wantTag = rawTag.trim() ? tagHash(rawTag) : null;
  if (q.length < 2) return [];

  const scored: { p: IndexPlayer; rank: number }[] = [];
  for (const p of players) {
    if (wantTag && p.th !== wantTag) continue;
    const n = fold(p.n);
    // Exact, then prefix, then substring: a fully typed name should not be
    // buried under longer names that merely contain it.
    const rank = n === q ? 0 : n.startsWith(q) ? 1 : n.includes(q) ? 2 : -1;
    if (rank >= 0) scored.push({ p, rank });
  }
  scored.sort(
    (a, b) => a.rank - b.rank || b.p.c.length - a.p.c.length || a.p.n.localeCompare(b.p.n),
  );
  return scored.slice(0, limit).map((x) => x.p);
}

/* ---- per-champion stats, fetched only for a player being viewed --------- */

export type QueueStats = {
  games: number | null; wr: number | null; kda: number | null; tf: number | null;
  gpm: number | null; dmg: number | null; taken: number | null; turret: number | null;
  mvp: number | null; sRating: number | null; aRating: number | null;
  legendary: number | null; penta: number | null; quadra: number | null;
  triple: number | null; firstBlood: number | null;
};

export type PlayerQueues = { ranked?: QueueStats; legendary?: QueueStats } | null;

/**
 * The player's ACCOUNT-WIDE Ranked and Legendary Ranked stats.
 *
 * These come from the profile's stats page, which reports the whole account
 * for a queue -- not the champion whose board we happened to reach it from.
 * The same player read via two boards therefore returns near-identical
 * numbers (340 vs 342 ranked games, 47.6% vs 47.7%), differing only because
 * the boards were captured days apart.
 *
 * So there is exactly one true reading per queue, and the freshest wins.
 * Games played only ever increase, which makes the higher count the later
 * capture -- a more reliable ordering than the capture date, since a board
 * can be re-extracted without being re-scraped.
 *
 * Deliberately not in the index: sixteen numbers per queue would bloat a file
 * every visitor downloads, to serve one profile at a time. The per-champion
 * files already carry it, and a player is on few boards.
 */
export async function fetchAccountStats(player: IndexPlayer): Promise<PlayerQueues> {
  const readings: NonNullable<PlayerQueues>[] = [];
  await Promise.all(
    player.c.map(async (entry) => {
      try {
        const res = await fetch(`/players/${entry.s}.json`);
        if (!res.ok) return;
        const data = (await res.json()) as { players: { r: number; p: string; stats: PlayerQueues }[] };
        // Match on rank AND name: the index and the champion file come from
        // the same export, but a later re-export can shift ranks, and a wrong
        // join here would show one player's stats under another's name.
        const row = data.players.find(
          (p) => p.r === entry.r && fold(p.p ?? "") === fold(player.n),
        );
        if (row?.stats) readings.push(row.stats);
      } catch {
        /* one unreachable champion file must not blank the whole profile */
      }
    }),
  );
  if (!readings.length) return null;

  const freshest = (queue: "ranked" | "legendary") =>
    readings
      .map((r) => r[queue])
      .filter((s): s is QueueStats => s != null)
      .sort((a, b) => (b.games ?? -1) - (a.games ?? -1))[0];

  const ranked = freshest("ranked");
  const legendary = freshest("legendary");
  return ranked || legendary ? { ranked, legendary } : null;
}
