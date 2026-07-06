import countersData from "@/data/counters.json";
import { getChampion, type Champion } from "@/lib/data";

const C = countersData as unknown as Record<string, { weak: string[]; strong: string[] }>;

/** Champions this champion is strong / weak against, resolved to full objects. */
export function getMatchups(slug: string): { strong: Champion[]; weak: Champion[] } {
  const e = C[slug];
  if (!e) return { strong: [], weak: [] };
  const resolve = (ss: string[]) =>
    ss.map((s) => getChampion(s)).filter((c): c is Champion => !!c);
  return { strong: resolve(e.strong), weak: resolve(e.weak) };
}
