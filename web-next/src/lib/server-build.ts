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

/** What the card renders: one server's most-common build, already named. */
export interface ServerBuild {
  items: { slug: string; name: string; icon: string }[];
  boots?: { slug: string; name: string; icon: string } | null;
  runes: { keystone?: string; minors: string[]; flex?: string };
  /** "41 of 50 players" behind the most-built item. */
  sample?: { count: number; of: number } | null;
}

/** The minimum a consensus build has to look like to be rendered. */
interface ConsensusLike {
  items: string[];
  boots?: string;
  runes: { keystone?: string; minors: string[]; flex?: string };
  sampleOf?: number;
  of?: number;
}

/** A consensus build in the shape the card renders. Server-side: the caller
 *  passes the item catalogue, which is another file the browser does not need. */
export function toServerBuild(
  build: ConsensusLike | null,
  item: (slug: string) => { slug: string; name: string; icon: string },
): ServerBuild | null {
  if (!build) return null;
  return {
    items: build.items.map(item),
    boots: build.boots ? item(build.boots) : null,
    runes: {
      keystone: build.runes.keystone,
      minors: build.runes.minors,
      flex: build.runes.flex,
    },
    sample: build.sampleOf && build.of ? { count: build.sampleOf, of: build.of } : null,
  };
}
