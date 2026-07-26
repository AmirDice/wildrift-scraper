/**
 * The build the best player on a champion actually runs.
 *
 * Everything else on the site is derived: scraped win rates, generated builds,
 * engine scores. This is the one place for something that can only be recorded
 * by hand -- what the number-one player on a champion is genuinely building,
 * read off their profile and typed in.
 *
 * That makes it the most authoritative build on the site and the one that
 * cannot be automated, so it is admin-only: written through
 * /api/admin/best-builds with ADMIN_TOKEN, read by anyone.
 */
import { kvGetJson, kvSetJson, kvDelete } from "@/lib/kv";

export interface BestPlayerBuild {
  championSlug: string;
  /** The player this build was taken from. */
  player: string;
  /** Their rank or placement, free text: "Rank 1 EU", "Sovereign 200 LP". */
  standing?: string;
  /** Item slugs in purchase order. */
  items: string[];
  /** Boots slug, kept separate so it can be shown in its own slot. */
  boots?: string;
  /** Rune names: keystone first. */
  runes: string[];
  /** Anything worth saying about how they play it. */
  note?: string;
  updatedAt: string;
}

const key = (slug: string) => `bestbuild:${slug}`;
const INDEX_KEY = "bestbuild:index";

export async function getBestBuild(slug: string): Promise<BestPlayerBuild | null> {
  return kvGetJson<BestPlayerBuild | null>(key(slug), null);
}

/** Every recorded build, for the admin console and bulk display. */
export async function listBestBuilds(): Promise<BestPlayerBuild[]> {
  const slugs = await kvGetJson<string[]>(INDEX_KEY, []);
  const builds = await Promise.all(slugs.map((slug) => getBestBuild(slug)));
  return builds
    .filter((build): build is BestPlayerBuild => Boolean(build))
    .sort((left, right) => left.championSlug.localeCompare(right.championSlug));
}

export async function saveBestBuild(
  input: Omit<BestPlayerBuild, "updatedAt">,
): Promise<BestPlayerBuild> {
  const record: BestPlayerBuild = { ...input, updatedAt: new Date().toISOString() };
  await kvSetJson(key(record.championSlug), record);
  const index = await kvGetJson<string[]>(INDEX_KEY, []);
  if (!index.includes(record.championSlug)) {
    await kvSetJson(INDEX_KEY, [...index, record.championSlug].sort());
  }
  return record;
}

export async function deleteBestBuild(slug: string): Promise<boolean> {
  const existing = await getBestBuild(slug);
  if (!existing) return false;
  await kvDelete(key(slug));
  const index = await kvGetJson<string[]>(INDEX_KEY, []);
  await kvSetJson(INDEX_KEY, index.filter((entry) => entry !== slug));
  return true;
}
