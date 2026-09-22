import { createHash } from "node:crypto";

import items from "@/data/items.json";

type CatalogItem = { slug: string; removedIn?: string };

const catalog = items as CatalogItem[];
const slugs = catalog.map((item) => item.slug).sort();

/**
 * Identifies the exact item catalogue baked into this site build.
 *
 * The build advisor is a separate Vercel project with its own copy of the
 * catalogue. Sending this on every remote request turns a stale deployment
 * into an explicit, actionable error instead of silently hiding new items or
 * reporting them as unknown.
 */
export const ITEM_CATALOG_VERSION = createHash("sha256")
  .update(slugs.join("\n"))
  .digest("hex")
  .slice(0, 16);

export const ITEM_CATALOG_COUNT = catalog.length;
