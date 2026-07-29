import engineData from "@/data/engine.json";
import itemData from "@/data/items.json";
import championDetailsData from "@/data/champion_details.json";
import statRulesData from "@/data/stat_rules.json";

type StatValue = { value?: number; percent?: boolean } | number;

// A formula number is flat, per-ability-rank, or a per-CHAMPION-level range —
// the last for values a tooltip writes as "8 - 36 bonus magic damage".
type RankValue = number | number[] | { lvlRange: number[] };

type AbilityRatio = { stat: string; pct: RankValue };

type AbilityFormulaComponent = {
  name?: string;
  type?: string;
  base?: RankValue;
  ratios?: AbilityRatio[];
  hits?: RankValue;
  when?: string;
  alt?: boolean;
  note?: string;
  unmodeled?: string;
  durationS?: number;
};

type AbilityDefensiveComponent = AbilityFormulaComponent & {
  kind?: string;
  stat?: string;
  flat?: RankValue;
};

type AbilitySteroidComponent = {
  stat: string;
  pct?: RankValue;
  flat?: RankValue;
  /** A steroid can scale off a stat as well as grant a flat amount: Olaf's
   *  Ragnarok is "5 / 15 / 25 (+20% AD) Attack Damage". */
  ratios?: AbilityRatio[];
  from?: string;
  pctFromStat?: number;
  note?: string;
  unmodeled?: string;
  when?: string;
  alt?: boolean;
  durationS?: number;
};

type AbilityFormula = {
  name?: string;
  cooldowns?: RankValue;
  damage?: AbilityFormulaComponent[];
  defensive?: AbilityDefensiveComponent[];
  steroids?: AbilitySteroidComponent[];
  unmodeled?: string[];
};

type PassiveStatRule = {
  slot: string;
  stat: string;
  values: number[];
  label: string;
};

type CooldownVariantRule = { label: string; multiplier: number; note?: string };

type ChampionStatRule = {
  baseStats?: Record<string, { base: number; perLevel: number; lvl15?: number }>;
  statRules?: {
    attackSpeedRatio?: number;
    passiveStats?: PassiveStatRule[];
    cooldownVariants?: Record<string, CooldownVariantRule[]>;
  };
};

type ItemAlwaysRule = {
  stat: string;
  value?: number;
  percent?: boolean;
  set?: number;
  ad?: number;
  ap?: number;
  label: string;
};

type ItemStatRule = {
  always?: ItemAlwaysRule[];
  conditional?: { label: string; detail: string }[];
};

type StatRulesData = {
  targetPatch: string;
  champions: Record<string, ChampionStatRule>;
  items: Record<string, ItemStatRule>;
  runes?: Record<string, { description?: string }>;
};

type EngineData = {
  champions: Record<string, {
    baseStats?: Record<string, { base?: number; perLevel?: number }>;
    skillOrder?: Record<string, number[]>;
  }>;
  formulas: Record<string, { abilities?: Record<string, AbilityFormula> }>;
  items: Record<string, {
    name: string;
    icon: string;
    cost: number;
    category: string;
    stats?: Record<string, StatValue>;
  }>;
  runes: Record<string, { icon: string; tree: string; type: string; slot: number; description?: string }>;
  runeEngine?: Record<string, { hasteFlat?: number }>;
  mutex: Record<string, string[]>;
};

const DATA = engineData as EngineData;
const STAT_RULES = statRulesData as StatRulesData;

type ItemDetail = {
  slug: string;
  cost?: number;
  stats?: Record<string, StatValue>;
  passives?: string[];
  scopedStats?: Record<string, StatValue>;
};

const ITEM_DETAILS = new Map(
  (itemData as unknown as ItemDetail[]).map((item) => [item.slug, item]),
);

type ChampionAbility = {
  slot: string;
  key: string;
  name: string;
  text: string;
  cooldowns: string[];
  damageTypes: string[];
  icon: string;
  /** One icon per form, in the order the ability's two halves are named
   *  ("Javelin Toss / Takedown"). Only free-switching champions have it. */
  formIcons?: string[];
};

type ChampionDetail = { name: string; abilities?: ChampionAbility[] };
const CHAMPION_DETAILS = championDetailsData as Record<string, ChampionDetail>;

