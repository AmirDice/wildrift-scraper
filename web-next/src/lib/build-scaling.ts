/**
 * "Fully scaled" build stats: what the loadout is worth once everything that
 * ramps has ramped.
 *
 * The transparent sheet in customizer-data.ts deliberately shows only
 * guaranteed stats, because a resting stat page that quietly includes Muramana's
 * mana conversion or a fully stacked Eyeball Collector is lying about what you
 * have when the fight starts. But the opposite is also true: a stat page that
 * ignores them undersells half the item pool, and the Custom Build Lab is
 * exactly where you want to compare a stacking item against a static one.
 *
 * So both exist, behind a toggle, and this module is the second half:
 *
 *   guaranteed  base + printed item stats + always-on rune stats
 *   fully scaled  the above, plus every quantified conversion and max-stack
 *                 value we have real data for
 *
 * Everything here is driven by the extracted engine data (engine.json's `itemFx`,
 * `runeEngine` and `runeFx`), never by hand-written numbers. Effects we have no
 * number for stay out, and every applied value is returned as a labelled
 * contribution so the UI can show its work.
 */
import engineData from "@/data/engine.json";
import itemData from "@/data/items.json";
import runeScalingData from "@/data/rune_scaling.json";
import { listedBuildStats, type ListedBuildStats } from "@/lib/customizer-data";

type StatValue = { value?: number; percent?: boolean } | number;

type EngineShape = {
  champions: Record<string, { class?: string }>;
  items: Record<string, { name: string; stats?: Record<string, StatValue> }>;
  itemFx?: Record<string, Record<string, unknown>>;
  runeEngine?: Record<string, Record<string, unknown>>;
  runeFx?: {
    keystones?: Record<string, Record<string, unknown>>;
    minors?: Record<string, Record<string, unknown>>;
  };
};

/** One max-stack stat from data/rune_scaling.json. */
type RuneStat = {
  stat: string;
  value?: number;
  /** Adaptive runes pay one or the other; the build decides which. */
  ad?: number;
  ap?: number;
  /** Runes that pay melee and ranged champions differently. */
  melee?: number;
  ranged?: number;
  note?: string;
  /** Already counted by the guaranteed sheet, so scaled mode must not re-add. */
  alreadyGuaranteed?: boolean;
};

/** A quantified rune value that is NOT a stat: proc damage, shields, amps. */
export interface RuneEffect {
  rune: string;
  label: string;
  /** Either a fixed string, or a [level 1, level 15] range resolved on read. */
  value: string;
  note?: string;
}

type RuneScalingShape = {
  runes: Record<string, {
    stats?: RuneStat[];
    effects?: { label: string; value: string | [number, number]; note?: string }[];
    evidence?: string;
  }>;
  unmodelled: string[];
};

const DATA = engineData as unknown as EngineShape;
// The JSON widens [lo, hi] level ranges to number[], so the cast goes through
// unknown rather than pretending the literal type already matches.
const RUNE_SCALING = runeScalingData as unknown as RuneScalingShape;
const ITEM_STATS = new Map(
  (itemData as unknown as { slug: string; stats?: Record<string, StatValue> }[])
    .map((item) => [item.slug, item.stats ?? {}]),
);

/** Matches RANGED_CLASSES in web/fight_engine.py, which splits melee and ranged
 *  item values the same way. One convention across the project beats two. */
const RANGED_CLASSES = new Set(["Marksman", "Mage", "Enchanter"]);

export interface ScalingContribution {
  /** Item or rune the value comes from. */
  source: string;
  /** Which stat it lands on: a stat-sheet key, or one of the percentage forms
   *  that can only be resolved once every flat value is known. */
  stat: keyof ListedBuildStats
    | "attackSpeedPct" | "moveSpeedPct" | "armorPct" | "mrPct" | "hpPctMax";
  /** Amount added on top of what the guaranteed sheet already counted. */
  amount: number;
  /** Human-readable explanation of where the number comes from. */
  note: string;
}

