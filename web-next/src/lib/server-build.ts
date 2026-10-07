/**
 * The per-server build vocabulary, with NO data behind it.
 *
 * Deliberately separate from ladder-build.ts: that module imports every
 * server's full records (~100KB each), and the card that renders them is a
 * Client Component. Importing the labels from there would have dragged all of
 * it into the browser bundle to render one champion's six items -- and calling
 * a helper exported from the client file on the server is a runtime error, not
 * a type one, which is exactly how this was found.
 *
 * So: shapes and words here, data in ladder-build.ts, pixels in
 * components/server-builds.tsx.
 */

export const BUILD_SERVERS = ["eu", "na", "cn"] as const;
export type BuildServer = (typeof BUILD_SERVERS)[number];

export const SERVER_LABEL: Record<BuildServer, string> = { eu: "EU", na: "NA", cn: "China" };

/**
 * Why a server has nothing to show, in its own words.
 *
 * China is not "coming soon". Tencent publishes per-lane win, pick and ban
 * rates -- which is where the CN boards come from -- and no item data: the
 * per-champion build endpoint is not public, and CN builds live behind the
 * in-app companion API with signed parameters. Until that changes, the honest
 * answer is that there is nothing to show.
 */
export const SERVER_GAP: Record<BuildServer, string> = {
  eu: "No ladder record for this champion yet.",
  na: "NA win rates are collected; NA builds are not, yet. They arrive with the next NA collection.",
  cn: "Tencent publishes China win rates but not builds, so there is nothing to show here.",
};

/** Level-15 profile for a ladder build. These are deterministic engine
 * estimates, not another win-rate sample: they let readers compare what the
 * server builds do under the same champion and target assumptions. */
export interface ServerBuildStats {
  cost: number;
  dps8?: number;
  burst3?: number;
  ttk?: number | null;
  ehp?: number;
  sustain?: number;
  ad?: number;
  ap?: number;
  hp?: number;
  armor?: number;
  mr?: number;
  moveSpeed?: number;
  attackSpeed?: number;
  haste?: number;
  crit?: number;
  mana?: number;
  physicalPenFlat?: number;
  physicalPen?: number;
  magicPenFlat?: number;
  magicPen?: number;
  lethality?: number;
  lifesteal?: number;
  profile: string[];
}

/** What the card renders: one server's most-common build, already named. */
export interface ServerBuild {
  /** In purchase order when `ordered`, most-built first otherwise. */
  items: { slug: string; name: string; icon: string; rate?: number }[];
  boots?: { slug: string; name: string; icon: string; rate?: number } | null;
  /** Where the boots fall among all six in the purchase order, 0-based. */
  bootsAt?: number | null;
  /** The card may number these as a buying order only when this is true. */
  ordered?: boolean;
  runes: { keystone?: string; minors: string[]; flex?: string };
  /** "41 of 50 players" behind the most-built item. */
  sample?: { count: number; of: number } | null;
  /** Optional engine/stat profile, calculated server-side for comparison. */
  stats?: ServerBuildStats;
}

/** The minimum a consensus build has to look like to be rendered. */
interface ConsensusLike {
  items: string[];
  /** Pick rate per item, when the ladder record includes counts. */
  itemRates?: Record<string, number>;
  boots?: string;
  bootsAt?: number;
  ordered?: boolean;
  runes: { keystone?: string; minors: string[]; flex?: string };
  sampleOf?: number;
  of?: number;
}

/** A consensus build in the shape the card renders. Server-side: the caller
 *  passes the item catalogue, which is another file the browser does not need. */
export function toServerBuild(
  build: ConsensusLike | null,
  item: (slug: string) => { slug: string; name: string; icon: string },
  stats?: ServerBuildStats,
): ServerBuild | null {
  if (!build) return null;
  return {
    items: build.items.map((slug) => ({ ...item(slug), rate: build.itemRates?.[slug] })),
    boots: build.boots ? { ...item(build.boots), rate: build.itemRates?.[build.boots] } : null,
    bootsAt: build.bootsAt ?? null,
    ordered: Boolean(build.ordered),
    runes: {
      keystone: build.runes.keystone,
      minors: build.runes.minors,
      flex: build.runes.flex,
    },
    sample: build.sampleOf && build.of ? { count: build.sampleOf, of: build.of } : null,
    stats,
  };
}