export interface CustomizerItem {
  slug: string;
  name: string;
  icon: string;
  cost: number;
  category: string;
  stats: Record<string, StatValue>;
  scopedStats: Record<string, StatValue>;
  passives: string[];
}

export interface CustomizerRune {
  name: string;
  icon: string;
  tree: string;
  type: string;
  slot: number;
  description: string;
}

export interface ListedBuildStats {
  ad: number;
  ap: number;
  hp: number;
  armor: number;
  mr: number;
  attackSpeed: number;
  crit: number;
  critDamage: number;
  haste: number;
  basicAbilityHaste: number;
  ultimateAbilityHaste: number;
  summonerSpellHaste: number;
  moveSpeed: number;
  mana: number;
  physicalPenFlat: number;
  physicalPen: number;
  magicPenFlat: number;
  magicPen: number;
  omnivamp: number;
  physicalVamp: number;
  magicVamp: number;
  tenacity: number;
  healShieldPower: number;
  manaRegen: number;
  hpRegen: number;
  itemCost: number;
}

export interface CalculatedAbilityDamage {
  label: string;
  type: string;
  amount: number;
  total?: number;
  hits: number;
  breakdown: string;
  unresolved: string[];
  context?: string;
}

export interface CalculatedAbilityEffect {
  label: string;
  value: string;
  context?: string;
}

export interface CalculatedChampionAbility {
  slot: string;
  key: string;
  name: string;
  icon: string;
  /** Per-form icons for free-switching champions; see ChampionAbility. */
  formIcons?: string[];
  rank: number;
  maxRank: number;
  unlockLevel?: number;
  baseCooldown?: number;
  cooldown?: number;
  hasteUsed?: number;
  cooldownVariants: { label: string; cooldown: number; note?: string }[];
  damage: CalculatedAbilityDamage[];
  effects: CalculatedAbilityEffect[];
  notes: string[];
  fallbackText?: string;
}

export interface ConditionalBuildEffect {
  source: string;
  label: string;
  detail: string;
}

/**
 * Does this champion have a kit the engine can actually simulate?
 *
 * An unreleased champion's guide page carries placeholder tooltips with no
 * numbers ("dealing damage and slowing them"), so extraction yields components
 * with empty values and every simulated build scores the same. A generated
 * build for such a champion is a guess no engine ever checked, so the studio
 * does not offer one.
 */
export function hasSimulatableKit(name: string): boolean {
  const abilities = DATA.formulas[name]?.abilities ?? {};
  return Object.values(abilities).some((ability) =>
    (ability.damage ?? []).some((part) => {
      const nums = (v: unknown): number[] =>
        typeof v === "number" ? [v]
          : Array.isArray(v) ? v.filter((x): x is number => typeof x === "number")
          : v && typeof v === "object" && "lvlRange" in (v as object)
            ? ((v as { lvlRange: number[] }).lvlRange ?? []) : [];
      const base = nums(part.base).some((x) => x !== 0);
      const ratio = (part.ratios ?? []).some((r) => nums(r.pct).some((x) => x !== 0));
      return base || ratio;
    }),
  );
}

export function customizerItems(): CustomizerItem[] {
  return Object.entries(DATA.items)
    .filter(([, item]) => item.category !== "Enchantment")
    .map(([slug, item]) => ({
      slug,
      name: item.name,
      icon: item.icon,
      cost: ITEM_DETAILS.get(slug)?.cost ?? item.cost,
      category: item.category,
      stats: ITEM_DETAILS.get(slug)?.stats ?? item.stats ?? {},
      scopedStats: ITEM_DETAILS.get(slug)?.scopedStats ?? {},
      passives: ITEM_DETAILS.get(slug)?.passives ?? [],
    }));
}

export function customizerRunes(): CustomizerRune[] {
  return Object.entries(DATA.runes)
    .map(([name, rune]) => ({
      name,
      icon: rune.icon,
      tree: rune.tree,
      type: rune.type,
      slot: rune.slot,
      description: STAT_RULES.runes?.[name]?.description ?? rune.description ?? "",
    }));
}