export interface ScaledBuildStats {
  stats: ListedBuildStats;
  contributions: ScalingContribution[];
  /** Rune values that are real and quantified but are not stats. */
  runeEffects: RuneEffect[];
}

const MAX_LEVEL = 15;

/** Resolves a possibly level-scaling engine value at the given level. */
function resolve(value: unknown, level: number): number {
  if (typeof value === "number") return value;
  if (Array.isArray(value) && value.length === 2) {
    return interpolate(Number(value[0]), Number(value[1]), level);
  }
  if (value && typeof value === "object" && "lvlRange" in value) {
    const range = (value as { lvlRange?: [number, number] }).lvlRange;
    if (Array.isArray(range) && range.length === 2) return interpolate(range[0], range[1], level);
  }
  return 0;
}

function interpolate(low: number, high: number, level: number): number {
  const clamped = Math.min(Math.max(level, 1), MAX_LEVEL);
  return low + (high - low) * ((clamped - 1) / (MAX_LEVEL - 1));
}

/** What an item already contributed to a stat through its printed stat line. */
function printed(slug: string, key: string): number {
  const raw = (ITEM_STATS.get(slug) ?? DATA.items[slug]?.stats ?? {})[key];
  if (raw === undefined) return 0;
  return typeof raw === "number" ? raw : Number(raw.value ?? 0);
}

const itemName = (slug: string) => DATA.items[slug]?.name ?? slug;

/**
 * Item passives whose value is a plain stat we can add, keyed by the engine
 * field. `printedAs` names the stat line the item may ALREADY grant, so a
 * passive that tops an existing stat up (Bloodthirster: 8% printed physical
 * vamp, 12% once crits are landing) only contributes the difference.
 */
const ITEM_FLAT_FX: Record<string, {
  stat: ScalingContribution["stat"];
  printedAs?: string;
  note: (value: number) => string;
}> = {
  apFlatPassive: { stat: "ap", printedAs: "ap", note: (v) => `+${v} AP once the passive is active` },
  hpFlatPassive: { stat: "hp", printedAs: "hp", note: (v) => `+${v} Health once the passive is active` },
  hasteFlatPassive: { stat: "haste", printedAs: "abilityHaste", note: (v) => `+${v} Ability Haste from the passive` },
  msFlat: { stat: "moveSpeed", printedAs: "moveSpeed", note: (v) => `+${v} Move Speed while the passive holds` },
  msPct: { stat: "moveSpeedPct", printedAs: "moveSpeed", note: (v) => `+${v}% Move Speed while the passive holds` },
  asPctPassive: { stat: "attackSpeedPct", printedAs: "attackSpeed", note: (v) => `+${v}% Attack Speed at full ramp` },
  omnivampPct: { stat: "omnivamp", printedAs: "omnivamp", note: (v) => `${v}% Omnivamp at full ramp` },
  physVampPct: { stat: "physicalVamp", printedAs: "physicalVamp", note: (v) => `${v}% Physical Vamp with the passive up` },
  healShieldAmpPct: { stat: "healShieldPower", printedAs: "healShieldPower", note: (v) => `+${v}% Heal & Shield Power` },
};

/** Rune fields in the older damage-engine model, used only for runes that
 *  data/rune_scaling.json does not cover. */
const RUNE_FLAT_FX: Record<string, { stat: ScalingContribution["stat"]; label: string }> = {
  bonusAd: { stat: "ad", label: "Attack Damage" },
  bonusAp: { stat: "ap", label: "Ability Power" },
  hpFlat: { stat: "hp", label: "Health" },
  armorFlat: { stat: "armor", label: "Armor" },
  mrFlat: { stat: "mr", label: "Magic Resist" },
  manaFlat: { stat: "mana", label: "Mana" },
  hasteFlat: { stat: "haste", label: "Ability Haste" },
  asPctAvg: { stat: "attackSpeedPct", label: "Attack Speed" },
  msPctAvg: { stat: "moveSpeedPct", label: "Move Speed" },
  bonusAdAtStacks: { stat: "ad", label: "Attack Damage at full stacks" },
  healShieldAmpPct: { stat: "healShieldPower", label: "Heal & Shield Power" },
};

