/**
 * What the top fifty players actually build, as a build.
 *
 * This is the fallback for every surface that wants to show something for a
 * champion nobody has generated yet: the draft page's instant panel and the
 * overlay's offline bundle.
 *
 * It costs nothing. ladder_builds.json is already in the repo, already
 * refreshed with each ladder collection, and is a record of what real top-50
 * players hold rather than an opinion about what they should. That makes it a
 * better default than the alternative we tried: generating a build for all 141
 * champions up front exhausted the Gemini prepayment at 80 champions, and the
 * 61 that did not make it were the whole problem it was meant to solve.
 *
 * A generated build still wins when one exists -- it answers the player's
 * actual settings, which a consensus cannot -- so this is only ever consulted
 * on a miss, and the caller is told which it got so it can say so.
 */
import ladderData from "@/data/ladder_builds.json";
import ladderDataNa from "@/data/ladder_builds_na.json";
import { BUILD_SERVERS, type BuildServer } from "@/lib/server-build";
import engineData from "@/data/engine.json";
import itemsData from "@/data/items.json";
import pulseData from "@/data/ladder_pulse.json";

type Counted = { name?: string; slug?: string; count?: number; of?: number };
type LadderEntry = {
  items?: Counted[];
  keystones?: Counted[];
  minors?: Counted[];
  /** The six shown items in the order the top 50 BUY them, boots included
   *  where they are bought (scripts/ladder_item_order.py). Absent on a board
   *  whose per-player builds were never read. */
  order?: string[];
};

/**
 * One record per SERVER, because that is the question the champion pages and
 * the Build Studio ask: what do the top 50 on THIS server build. The answers
 * differ, so they cannot be one merged file -- and a server with nothing
 * collected yet must read as "not collected yet" rather than silently
 * borrowing another server's answer.
 *
 * CN is deliberately absent. Tencent publishes per-lane win, pick and ban
 * rates (that is where the CN boards come from) but no item data: the
 * per-champion build endpoint is not public, and CN builds live behind the
 * in-app companion API with signed parameters. Nothing here can fill it, so
 * nothing here pretends to.
 */
const BY_SERVER: Record<BuildServer, Record<string, LadderEntry>> = {
  eu: ladderData as Record<string, LadderEntry>,
  na: ladderDataNa as Record<string, LadderEntry>,
  cn: {},
};

/** The EU record, which every older caller means by "the ladder". */
const LADDER = BY_SERVER.eu;
const RUNES = (engineData as { runes?: Record<string, { tree?: string; slot?: number; type?: string }> }).runes ?? {};
const ITEM = new Map(
  (itemsData as { slug: string; name: string; category?: string }[]).map((i) => [i.slug, i]),
);

export interface LadderBuild {
  /** The five non-boot items. In PURCHASE order when `ordered` is set,
   *  otherwise most-built first. */
  items: string[];
  boots?: string;
  /** Where the boots fall in the purchase order, 0-based across all six. */
  bootsAt?: number;
  /** True when `items` and `bootsAt` describe the order players buy in,
   *  rather than how many of them bought each item. */
  ordered?: boolean;
  runes: { keystone?: string; minors: string[]; flex?: string; primaryTree?: string };
  /** Where this came from, so the UI can label it honestly. */
  source: "ladder";
  /** Pick count of the most-built item, out of the sample. */
  sampleOf?: number;
  /** How many players that count is out of, so the card can say "41 of 50". */
  of?: number;
}

function isBoots(slug: string): boolean {
  return ITEM.get(slug)?.category === "Boots";
}

/**
 * The most-picked rune in one tree and slot across the WHOLE ladder.
 *
 * Built once from every champion's record, so it answers "what do players put
 * in Precision slot 2" without any champion's own preferences deciding it.
 */
const POPULAR_IN_SLOT = (() => {
  const tally = new Map<string, Map<string, number>>();
  for (const entry of Object.values(LADDER)) {
    for (const m of entry.minors ?? []) {
      const meta = RUNES[m.name ?? ""];
      if (!meta?.tree || !meta.slot || !m.name) continue;
      const key = `${meta.tree}:${meta.slot}`;
      const inner = tally.get(key) ?? new Map<string, number>();
      inner.set(m.name, (inner.get(m.name) ?? 0) + (m.count ?? 0));
      tally.set(key, inner);
    }
  }
  const best = new Map<string, string>();
  for (const [key, inner] of tally) {
    let top = "";
    let n = -1;
    for (const [name, count] of inner) {
      if (count > n) { n = count; top = name; }
    }
    if (top) best.set(key, top);
  }
  return best;
})();

function popularInSlot(tree: string, slot: number): string | undefined {
  return POPULAR_IN_SLOT.get(`${tree}:${slot}`);
}

/** Total ladder picks per minor rune, for choosing a flex outside a tree. */
const MINOR_PICKS = (() => {
  const tally = new Map<string, number>();
  for (const entry of Object.values(LADDER)) {
    for (const m of entry.minors ?? []) {
      if (m.name) tally.set(m.name, (tally.get(m.name) ?? 0) + (m.count ?? 0));
    }
  }
  return [...tally.entries()].sort((a, b) => b[1] - a[1]);
})();

/** The ladder's most-picked minor from any tree other than this one. */
function popularOutsideTree(tree: string): string | undefined {
  return MINOR_PICKS.find(([name]) => {
    const meta = RUNES[name];
    return meta?.tree && meta.tree !== tree;
  })?.[0];
}