export function championAbilities(name: string): ChampionAbility[] {
  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  const detail = CHAMPION_DETAILS[slug]
    ?? Object.values(CHAMPION_DETAILS).find((champion) => champion.name === name);
  return detail?.abilities ?? [];
}

/** Item legality only. This does not evaluate damage, durability, or build quality. */
export function customBuildIssues(items: string[]): string[] {
  const issues: string[] = [];
  if (new Set(items).size !== items.length) issues.push("duplicate item");
  for (const [groupName, group] of Object.entries(DATA.mutex)) {
    const selected = items.filter((slug) => group.includes(slug));
    if (selected.length > 1) {
      issues.push(`${selected.map((slug) => DATA.items[slug]?.name ?? slug).join(" + ")} share the '${groupName}' passive`);
    }
  }
  return issues;
}

/**
 * Which items the current selection has ruled out, and why.
 *
 * customBuildIssues reports a conflict AFTER it exists, which means the player
 * picks an item, sees the build go red, and has to work out what to undo. This
 * answers the same question one step earlier -- before the click -- so the
 * picker can lock those items and say what is blocking them.
 */
export function blockedItems(selected: string[]): Record<string, string> {
  const blocked: Record<string, string> = {};
  const nameOf = (slug: string) => DATA.items[slug]?.name ?? slug;
  for (const slug of selected) {
    if (slug) blocked[slug] = "Already in this build.";
  }
  for (const [groupName, group] of Object.entries(DATA.mutex)) {
    const owner = selected.find((slug) => group.includes(slug));
    if (!owner) continue;
    for (const slug of group) {
      if (slug === owner || blocked[slug]) continue;
      blocked[slug] = `Shares the '${groupName}' passive with ${nameOf(owner)}, so only one of them works.`;
    }
  }
  return blocked;
}

/**
 * Transparent stat sheet for the customizer: champion base growth plus the
 * unconditional champion, item, and rune stats. It deliberately does not
 * simulate triggered passives, targets, combos, or assign a build score.
 */
/**
 * Champions who switch between two kits, and the names of those kits.
 *
 * This is NOT Kayn: he commits to one form for the rest of the game, so each of
 * his forms is generated as its own champion with its own build. These four
 * swap mid-fight, so they keep one build and one set of numbers, and only the
 * half of the kit you are reading changes. Their tooltips carry both halves in
 * one line ("Javelin Toss / Takedown"), which is where the names come from.
 */
export const DUAL_FORM_CHAMPIONS: Record<string, [string, string]> = {
  Nidalee: ["Human", "Cougar"],
  Gnar: ["Mini", "Mega"],
  Jayce: ["Hammer", "Cannon"],
  Yunara: ["Base", "Transcendent"],
};

/**
 * The self-buff a champion's ULTIMATE grants, if any.
 *
 * Aatrox's World Ender is +50% AD, Shyvana's Dragon's Descent +600 Health.
 * These are real stats, but they only exist while the ult is up, so the stat
 * sheet leaves them out -- it reports what a build gives you unconditionally.
 * That means the transformed numbers were not visible anywhere, which is what
 * `ultActive` exposes.
 */
export function ultTransform(name: string): { label: string; steroids: AbilitySteroidComponent[] } | null {
  const abilities = DATA.formulas[name]?.abilities ?? {};
  const ult = abilities["4"];
  const steroids = [...(ult?.steroids ?? []).filter((s) => s && s.stat)];
  // Some transforms carry their stats on the PASSIVE, not the ultimate: Gnar's
  // Rage Gene is what grants Mega's Health, Armour, MR and AD, and reading only
  // slot 4 meant toggling him to Mega changed nothing on the stat sheet. His
  // passive also lists MINI's rage bonuses, so take only the ones the tooltip
  // attributes to the transformed form.
  const onForm = DUAL_FORM_CHAMPIONS[name]?.[1];
  if (onForm) {
    for (const s of abilities["P"]?.steroids ?? []) {
      if (s?.stat && (s.note ?? "").toLowerCase().includes(onForm.toLowerCase())) {
        steroids.push(s);
      }
    }
  }
  if (!steroids.length) return null;
  return { label: ult?.name ?? "Ultimate", steroids };
}