/** Stat keys used by rune_scaling.json that are not plain sheet keys. */
const RUNE_STAT_LABEL: Record<string, string> = {
  attackSpeedPct: "Attack Speed",
  moveSpeedPct: "Move Speed",
  hpPctMax: "max Health",
  armorPct: "Armor",
  mrPct: "Magic Resist",
  tenacity: "Tenacity",
  omnivamp: "Omnivamp",
  healShieldPower: "Heal & Shield Power",
  hpRegen: "Health Regen",
  haste: "Ability Haste",
  mana: "Mana",
  hp: "Health",
  ad: "Attack Damage",
  ap: "Ability Power",
};

/** Runes the guaranteed sheet already counts, so scaled mode must not re-add. */
const ALREADY_IN_LISTED = new Set(["Transcendence"]);

/** Renders a rune effect value: fixed text, or a level range resolved at the
 *  level the sheet is being read at. */
function effectValue(value: string | [number, number], level: number): string {
  if (typeof value === "string") return value;
  return String(Math.round(interpolate(value[0], value[1], level)));
}

/**
 * Champion base attack speed, needed because attack-speed bonuses are a
 * percentage of the base ratio rather than of the current value.
 */
function attackSpeedRatio(name: string, level: number): number {
  const base = listedBuildStats(name, [], 1);
  const atLevel = listedBuildStats(name, [], level);
  return base?.attackSpeed ?? atLevel?.attackSpeed ?? 0;
}

/**
 * The guaranteed sheet plus every conversion and max-stack value we can put a
 * real number on. Returns null for an unknown champion, exactly like
 * listedBuildStats.
 */
