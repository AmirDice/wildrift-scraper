/**
 * Cache for generated builds.
 *
 * Every generation is a real DeepSeek call: about 30 seconds of waiting, a few
 * tenths of a cent, and one of the user's ten daily generations. But the inputs
 * are a small, closed set -- champion, role, playstyle, objective, power spike,
 * damage path, and (in counter mode) up to five enemies. Two players asking for
 * "Graves, jungle, standard, balanced" want the same answer, and the model is
 * being paid to produce it twice.
 *
 * So the finished build is stored against a hash of its inputs. A hit returns
 * instantly and, deliberately, does NOT spend a generation from the daily
 * allowance: we did not pay for a model call, so neither should the player.
 *
 * The patch is part of the key. When the item and rune data move to 7.3, every
 * 7.2 build stops being reachable rather than quietly outliving its patch.
 */
import crypto from "node:crypto";
import statRules from "@/data/stat_rules.json";
import { kvGetJson, kvSetJson } from "@/lib/kv";

/** Builds are only valid for the patch whose item and rune data produced them. */
const PATCH = (statRules as { targetPatch?: string }).targetPatch ?? "unknown";

/** Long enough to span a patch cycle; the patch in the key does the real work. */
const TTL_SECONDS = 60 * 60 * 24 * 45;

export interface BuildRequestKey {
  champion: string;
  role: string;
  playstyle: string;
  objective: string;
  gamePhase: string;
  damagePath: string;
  championForm: string;
  aheadEnemy: string;
  mode: string;
  riskTolerance?: string;
  enemies: string[];
  allies: string[];
  /** Items and runes the player pinned; part of the key so a locked request
   *  never serves an unlocked cached build. */
  lockedItems?: string[];
  lockedRunes?: string[];
}

/**
 * Stable key for one request. Enemies and allies are sorted, because facing
 * Darius and Garen is the same problem as facing Garen and Darius, but the
 * snowball threat is not sorted away: it names one specific enemy.
 */
export function buildCacheKey(request: BuildRequestKey): string {
  const shape = JSON.stringify({
    patch: PATCH,
    champion: request.champion.toLowerCase(),
    role: request.role.toLowerCase(),
    playstyle: request.playstyle,
    objective: request.objective,
    gamePhase: request.gamePhase,
    damagePath: request.damagePath,
    championForm: request.championForm,
    aheadEnemy: request.aheadEnemy,
    mode: request.mode,
    riskTolerance: request.riskTolerance ?? "medium",
    enemies: [...request.enemies].map((e) => e.toLowerCase()).sort(),
    allies: [...request.allies].map((a) => a.toLowerCase()).sort(),
    lockedItems: [...(request.lockedItems ?? [])].map((s) => s.toLowerCase()).sort(),
    lockedRunes: [...(request.lockedRunes ?? [])].map((s) => s.toLowerCase()).sort(),
  });
  // Bump the version whenever the advisor's OUTPUT shape or logic changes, so
  // builds cached under the old behaviour are never served. v3: builds gained
  // summoner spells and item/rune locks. v4: the advisor was reworked around
  // derived champion combat profiles -- item scores split into competitive
  // candidates and a mandatory audit, situational swaps became reorderings
  // carrying a full resulting build, and rune swaps that free an item slot now
  // name its replacement. A v3 entry would render with pieces missing.
  // v5: requests carry risk tolerance, structured counter threats, per-mode
  // metadata (requestMeta) and, in counter mode, a counterSummary; a v4 entry
  // predates those, so it must not be served for a v5-shaped request.
  return `build:v5:${crypto.createHash("sha256").update(shape).digest("hex").slice(0, 32)}`;
}

export async function readCachedBuild(key: string): Promise<Record<string, unknown> | null> {
  return kvGetJson<Record<string, unknown> | null>(key, null);
}

export async function writeCachedBuild(key: string, build: unknown): Promise<void> {
  try {
    await kvSetJson(key, build, TTL_SECONDS);
  } catch {
    /* a cache miss next time is not worth failing a successful generation over */
  }
}