/** Stat keys a steroid can move, mapped onto the listed stat sheet. */
const STEROID_TO_STAT: Record<string, keyof ListedBuildStats> = {
  ad: "ad", ap: "ap", hp: "hp", armor: "armor", mr: "mr",
  attackSpeed: "attackSpeed", moveSpeed: "moveSpeed", critChance: "crit",
};

function applyUltSteroids(
  stats: ListedBuildStats, name: string, level: number, baseStats?: ListedBuildStats | null,
): ListedBuildStats {
  const t = ultTransform(name);
  if (!t) return stats;
  const out = { ...stats };
  // Ult rank at level 13+ is 3 (ranks land at 5/9/13), so read the top rank the
  // champion actually has rather than assuming max.
  const rankIndex = level >= 13 ? 2 : level >= 9 ? 1 : 0;
  for (const s of t.steroids) {
    const key = STEROID_TO_STAT[s.stat];
    if (!key) continue;
    const flat = rankValue(s.flat, rankIndex, level);
    const pct = rankValue(s.pct, rankIndex, level);
    const current = Number(out[key]) || 0;
    // Some percentages act on the BONUS half of a stat, not the total, and the
    // tooltip says so: K'Sante's All Out "loses 80% bonus armor (not total)".
    // Charging that against his total armour would strip his base as well and
    // make the transform look catastrophic instead of a trade.
    const onBonus = (s.note ?? "").toLowerCase().includes("bonus");
    const scaleBase = onBonus && baseStats
      ? Math.max(0, current - (Number(baseStats[key]) || 0))
      : current;
    out[key] = (current + flat + (pct ? scaleBase * pct / 100 : 0)) as never;
  }
  return out;
}