export function scaledBuildStats(
  name: string,
  itemSlugs: string[],
  level = 15,
  runeNames: string[] = [],
  ultActive = false,
): ScaledBuildStats | null {
  // The transform state has to reach this path too. Without it, switching Gnar
  // to Mega and then to "Fully scaled" made his stats DROP, because the scaled
  // sheet was recomputed from a build that had never heard of the ultimate.
  const listed = listedBuildStats(name, itemSlugs, level, runeNames, ultActive);
  const baseOnly = listedBuildStats(name, [], level, [], ultActive);
  if (!listed || !baseOnly) return null;

  const stats: ListedBuildStats = { ...listed };
  const contributions: ScalingContribution[] = [];
  const runeEffects: RuneEffect[] = [];
  let attackSpeedPercent = 0;
  let moveSpeedPercent = 0;
  // Percentage resistances and health apply to the total, so they resolve last.
  let armorPercent = 0;
  let mrPercent = 0;
  let hpPercentMax = 0;
  // Adaptive sources resolve after everything else, against the final AD/AP.
  const adaptive: { source: string; ad: number; ap: number; note: string }[] = [];
  const ranged = RANGED_CLASSES.has(DATA.champions?.[name]?.class ?? "");

  const add = (source: string, stat: ScalingContribution["stat"], amount: number, note: string) => {
    if (!Number.isFinite(amount) || Math.abs(amount) < 0.01) return;
    if (stat === "attackSpeedPct") attackSpeedPercent += amount;
    else if (stat === "moveSpeedPct") moveSpeedPercent += amount;
    else if (stat === "armorPct") armorPercent += amount;
    else if (stat === "mrPct") mrPercent += amount;
    else if (stat === "hpPctMax") hpPercentMax += amount;
    else stats[stat] += amount;
    // The guaranteed sheet folds omnivamp into both vamp columns before it
    // returns, so anything added afterwards has to fold itself in.
    if (stat === "omnivamp") {
      stats.physicalVamp += amount;
      stats.magicVamp += amount;
    }
    contributions.push({ source, stat, amount: Math.round(amount * 100) / 100, note });
  };

  /* ── runes ─────────────────────────────────────────────────────────────── */
  for (const rune of runeNames) {
    // data/rune_scaling.json is the primary source: it is the only one that
    // covers the whole pool, and its numbers are transcribed from the current
    // rune text with an evidence check (scripts/extract_rune_scaling.py). The
    // damage-engine model below is a fallback for anything it does not carry.
    const scaling = RUNE_SCALING.runes[rune];
    if (scaling) {
      for (const entry of scaling.stats ?? []) {
        if (entry.alreadyGuaranteed) continue;
        if (entry.stat === "adaptive") {
          adaptive.push({
            source: rune,
            ad: entry.ad ?? 0,
            ap: entry.ap ?? 0,
            note: entry.note
              ? `+${entry.ad ?? 0} AD or +${entry.ap ?? 0} AP · ${entry.note}`
              : `+${entry.ad ?? 0} AD or +${entry.ap ?? 0} AP`,
          });
          continue;
        }
        // Melee and ranged champions are paid differently by some runes; the
        // class split matches the one the fight engine already uses.
        const value = entry.melee != null || entry.ranged != null
          ? (ranged ? entry.ranged ?? 0 : entry.melee ?? 0)
          : entry.value ?? 0;
        if (!value) continue;
        const label = RUNE_STAT_LABEL[entry.stat] ?? entry.stat;
        const unit = entry.stat.endsWith("Pct") || entry.stat === "hpPctMax"
          || ["tenacity", "omnivamp", "healShieldPower"].includes(entry.stat) ? "%" : "";
        const split = entry.melee != null || entry.ranged != null
          ? ` (${ranged ? "ranged" : "melee"})`
          : "";
        add(rune, entry.stat as ScalingContribution["stat"], value,
          `+${value}${unit} ${label}${split}${entry.note ? ` · ${entry.note}` : ""}`);
        if (entry.stat === "haste") {
          stats.basicAbilityHaste += value;
          stats.ultimateAbilityHaste += value;
        }
      }
      for (const effect of scaling.effects ?? []) {
        runeEffects.push({
          rune,
          label: effect.label,
          value: effectValue(effect.value, level),
          note: effect.note,
        });
      }
      continue;
    }

    if (ALREADY_IN_LISTED.has(rune)) continue;
    const fx = DATA.runeEngine?.[rune]
      ?? DATA.runeFx?.keystones?.[rune]
      ?? DATA.runeFx?.minors?.[rune];
    if (!fx) continue;

    const adaptiveAd = resolve(fx.adaptiveAd, level);
    const adaptiveAp = resolve(fx.adaptiveAp, level);
    if (adaptiveAd || adaptiveAp) {
      adaptive.push({
        source: rune,
        ad: adaptiveAd,
        ap: adaptiveAp,
        note: `adaptive: +${Math.round(adaptiveAd)} AD or +${Math.round(adaptiveAp)} AP at full value`,
      });
      continue; // adaptive supersedes the rune's bonusAd/bonusAp mirror fields
    }
    for (const [field, mapping] of Object.entries(RUNE_FLAT_FX)) {
      const value = resolve(fx[field], level);
      if (!value) continue;
      const suffix = mapping.stat.endsWith("Pct") ? "%" : "";
      add(rune, mapping.stat, value, `+${Math.round(value * 10) / 10}${suffix} ${mapping.label}`);
      if (mapping.stat === "haste") {
        stats.basicAbilityHaste += value;
        stats.ultimateAbilityHaste += value;
      }
    }
  }

  /* ── items ─────────────────────────────────────────────────────────────── */
  for (const slug of itemSlugs) {
    const fx = DATA.itemFx?.[slug];
    if (!fx) continue;
    const source = itemName(slug);

    for (const [field, mapping] of Object.entries(ITEM_FLAT_FX)) {
      const total = resolve(fx[field], level);
      if (!total) continue;
      // Only the part the printed stat line did not already give us.
      const already = mapping.printedAs ? printed(slug, mapping.printedAs) : 0;
      const delta = total - already;
      if (delta <= 0) continue;
      add(source, mapping.stat, delta, mapping.note(Math.round(total * 10) / 10));
      if (mapping.stat === "haste") {
        stats.basicAbilityHaste += delta;
        stats.ultimateAbilityHaste += delta;
      }
    }

    const adaptiveAd = resolve(fx.adaptiveAdFlat, level);
    const adaptiveAp = resolve(fx.adaptiveApFlat, level);
    if (adaptiveAd || adaptiveAp) {
      adaptive.push({
        source,
        ad: adaptiveAd,
        ap: adaptiveAp,
        note: `adaptive: +${Math.round(adaptiveAd)} AD or +${Math.round(adaptiveAp)} AP`,
      });
    }
  }

  /* ── conversions, which depend on the totals above ─────────────────────── */
  for (const slug of itemSlugs) {
    const fx = DATA.itemFx?.[slug];
    if (!fx) continue;
    const source = itemName(slug);

    const adFromMana = resolve(fx.adFromManaPct, level);
    if (adFromMana) {
      add(source, "ad", stats.mana * adFromMana / 100,
        `${adFromMana}% of ${Math.round(stats.mana)} max Mana as AD`);
    }
    const apFromMana = resolve(fx.apFromManaPct, level);
    if (apFromMana) {
      add(source, "ap", stats.mana * apFromMana / 100,
        `${apFromMana}% of ${Math.round(stats.mana)} max Mana as AP`);
    }
    const hpFromMana = resolve(fx.hpFromManaPct, level);
    if (hpFromMana) {
      add(source, "hp", stats.mana * hpFromMana / 100,
        `${hpFromMana}% of ${Math.round(stats.mana)} max Mana as Health`);
    }
    const apFromBonusHp = resolve(fx.apFromBonusHpPct, level);
    if (apFromBonusHp) {
      const bonusHp = Math.max(0, stats.hp - baseOnly.hp);
      add(source, "ap", bonusHp * apFromBonusHp / 100,
        `${apFromBonusHp}% of ${Math.round(bonusHp)} bonus Health as AP`);
    }
  }

  /* ── adaptive resolution, once AD and AP are final ─────────────────────── */
  for (const entry of adaptive) {
    const bonusAd = Math.max(0, stats.ad - baseOnly.ad);
    if (stats.ap > bonusAd) add(entry.source, "ap", entry.ap, entry.note);
    else add(entry.source, "ad", entry.ad, entry.note);
  }

  /* ── percentage stats fold in last, against the finished totals ────────── */
  if (attackSpeedPercent) {
    stats.attackSpeed += attackSpeedRatio(name, level) * attackSpeedPercent / 100;
  }
  if (moveSpeedPercent) stats.moveSpeed *= 1 + moveSpeedPercent / 100;
  if (armorPercent) stats.armor *= 1 + armorPercent / 100;
  if (mrPercent) stats.mr *= 1 + mrPercent / 100;
  if (hpPercentMax) stats.hp *= 1 + hpPercentMax / 100;
  for (const key of Object.keys(stats) as (keyof ListedBuildStats)[]) {
    stats[key] = Math.round(stats[key] * 100) / 100;
  }

  return { stats, contributions, runeEffects };
}

/** Which of the selected items and runes actually have a scaling model. */
export function scalingSources(itemSlugs: string[], runeNames: string[]): string[] {
  const sources = [
    ...itemSlugs.filter((slug) => DATA.itemFx?.[slug]).map(itemName),
    ...runeNames.filter(
      (rune) => RUNE_SCALING.runes[rune]
        || (!ALREADY_IN_LISTED.has(rune)
          && (DATA.runeEngine?.[rune] || DATA.runeFx?.keystones?.[rune] || DATA.runeFx?.minors?.[rune])),
    ),
  ];
  return [...new Set(sources)];
}

/** Runes in the pool we have no quantified value for, so the UI can say so
 *  rather than implying the list is exhaustive. */
export function unmodelledRunes(runeNames: string[]): string[] {
  return runeNames.filter((rune) => RUNE_SCALING.unmodelled.includes(rune));
}
