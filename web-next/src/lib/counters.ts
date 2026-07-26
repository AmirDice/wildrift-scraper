import countersData from "@/data/counters.json";
import { getChampion, type Champion } from "@/lib/data";

export interface MatchupReference {
  slug: string;
  reason: string;
  confidence?: number;
}

export interface ResolvedMatchup extends MatchupReference {
  champion: Champion;
}

type RawReference = string | MatchupReference;
const C = countersData as unknown as Record<string, { weak: RawReference[]; strong: RawReference[] }>;

/** Champions this champion is strong / weak against, resolved to full objects. */
export function getMatchups(slug: string): { strong: ResolvedMatchup[]; weak: ResolvedMatchup[] } {
  const e = C[slug];
  if (!e) return { strong: [], weak: [] };
  const resolve = (references: RawReference[]) => references.flatMap((reference) => {
    const normalized = typeof reference === "string" ? { slug: reference, reason: "" } : reference;
    const champion = getChampion(normalized.slug);
    return champion ? [{ ...normalized, champion }] : [];
  });
  return { strong: resolve(e.strong), weak: resolve(e.weak) };
}