export function listedBuildStats(
  name: string,
  itemSlugs: string[],
  level = 15,
  runeNames: string[] = [],
  ultActive = false,
): ListedBuildStats | null {
  const champion = DATA.champions[name];
  if (!champion) return null;
  const verifiedChampion = STAT_RULES.champions[name];

  const atLevel = (key: string, fallback = 0) => {
    const stat = verifiedChampion?.baseStats?.[key] ?? champion.baseStats?.[key];
    return (stat?.base ?? fallback) + (stat?.perLevel ?? 0) * Math.max(0, level - 1);
  };

  const generalHaste = atLevel("abilityHaste");
  const result: ListedBuildStats = {
    ad: atLevel("ad"),
    ap: atLevel("ap"),
    hp: atLevel("hp"),
    armor: atLevel("armor"),
    mr: atLevel("mr"),
    attackSpeed: atLevel("attackSpeed"),
    crit: atLevel("crit"),
    critDamage: 175,
    haste: generalHaste,
    basicAbilityHaste: generalHaste,
    ultimateAbilityHaste: generalHaste,
    summonerSpellHaste: 0,
    moveSpeed: atLevel("moveSpeed"),
    mana: atLevel("mana"),
    physicalPenFlat: 0,
    physicalPen: 0,
    magicPenFlat: 0,
    magicPen: 0,
    omnivamp: 0,
    physicalVamp: 0,
    magicVamp: 0,
    // Read from baseStats like every other level-scaling stat. It was a hard 0,
    // so a champion with innate tenacity (Kayn carries 3%) showed none until an
    // item or Perseverance granted some.
    tenacity: atLevel("tenacity"),
    healShieldPower: 0,
    manaRegen: atLevel("manaRegen"),
    hpRegen: atLevel("hpRegen"),
    itemCost: 0,
  };
  let attackSpeedPercent = 0;
  let moveSpeedPercent = 0;
  let manaRegenPercent = 0;
  let hpRegenPercent = 0;
  const adaptiveRules: ItemAlwaysRule[] = [];

  for (const slug of itemSlugs) {
    result.itemCost += ITEM_DETAILS.get(slug)?.cost ?? DATA.items[slug]?.cost ?? 0;
    const itemStats = ITEM_DETAILS.get(slug)?.stats ?? DATA.items[slug]?.stats ?? {};
    for (const [key, raw] of Object.entries(itemStats)) {
      const value = typeof raw === "number" ? raw : Number(raw.value ?? 0);
      const percent = typeof raw === "number" ? false : Boolean(raw.percent);
      if (!Number.isFinite(value)) continue;
      if (key === "attackSpeed" && percent) attackSpeedPercent += value;
      else if (key === "moveSpeed" && percent) moveSpeedPercent += value;
      else if (key === "manaRegen" && percent) manaRegenPercent += value;
      else if (key === "hpRegen" && percent) hpRegenPercent += value;
      else if (key === "abilityHaste") {
        result.haste += value;
        result.basicAbilityHaste += value;
        result.ultimateAbilityHaste += value;
      }
      else if (key in result) result[key as keyof ListedBuildStats] += value;
    }
    for (const rule of STAT_RULES.items[slug]?.always ?? []) {
      if (rule.stat === "adaptive") {
        adaptiveRules.push(rule);
      } else if (rule.stat === "moveSpeed" && rule.percent) {
        moveSpeedPercent += Number(rule.value ?? 0);
      } else if (rule.stat === "critDamage" && rule.set !== undefined) {
        result.critDamage = Math.max(result.critDamage, rule.set);
      } else if (rule.stat in result) {
        const key = rule.stat as keyof ListedBuildStats;
        if (rule.set !== undefined) result[key] = rule.set;
        else result[key] += Number(rule.value ?? 0);
      }
    }
    for (const [key, raw] of Object.entries(ITEM_DETAILS.get(slug)?.scopedStats ?? {})) {
      const value = typeof raw === "number" ? raw : Number(raw.value ?? 0);
      if (!Number.isFinite(value)) continue;
      if (key === "basicAbilityHaste") result.basicAbilityHaste += value;
      else if (key === "ultimateAbilityHaste") result.ultimateAbilityHaste += value;
      else if (key === "summonerSpellHaste") result.summonerSpellHaste += value;
    }
  }

  // Resolve adaptive stats after every item's printed stats are known so the
  // result cannot change just because boots were added before another item.
  for (const rule of adaptiveRules) {
    const bonusAd = Math.max(0, result.ad - atLevel("ad"));
    if (result.ap > bonusAd) result.ap += Number(rule.ap ?? 0);
    else result.ad += Number(rule.ad ?? 0);
  }

  // Only guaranteed, always-on rune stats belong in this transparent sheet.
  // Triggered and uptime-weighted rune values (for example Phase Rush) stay out.
  if (runeNames.includes("Transcendence")) {
    const transcendenceHaste = Number(DATA.runeEngine?.Transcendence?.hasteFlat ?? 10);
    result.haste += transcendenceHaste;
    result.basicAbilityHaste += transcendenceHaste;
    result.ultimateAbilityHaste += transcendenceHaste;
  }
  // Perseverance's tenacity is flat and unconditional; only its defensive half
  // (armor and MR while immobilised) is situational, and that stays out.
  if (runeNames.includes("Perseverance")) result.tenacity += 10;
  // Celerity is why a build's Move Speed reads low against the in-game sheet:
  // it gives 2% outright AND makes every other Move Speed bonus 7% more
  // effective. Both halves are always on, so both are applied below, where the
  // flat and percent totals are finally combined.
  const celerity = runeNames.includes("Celerity");

  for (const passive of verifiedChampion?.statRules?.passiveStats ?? []) {
    const learnedAt = champion.skillOrder?.[passive.slot] ?? [];
    const rank = learnedAt.filter((unlockLevel) => unlockLevel <= level).length;
    if (rank <= 0 || !(passive.stat in result)) continue;
    result[passive.stat as keyof ListedBuildStats] += passive.values[Math.min(rank - 1, passive.values.length - 1)] ?? 0;
  }

  const attackSpeedRatio = verifiedChampion?.statRules?.attackSpeedRatio
    ?? champion.baseStats?.attackSpeed?.base
    ?? result.attackSpeed;
  result.attackSpeed += attackSpeedRatio * attackSpeedPercent / 100;
  // Move Speed: base is untouched, bonuses stack additively, and the percent
  // total applies to the whole. Celerity amplifies the BONUSES only -- flat and
  // percent alike -- which is why the base is pulled back out here first.
  const baseMoveSpeed = atLevel("moveSpeed");
  let flatMoveSpeedBonus = result.moveSpeed - baseMoveSpeed;
  if (celerity) {
    moveSpeedPercent += 2;
    flatMoveSpeedBonus *= 1.07;
    moveSpeedPercent *= 1.07;
  }
  result.moveSpeed = (baseMoveSpeed + flatMoveSpeedBonus) * (1 + moveSpeedPercent / 100);
  result.manaRegen *= 1 + manaRegenPercent / 100;
  result.hpRegen *= 1 + hpRegenPercent / 100;
  result.physicalVamp += result.omnivamp;
  result.magicVamp += result.omnivamp;
  if (itemSlugs.includes("infinity-edge") && result.crit > 100) {
    result.critDamage += (result.crit - 100) * 0.6;
  }
  for (const key of Object.keys(result) as (keyof ListedBuildStats)[]) {
    result[key] = Math.round(result[key] * 100) / 100;
  }
  // The no-items sheet tells a bonus-scaling steroid what counts as bonus. It
  // is computed with ultActive false, so this recurses exactly once.
  return ultActive
    ? applyUltSteroids(result, name, level, listedBuildStats(name, [], level))
    : result;
}

