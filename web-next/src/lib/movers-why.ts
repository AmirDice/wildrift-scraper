import historyData from "@/data/champion_change_history.json";
import loadoutsData from "@/data/cn_loadouts.json";
import changedData from "@/data/patch_changed_items.json";
import { MOVERS_META } from "@/lib/movers";

/**
 * Why a champion might have moved on the movers patch.
 *
 * A patch moves champions it never names: Zeri rose on 7.3d with nothing of
 * hers changed, because Essence Reaver and Fiendhunter Bolts, both in her
 * best China cores, were buffed. So a mover is tagged with the patch's own
 * change to it, if any, and with every changed item that sits in one of its
 * commonly built China cores.
 *
 * Server only: cn_loadouts.json is several megabytes and must not reach a
 * client bundle, which is why this is not in lib/movers.ts.
 */

/** A core counts as commonly built from this share of a lane's games. */
const COMMON_CORE_PICK = 2;

type HistoryEntry = { patch: string; modeOnly?: boolean };
type LoadoutLane = { tabs?: { items?: { rows?: { entities: string[]; pickRate: number }[] } } };

const HISTORY = (historyData as unknown as { champions: Record<string, HistoryEntry[]> }).champions;
const LOADOUTS = (loadoutsData as unknown as { champions: Record<string, LoadoutLane[]> }).champions;
const CHANGED = new Set((changedData as Record<string, string[]>)[MOVERS_META.patch] ?? []);

export interface MoverWhy {
  /** The patch changed this champion directly. */
  changed: boolean;
  /** Items the patch changed that are in this champion's common China cores. */
  items: string[];
}

export function moverWhy(slug: string, name: string): MoverWhy {
  const changed = (HISTORY[name] ?? []).some((e) => e.patch === MOVERS_META.patch && !e.modeOnly);
  const items = new Set<string>();
  for (const lane of LOADOUTS[slug] ?? []) {
    for (const row of lane.tabs?.items?.rows ?? []) {
      if (row.pickRate < COMMON_CORE_PICK) continue;
      for (const item of row.entities) if (CHANGED.has(item)) items.add(item);
    }
  }
  return { changed, items: [...items].sort() };
}
