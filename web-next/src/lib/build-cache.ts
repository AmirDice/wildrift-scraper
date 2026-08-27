/**
 * Cache for generated builds.
 *
 * Every generation is a real model call: the better part of a minute of
 * waiting, a few tenths of a cent, and one of the user's ten daily
 * generations. But the inputs
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
  buildBias?: string;
  /** The player's own rank bracket; a Master+ build and an Emerald build are
   *  different answers to the same champion. */
  skillLevel?: string;
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
    // Only present when the slider moved. A balanced request must serialise to
    // the exact shape it had before the slider existed: the balanced prompt is
    // byte-identical to the pre-slider prompt, so every v24 entry stays valid,
    // and adding the field unconditionally would have silently flushed the
    // whole namespace for no behavioural difference.
    ...(request.buildBias && request.buildBias !== "balanced"
      ? { buildBias: request.buildBias }
      : {}),
    skillLevel: request.skillLevel ?? "average",
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
  // v6: rune reasons were being stored against the wrong runes. They are zipped
  // with the runes by index, so one reason written for a rune that did not make
  // the final page shifted every reason after it, and a v5 entry has that
  // baked in -- a live Pantheon build explained Hubris as "Eyeball Collector:
  // scales AD from takedowns". Reasons are now re-keyed to the rune they name,
  // and every build cached before that fix is unreachable.
  // v7: the advisor changed MODEL. Every v6 entry was authored by DeepSeek,
  // and the switch to Gemini was made on build quality -- it won a blind
  // five-champion comparison judged on the builds themselves. Serving the
  // DeepSeek answer for the next 45 days would mean the change reaches nobody
  // who asks for a champion someone has already asked for. The prompt and the
  // validator moved underneath it too: kits now state energy costs, illegal
  // rune pages and mistimed swaps are rejected up front, and a build that
  // fails validation is no longer served at all.
  // v8: counter builds cached under v7 were generated while enemy shielding
  // was measured but not itemizable, so none of them answer it. The cache is
  // only hours old, so retiring it costs little against serving a build that
  // ignores four shielders for the next 45 days.
  // v9: summoner spells moved from a static lookup to the model, which can see
  // the enemy comp the lookup never could. A v8 entry carries the lookup's
  // answer -- correct, but blind to the matchup it was generated against.
  // v10: four changes to what the advisor produces, each of which makes a v9
  // entry wrong rather than merely older.
  //   - Support builds open with the free support item. Every cached support
  //     build skips it, which is the role's entire gold income.
  //   - Mana-bound kits are told mana is a limiting stat. Cached Sona and Ryze
  //     builds carry no mana item at all.
  //   - The damage path now reaches the boots, so cached AP builds can be
  //     holding attack-speed boots.
  //   - Active items are audited rather than passed over, so cached builds
  //     under-represent them.
  // Serving any of those for the next 45 days would hide all four fixes from
  // exactly the champions someone has already asked about.
  // v11: v10 was bumped too early. Five changes to what the advisor produces
  // landed AFTER it -- playstyles rewritten from mechanism to outcome, Max
  // stats no longer discounting actives, the summoner pool rules, and the
  // request reaching the rune page and the summoner slots instead of stopping
  // at the items. v10 went live before the last of those deployed, so entries
  // written in that window carry builds from the older prompt and would be
  // served for the full 45 days.
  //
  // The lesson, for whoever bumps this next: the version has to move with the
  // LAST advisor change that ships, not the first one noticed.
  // v12: builds now carry a playGuide. A v11 entry has no guide at all, so
  // serving one would render the panel empty for every champion someone has
  // already asked about -- which is most of the popular ones.
  // v13: seven champions had a multi-hit empowered attack counted as ONE on-hit
  // application, so Pantheon, Renekton, Shyvana, Viego, Fiora, Graves and Lee
  // Sin all read as low on-hit reliance and never saw on-hit items considered.
  // Sundered Sky's truncated passive text was repaired in the same batch. A v12
  // entry for any of them was built from the wrong profile.
  // v18, and v17 is deliberately SKIPPED: v17 keys exist in KV from the
  // 2026-07-29 window that was rolled back the same day, so reusing the number
  // would serve those entries again. v18: Kayn form text no longer fights an
  // explicit playstyle, and explicit-playstyle builds are authored by the
  // escalation model -- cached preference builds (including a live tanky
  // 'burst' Rhaast) predate both.
  // v19: complex champions (forms, curated identities, derived tanks -- 30 of
  // 141) escalate to the premium model even on standard requests. v18 entries
  // for those champions are minutes old and lite-authored, and Malphite's
  // measured failure was exactly a lite-authored standard build.
  // v20: the prompt was reworked in the 2026-08-05/06 batch and none of it
  // bumped the cache: ladder-core required candidates with scoring teeth, the
  // item-to-item synergyWith field, Burst and Glass cannon merged into
  // One-shot, the typical-comp unknown-enemy block, redundancy and
  // reactive-item withholding removed, and best-of-N machinery. A v19 counter
  // build predates all of it -- the reported symptom was a Graves counter
  // versus a triple-shield comp (Lee Sin, Riven, Karma) that carried no
  // Serpent's Fang, while a fresh generation of the identical request picks it
  // second with shields as its top stated priority. The stale entry was the
  // whole difference.
  // v21: everything that landed AFTER the v20 bump, in the same day -- threat
  // priority is now driven by measured enemy win rates, counter builds must
  // answer with at least one rune, the studio summoner pool reads the typical
  // ranked comp (Barrier joined it), skill level exists, and Skarner moved to
  // Baron. v20 was bumped mid-batch, so an entry written in the gap carries a
  // prompt none of those saw. The v20 namespace is hours old and likely near
  // empty; retiring it costs nothing and removes the doubt.
  // v22: the champion and rune source data turned out to predate patch 7.2 --
  // the Jul 6 scrape missed the 7.2 rune nerfs (~30 runes) and 14 champions'
  // ability changes (Lee Sin's whole kit among them), and ability formulas
  // were never re-extracted after the 7.2a / 7.2b text edits either. A v21
  // entry for any affected champion was reasoned from pre-7.2 numbers.
  // v23: patch 7.2c (2026-08-12) changed nine champions -- Cho'Gath, Jinx,
  // Nilah, Leona, Rumble, Nasus, Ryze, Warwick, Kog'Maw -- and ability
  // formulas were re-extracted for all nine, so a v22 entry for any of them
  // was reasoned from 7.2b damage, cooldowns and base stats. Warwick's ult
  // alone moved from 125/300/475 on 80/70/60 to 100/275/450 on 100/90/80.
  //
  // The whole namespace goes, not just those nine, because the key is a hash
  // of the request shape and the stored value records no champion: there is
  // nothing to match on, so a targeted purge is not possible. Counter builds
  // would need it anyway, since one names enemies rather than the champion
  // being built. 270 entries retired.
  // v24: 7.2c turned out to carry ITEM changes as well, and v23 was cut before
  // they were applied. The whole boots tier moved (Berserker's 30 to 35% attack
  // speed, Mercury's tenacity 15 to 30%, Armored Advance 35 to 30 armor,
  // Spellslinger's 40 to 35 AP) and five legendaries with it, including
  // Sunfire Aegis going 20 to 40 armor for 425 to 350 health. A v23 entry
  // priced items that no longer exist at those numbers, which is exactly what
  // a build recommendation is built out of. Three entries retired.
  // v25: the model now times the tier-3 boot upgrade itself (bootsUpgradeAfter:
  // after how many completed items the ~1000g enchant is worth buying, 0 =
  // never this game). A v24 entry has no timing and would render the old fixed
  // "after 2 items" forever, and the evaluation section it was scored under
  // has left the page.
  // v26: counter builds gained the LANE OPPONENT block -- the enemy in your
  // role is named, its lane profile (ranged-into-melee, sustained harass,
  // burst, CC) is stated, and the rune page must answer that lane first. A
  // v25 counter entry was reasoned against the team aggregate only (the
  // reported Riven-vs-Teemo standard-runes case).
  // v27: the magic-penetration hard-exclusive group exists (Void Staff /
  // Cryptbloom / Bloodletter's Curse -- no shared passive NAME, so the
  // passive-text extraction never formed it). A v26 entry could legally
  // carry Cryptbloom + Bloodletter's, a pair the game refuses.
  // v28: 7.2c fully landed on the DERIVED surfaces -- ability formulas
  // re-extracted for the nine changed champions, stale item effects fixed
  // (Kaenic's shield, Gunmetal's on-hit MS), and the Lucidity boots'
  // summoner-spell haste no longer counts as ability CDR. A v27 entry was
  // reasoned from pre-7.2c fight numbers.
  // v29: patch 7.2d (2026-08-26). Thirteen champions and two items moved, and
  // the derived surfaces moved with them -- ability formulas re-extracted for
  // the eleven whose text changed, Yone's base armor cut 43 -> 37, Edge of
  // Night's flat armor penetration 8 -> 12 and Stormsurge 2900 -> 2800 gold.
  // A v28 entry was reasoned from 7.2c numbers: it would still rate Twisted
  // Fate's Stacked Deck at 45% AP and price Stormsurge out of builds it now
  // fits.
  // v30: the enemy threat profile the counter prompt argues from changed
  // underneath it. Healing and shielding are now derived from the extracted
  // formulas rather than a scrape tag that sat on 109 of 141 champions, and
  // hard crowd control from the ability tooltips rather than one on 134 of
  // 141. A v29 counter build was reasoned against a picture where every comp
  // sustained and every comp had maximum crowd control; the namespace is a
  // few hours old, so retiring it costs almost nothing.
  // v31: counter prompts now carry the items that answer each threat category
  // this comp actually raised, drawn from the champion's own legal pool. A v30
  // build was chosen while the categories were prose -- "apply grievous
  // wounds" with no statement of which items do -- so it could answer a
  // sustain comp with nothing that cuts healing and still read as complete.
  return `build:v31:${crypto.createHash("sha256").update(shape).digest("hex").slice(0, 32)}`;
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