export function conditionalBuildEffects(itemSlugs: string[]): ConditionalBuildEffect[] {
  return itemSlugs.flatMap((slug) => {
    const source = DATA.items[slug]?.name ?? slug;
    return (STAT_RULES.items[slug]?.conditional ?? []).map((effect) => ({ source, ...effect }));
  });
}

const ABILITY_STAT_LABELS: Record<string, string> = {
  ad: "AD",
  bonusAd: "bonus AD",
  ap: "AP",
  ownMaxHp: "max Health",
  ownBonusHp: "bonus Health",
  targetMaxHp: "target max Health",
  targetCurrentHp: "target current Health",
  targetMissingHp: "target missing Health",
  armor: "Armor",
  mr: "Magic Resist",
  moveSpeed: "Move Speed",
  bonusMs: "bonus Move Speed",
  attackSpeed: "Attack Speed",
};

const EFFECT_LABELS: Record<string, string> = {
  ad: "Attack Damage",
  ap: "Ability Power",
  armor: "Armor",
  mr: "Magic Resist",
  moveSpeed: "Move Speed",
  attackSpeed: "Attack Speed",
  heal: "Healing",
  shield: "Shield",
  damageReduction: "Damage reduction",
};

function rankValue(value: RankValue | undefined, rankIndex: number, level = 15): number {
  if (typeof value === "number") return value;
  if (value && !Array.isArray(value) && "lvlRange" in value) {
    const [lo, hi] = value.lvlRange;
    return lo + (hi - lo) * (Math.min(Math.max(level, 1), 15) - 1) / 14;
  }
  if (!Array.isArray(value) || value.length === 0) return 0;
  return Number(value[Math.min(Math.max(rankIndex, 0), value.length - 1)]) || 0;
}

function cleanNumber(value: number): number {
  return Math.round(value * 10) / 10;
}

function maxFormulaRank(formula: AbilityFormula | undefined): number {
  const lengths = [
    Array.isArray(formula?.cooldowns) ? formula.cooldowns.length : 0,
    ...(formula?.damage ?? []).flatMap((part) => [
      Array.isArray(part.base) ? part.base.length : 0,
      ...(part.ratios ?? []).map((ratio) => Array.isArray(ratio.pct) ? ratio.pct.length : 0),
    ]),
    ...(formula?.defensive ?? []).flatMap((part) => [
      Array.isArray(part.base) ? part.base.length : 0,
      Array.isArray(part.flat) ? part.flat.length : 0,
    ]),
    ...(formula?.steroids ?? []).flatMap((part) => [
      Array.isArray(part.pct) ? part.pct.length : 0,
      Array.isArray(part.flat) ? part.flat.length : 0,
    ]),
  ];
  return Math.max(1, ...lengths);
}

/**
 * Display-only ability calculator. It uses rank data plus unconditional build
 * stats and never assigns a build score or guesses a target/combat scenario.
 */