/**
 * A legal rune page from the ladder's counts.
 *
 * NOT simply the three most-picked minors. Checked across the roster: for 89
 * of 140 champions the top three do not form a legal page, because a page
 * takes one minor from each of slots 1, 2 and 3 of a single tree and the raw
 * counts happily return two from the same slot. So the tree is chosen by total
 * count and then each slot is filled by the best rune the ladder picked in it.
 */
function runePage(entry: LadderEntry): LadderBuild["runes"] {
  const keystone = entry.keystones?.[0]?.name;
  const minors = entry.minors ?? [];
  const byTree = new Map<string, number>();
  for (const m of minors) {
    const tree = RUNES[m.name ?? ""]?.tree;
    if (tree) byTree.set(tree, (byTree.get(tree) ?? 0) + (m.count ?? 0));
  }
  let primaryTree = "";
  let best = -1;
  for (const [tree, total] of byTree) {
    if (total > best) { best = total; primaryTree = tree; }
  }
  const picked: string[] = [];
  for (const slot of [1, 2, 3]) {
    const hit = minors.find((m) => {
      const meta = RUNES[m.name ?? ""];
      return meta?.tree === primaryTree && meta?.slot === slot;
    });
    // A champion's ladder record holds only its top three minors, so once the
    // primary tree is fixed a slot can have nothing in it -- Nilah and Yone
    // both came back with two-minor pages, which is not a page anyone can
    // equip. The gap is filled from what the WHOLE ladder picks in that tree
    // and slot, so it is still a real player's rune rather than an invention.
    const name = hit?.name ?? popularInSlot(primaryTree, slot);
    if (name) picked.push(name);
  }
  // The flex is the best minor from any OTHER tree; a page runs two trees, not
  // one. When all three of a champion's recorded minors sit in the primary
  // tree there is nothing here to use -- that was 22 of 141 champions, and the
  // rune validator rejected every one of their pages -- so it falls back to
  // what the whole ladder picks outside this tree.
  const flex = minors.find((m) => {
    const meta = RUNES[m.name ?? ""];
    return meta && meta.tree && meta.tree !== primaryTree;
  })?.name ?? popularOutsideTree(primaryTree);
  return { keystone, minors: picked, flex, primaryTree: primaryTree || undefined };
}

/** The top-fifty consensus build for a champion on one server, or null if that
 *  server has no record of it. Defaults to EU, which is what every caller
 *  written before the site had more than one board means. */
export function ladderConsensusBuild(
  champion: string,
  server: BuildServer = "eu",
): LadderBuild | null {
  const entry = BY_SERVER[server][champion];
  if (!entry?.items?.length) return null;
  const items: string[] = [];
  let boots: string | undefined;
  for (const row of entry.items) {
    const slug = row.slug ?? "";
    if (!slug || !ITEM.has(slug)) continue;
    if (isBoots(slug)) {
      boots ??= slug;
      continue;
    }
    if (items.length < 5) items.push(slug);
  }
  if (items.length < 5) return null;
  // Reorder to the purchase order when the board recorded one AND it covers
  // exactly the six picked above. The two are chosen by the same rule on the
  // same catalogue, so they agree; the check is there so that a mismatch
  // falls back to most-built order instead of silently dropping an item.
  const shown = boots ? [...items, boots] : [...items];
  const order = entry.order ?? [];
  const covers = order.length === shown.length && shown.every((slug) => order.includes(slug));
  return {
    items: covers ? order.filter((slug) => slug !== boots) : items,
    boots,
    bootsAt: covers && boots ? order.indexOf(boots) : undefined,
    ordered: covers,
    runes: runePage(entry),
    source: "ladder",
    sampleOf: entry.items[0]?.count,
    of: entry.items[0]?.of,
  };
}

const MONTHS = ["January", "February", "March", "April", "May", "June", "July",
  "August", "September", "October", "November", "December"];

/**
 * When a server's BUILDS were collected, as the card should state it.
 *
 * Not the board's win-rate date. A collection can read win rates alone -- the
 * 2026-09-03 EU refresh did -- and the item tables are then carried forward
 * from the last collection that read builds. The card used to print the
 * win-rate date under builds that were two weeks older, which is the one date
 * on it that describes something else. `buildsFrom` in ladder_pulse.json is
 * written exactly when that carry happens.
 *
 * Formatted here, on the server, by hand rather than with toLocaleDateString:
 * the value is a string prop, and a date formatted in two locales is a
 * hydration mismatch waiting for the first visitor outside en-US.
 */
export function ladderBuildsCollected(server: BuildServer): string | undefined {
  if (server !== "eu") return undefined;
  const pulse = pulseData as { buildsFrom?: string; generatedAt?: string };
  const stamp = (pulse.buildsFrom ?? pulse.generatedAt ?? "").slice(0, 10);
  const [y, m, d] = stamp.split("-").map(Number);
  if (!y || !m || !d) return undefined;
  return `${MONTHS[m - 1]} ${d}, ${y}`;
}

/** Every server's answer for one champion, for the per-server build card. */
export function buildsByServer(champion: string): Record<BuildServer, LadderBuild | null> {
  return Object.fromEntries(
    BUILD_SERVERS.map((s) => [s, ladderConsensusBuild(champion, s)]),
  ) as Record<BuildServer, LadderBuild | null>;
}