export function calculatedChampionAbilities(
  name: string,
  itemSlugs: string[],
  runeNames: string[] = [],
  level = 15,
  ultActive = false,
): CalculatedChampionAbility[] {
  // With the ult up, every ability's numbers change, because the buff feeds the
  // same AD/AP the ratios read from -- that is the whole point of showing it.
  const stats = listedBuildStats(name, itemSlugs, level, runeNames, ultActive);
  const baseStats = listedBuildStats(name, [], level, [], ultActive);
  const champion = DATA.champions[name];
  if (!stats || !baseStats || !champion) return [];
  const verifiedChampion = STAT_RULES.champions[name];

  const formulas = DATA.formulas[name]?.abilities ?? {};
  const details = championAbilities(name);
  const detailBySlot = new Map(details.map((ability) => [ability.slot, ability]));
  const slots = [...new Set([...details.map((ability) => ability.slot), ...Object.keys(formulas)])]
    .sort((left, right) => ["P", "1", "2", "3", "4"].indexOf(left) - ["P", "1", "2", "3", "4"].indexOf(right));
  const statSources: Record<string, number | undefined> = {
    ad: stats.ad,
    bonusAd: Math.max(0, stats.ad - baseStats.ad),
    ap: stats.ap,
    ownMaxHp: stats.hp,
    ownBonusHp: Math.max(0, stats.hp - baseStats.hp),
    armor: stats.armor,
    mr: stats.mr,
    moveSpeed: stats.moveSpeed,
    bonusMs: Math.max(0, stats.moveSpeed - baseStats.moveSpeed),
    attackSpeed: stats.attackSpeed,
    targetMaxHp: undefined,
    targetCurrentHp: undefined,
    targetMissingHp: undefined,
  };

  return slots.map((slot) => {
    const formula = formulas[slot];
    const detail = detailBySlot.get(slot);
    const learnedAt = champion.skillOrder?.[slot] ?? [];
    const fallbackMaxRank = slot === "4" ? 3 : 4;
    const maxRank = slot === "P" ? 1 : (learnedAt.length || Math.max(maxFormulaRank(formula), fallbackMaxRank));
    // Only two newly added champions currently lack a guide skill order. At
    // level 15 every ability is known to be max rank; below that, do not invent
    // an upgrade order the source does not provide.
    const rank = slot === "P" ? 1 : learnedAt.length
      ? learnedAt.filter((unlockLevel) => unlockLevel <= level).length
      : level >= 15 ? maxRank : 0;
    const unlockLevel = rank === 0 ? learnedAt[0] : undefined;
    const rankIndex = Math.max(0, rank - 1);
    const scrapedCooldowns = detail?.cooldowns.map(Number).filter(Number.isFinite) ?? [];
    const formulaCooldown = rankValue(formula?.cooldowns, rankIndex);
    const scrapedCooldown = rankValue(scrapedCooldowns, rankIndex);
    const baseCooldown = rank > 0 ? (formulaCooldown || scrapedCooldown || undefined) : undefined;
    const hasteUsed = slot === "4" ? stats.ultimateAbilityHaste : stats.basicAbilityHaste;
    const cooldown = baseCooldown && baseCooldown > 0
      ? cleanNumber(baseCooldown * 100 / (100 + Math.max(0, hasteUsed)))
      : undefined;
    const cooldownVariants = cooldown === undefined ? []
      : (verifiedChampion?.statRules?.cooldownVariants?.[slot] ?? []).map((variant) => ({
          label: variant.label,
          cooldown: cleanNumber(cooldown * variant.multiplier),
          note: variant.note,
        }));

    const damage: CalculatedAbilityDamage[] = rank === 0 ? [] : (formula?.damage ?? []).map((part) => {
      const base = rankValue(part.base, rankIndex, level);
      let amount = base;
      const breakdown = [String(cleanNumber(base))];
      const unresolved: string[] = [];
      for (const ratio of part.ratios ?? []) {
        const pct = rankValue(ratio.pct, rankIndex, level);
        const stat = statSources[ratio.stat];
        const label = ABILITY_STAT_LABELS[ratio.stat] ?? ratio.stat;
        if (typeof stat === "number") {
          const contribution = stat * pct / 100;
          amount += contribution;
          breakdown.push(`${cleanNumber(contribution)} (${cleanNumber(pct)}% ${label})`);
        } else {
          unresolved.push(`${cleanNumber(pct)}% ${label}`);
        }
      }
      const hits = Math.max(1, Math.round(rankValue(part.hits ?? 1, rankIndex, level)));
      const durationMultiplier = part.when === "dot total" && part.durationS ? part.durationS : 1;
      const totalMultiplier = hits * durationMultiplier;
      const context = [part.when, part.note, part.durationS ? `${part.durationS}s duration` : ""]
        .filter(Boolean).join(" · ");
      return {
        label: part.name ?? "Damage",
        type: part.type ?? "damage",
        amount: cleanNumber(amount),
        total: totalMultiplier > 1 ? cleanNumber(amount * totalMultiplier) : undefined,
        hits,
        breakdown: breakdown.join(" + "),
        unresolved,
        context: context || undefined,
      };
    });

    const effects: CalculatedAbilityEffect[] = [];
    if (rank > 0) {
      for (const part of formula?.defensive ?? []) {
        const kind = part.kind ?? part.stat ?? "Effect";
        const base = rankValue(part.base ?? part.flat, rankIndex, level);
        let amount = base;
        const unresolved: string[] = [];
        for (const ratio of part.ratios ?? []) {
          const pct = rankValue(ratio.pct, rankIndex, level);
          const stat = statSources[ratio.stat];
          if (typeof stat === "number") amount += stat * pct / 100;
          else unresolved.push(`${cleanNumber(pct)}% ${ABILITY_STAT_LABELS[ratio.stat] ?? ratio.stat}`);
        }
        if (part.when === "dot total" && part.durationS) amount *= part.durationS;
        if ((part.kind === "heal" || part.kind === "shield") && stats.healShieldPower) {
          amount *= 1 + stats.healShieldPower / 100;
        }
        const pieces = [];
        if (amount > 0) pieces.push(String(cleanNumber(amount)));
        pieces.push(...unresolved.map((term) => `+ ${term}`));
        effects.push({
          label: EFFECT_LABELS[kind] ?? kind,
          value: pieces.join(" ") || "Conditional",
          context: [part.when, part.note, part.durationS ? `${part.durationS}s duration` : "", part.unmodeled]
            .filter(Boolean).join(" · ") || undefined,
        });
      }
      for (const part of formula?.steroids ?? []) {
        const pct = rankValue(part.pct, rankIndex, level);
        const flat = rankValue(part.flat, rankIndex, level);
        const source = part.from ? statSources[part.from] : statSources[part.stat];
        const dynamicPct = pct + (part.pctFromStat && typeof statSources[part.from ?? ""] === "number"
          ? Number(statSources[part.from ?? ""]) * part.pctFromStat / 100
          : 0);
        const derived = part.from && typeof source === "number" ? source * dynamicPct / 100
          : !part.from && typeof source === "number" && dynamicPct ? source * dynamicPct / 100
          : 0;
        const values = [];
        if (flat) {
          const suffix = ["moveSpeed", "attackSpeed"].includes(part.stat) ? "%" : "";
          values.push(`+${cleanNumber(flat)}${suffix}`);
        }
        if (dynamicPct) values.push(`+${cleanNumber(dynamicPct)}%`);
        if (derived) values.push(`≈ +${cleanNumber(derived)} ${ABILITY_STAT_LABELS[part.stat] ?? part.stat}`);
        effects.push({
          label: EFFECT_LABELS[part.stat] ?? part.stat,
          value: values.join(" · ") || "Conditional",
          context: [part.from ? `from ${ABILITY_STAT_LABELS[part.from] ?? part.from}` : "", part.when, part.note, part.unmodeled]
            .filter(Boolean).join(" · ") || undefined,
        });
      }
    }

    return {
      slot,
      key: detail?.key ?? (slot === "P" ? "Passive" : ({ "1": "Q", "2": "W", "3": "E", "4": "R" }[slot] ?? slot)),
      name: formula?.name ?? detail?.name ?? slot,
      icon: detail?.icon ?? "",
      formIcons: detail?.formIcons,
      rank,
      maxRank,
      unlockLevel,
      baseCooldown: baseCooldown || undefined,
      cooldown,
      hasteUsed: baseCooldown ? hasteUsed : undefined,
      cooldownVariants,
      damage,
      effects,
      notes: formula?.unmodeled ?? [],
      fallbackText: !damage.length && !effects.length ? detail?.text : undefined,
    };
  });
}
