/**
 * Browser port of the deterministic fight engine (web/fight_engine.py).
 * Computes live metrics for CUSTOM builds when users swap items/runes.
 * Reads the same data both engines share (src/data/engine.json).
 */
import engineData from "@/data/engine.json";
import { scaledBuildStats } from "@/lib/build-scaling";
import type { BuildAnalysis } from "@/lib/builds";

/* eslint-disable @typescript-eslint/no-explicit-any */
const DATA = engineData as any;

const BASE_CRIT_MULT = 1.75;
const AS_CAP = 2.5;
const SPELLBLADE_CD = 1.5;
const CLEAVE_EVERY = 1.75;
const MELEE_AUTO_UPTIME = 0.75;
// A champion mid-fight is not at full health. The one assumption in the kit
// sustain model, and the same value fight_engine.py uses.
const MISSING_HP_IN_FIGHT = 0.4;

// ---- The ally model. An enchanter's entire job lives here, and none of it
// existed in this engine: eight ally* keys shipped in the data and were read by
// the Python engine only, so the TS side scored Soraka on her own damage and
// survival and every support item looked like a weak stat stick. Constants are
// fight_engine's, duplicated rather than exported because they are assumptions
// about a fight, not data about the game.
const SUPPORT_WINDOW = 8;
const ALLY_AUTOS = 8;              // buffed ally basic attacks in the window
const ALLY_DAMAGE = 2500;          // damage a buffed ally deals in the window
const ALLY_INCOMING = 2500;        // damage an ally takes in the window
const AP_TO_ALLY_DAMAGE = 2.5;
const AD_TO_ALLY_DAMAGE = 4.0;
const FONT_PROC_EVERY = 3.0;
/** Assumed seconds between procs for a rune that states no cadence. */
const RUNE_PROC_EVERY = 9.0;
/** Runes that pay nothing without an ally in range. */
const ALLY_GATED_RUNES = new Set(["Guardian", "Font of Life"]);
/** How much of a fight each lane spends beside an ally. */
const ALLY_UPTIME_BY_ROLE: Record<string, number> = {
  Support: 0.90, Dragon: 0.75, Jungle: 0.30, Baron: 0.25, Mid: 0.30,
};
const allyUptime = (name: string): number =>
  ALLY_UPTIME_BY_ROLE[String(DATA.champions[name]?.role ?? "")] ?? 0.35;
const RANGED_CLASSES = new Set(["Marksman", "Mage", "Enchanter"]);
const AUTO_GATED_RUNES = new Set(["Empowerment", "Lethal Tempo"]);
/** Champions whose ultimate is area damage; see data/ult_shape.json. */
const AOE_ULTS = new Set<string>((DATA.aoeUlts ?? []) as string[]);
const REF_BURST = 2400, REF_DPS = 700, REF_DEF = 7000;
const BURSTY = new Set(["oneshot", "burst", "poke", "crit"]);

// Gold efficiency model (mirrors Python fight_engine). Passive value is priced
// through the battle score, not here — a strong passive can still justify a
// stat-inefficient item. FinalScore = BattleScore * efficiency**ALPHA.
const STAT_GOLD: Record<string, number> = {
  ad: 35, ap: 21.75, abilityHaste: 26.7, hp: 2.67, armor: 20, mr: 20,
  attackSpeed: 30, crit: 40, magicPen: 41.7, physicalPen: 41.7, lethality: 50,
  mana: 1.4, moveSpeed: 13,
};
const EFFICIENCY_ALPHA = 0.5;

/** How much of each offensive stat a champion's kit can use (0..1), from its
 *  ability ratios and scaling — not its class. Mirrors Python stat_usability. */
function statUsability(name: string): Record<string, number> {
  const champ = DATA.champions[name] ?? {};
  const scales = new Set<string>(champ.scalesWith ?? []);
  const mechs = new Set<string>(champ.mechanics ?? []);
  const ratioStats = new Set<string>();
  for (const ab of Object.values<any>(DATA.formulas[name]?.abilities ?? {}))
    for (const c of ab.damage ?? [])
      for (const r of c.ratios ?? []) ratioStats.add(r.stat);
  const hasAp = ratioStats.has("ap") || scales.has("ap");
  const hasAd = ratioStats.has("ad") || ratioStats.has("bonusAd") || scales.has("ad") || scales.has("bonusAd");
  const autos = scales.has("attackSpeed") || mechs.has("onHit") || champ.primaryDamage === "physical";
  const apUse = hasAp ? 1 : 0.05;
  const adUse = hasAd ? 1 : autos ? 0.35 : 0.05;
  const asUse = autos ? 1 : 0.15;
  const critUse = autos && (hasAd || scales.has("crit") || champ.primaryDamage === "physical") ? 1 : 0;
  return { ad: adUse, ap: apUse, attackSpeed: asUse, crit: critUse, magicPen: apUse, physicalPen: adUse, lethality: adUse };
}

/** Per-champion usefulness (0..1) of every item stat, for gold efficiency. */
/** (needs_mobility, has_dash). Short-range / committed champs — any melee, plus
 *  auto-attack marksmen like Graves/Lucian — need MS to reposition and stick;
 *  ranged casters keep their distance. Mirrors Python _mobility_profile. */
function mobilityProfile(name: string): [boolean, boolean] {
  const champ = DATA.champions[name] ?? {};
  const mechs = new Set<string>(champ.mechanics ?? []);
  const cls = champ.class ?? "";
  const melee = !RANGED_CLASSES.has(cls);
  const autoMarksman = cls === "Marksman" || mechs.has("onHit") || (champ.scalesWith ?? []).includes("attackSpeed");
  const rangedCaster = cls === "Mage" || cls === "Enchanter";
  return [(melee || autoMarksman) && !rangedCaster, mechs.has("dash")];
}

function statWeights(name: string): Record<string, number> {
  const u = statUsability(name);
  const noResource = (DATA.formulas[name]?.mechanics ?? []).some((m: any) => m.kind === "noResource");
  const [mobile, hasDash] = mobilityProfile(name);
  let hasteW = hasDash ? 0.9 : 0.85;
  let manaW = noResource ? 0 : 0.35;
  // Behaviour model (A3): high spell-cast champs value ability haste and mana
  // more (Manamune/Shojin on Hecarim). Emergent from the metric, no rule.
  const cast = DATA.formulas[name]?.behavior?.spellCastRate;
  if (typeof cast === "number") {
    hasteW = Math.min(1, hasteW + 0.15 * (cast - 0.5));
    if (!noResource) manaW = Math.min(0.7, manaW + 0.5 * Math.max(0, cast - 0.4));
  }
  return {
    ad: u.ad, ap: u.ap, attackSpeed: u.attackSpeed, crit: u.crit,
    magicPen: u.ap, physicalPen: u.ad, lethality: u.ad,
    abilityHaste: hasteW, hp: 0.8, armor: 0.75, mr: 0.75,
    mana: manaW, moveSpeed: mobile ? 0.75 : 0.45,
  };
}

/** Fraction of a build's raw-stat gold that the champion's kit can use. */
function buildEfficiency(name: string, itemSlugs: string[]): number {
  const w = statWeights(name);
  let useful = 0, total = 0;
  for (const s of itemSlugs) {
    const stats = DATA.items[s]?.stats ?? {};
    for (const k of Object.keys(stats)) {
      if (STAT_GOLD[k] == null) continue;
      const v = stats[k]?.value ?? stats[k] ?? 0;
      const gold = STAT_GOLD[k] * v;
      total += gold;
      useful += gold * (w[k] ?? 0.5);
    }
  }
  return total > 0 ? useful / total : 1;
}
const VARIANT_WEIGHTS: Record<string, [number, number]> = {
  oneshot: [0.85, 0.15], burst: [0.8, 0.2], damage: [0.7, 0.3],
  crit: [0.7, 0.3], poke: [0.7, 0.3], battlemage: [0.55, 0.45],
  balanced: [0.55, 0.45], tanky: [0.3, 0.7], utility: [0.25, 0.75],
};

/**
 * A discrete hit: keystone procs, item actives, first-hit bonuses, %max-HP
 * strikes. Anything that fires on its own clock instead of riding autos.
 *
 * These used to live in four separate fields (burstProcs, runeProcs, firstHit,
 * procMaxHpPct) and every one of them was charged EXACTLY ONCE per fight, no
 * matter how long the fight ran. Aery, which can re-proc every 2 seconds, was
 * therefore worth the same as Dark Harvest on its 20-second cooldown, and a
 * 20-second fight paid for neither of them more than a 2-second one did.
 * Measured on Zed: adding Electrocute moved rotation damage by +143 at a 2s
 * window and by exactly +143 at 20s.
 *
 * `cd` is the cooldown the effect's own description states; Infinity means
 * once per fight, which is both the correct answer for the effects whose text
 * states no repeat (Empowerment lasts "until you exit combat") and the default
 * for anything with no evidence either way -- so nothing moves without a
 * quoted source.
 */
export interface Proc {
  flat: number;
  /** Fractions, not percents: 0.10 means 10% bonus AD. */
  adRatio: number;
  apRatio: number;
  /** Fraction of the TARGET's max health. */
  pctMaxHp: number;
  /** physical | magic | true | adaptive */
  type: string;
  /** Seconds between procs; Infinity == once per fight. */
  cd: number;
  /** Seconds of build-up before the first one can land. */
  arm: number;
  /** 0 = unconditional. 0.5 = target must be under half health. */
  need: number;
  label: string;
}

export interface LiveMetrics {
  burst3: number; dps8: number; ttk: number | null; ehp: number; sustain: number;
  score: number; ad: number; ap: number; hp: number; armor: number; mr: number;
  moveSpeed: number; attackSpeed: number; haste: number; crit: number; mana: number;
}

export interface AttackStyleLive {
  style: "basic-attack" | "ability-caster" | "hybrid";
  autoness: number;
  measuredAutoShare: number;
  asEfficiency: number | null;
  dataQuality: string;
  buildHint: string;
}

const lvlRange = (v: any, level: number): number => {
  if (v && typeof v === "object" && "lvlRange" in v) {
    const [lo, hi] = v.lvlRange;
    return lo + (hi - lo) * (level - 1) / 14;
  }
  return Number(v) || 0;
};
const rankVal = (arr: any, rank: number): number => {
  if (typeof arr === "number") return arr;
  // A per-level range read where no level is in scope (hit counts, cooldowns):
  // take the level-15 end rather than returning nothing.
  if (arr && typeof arr === "object" && "lvlRange" in arr) return Number(arr.lvlRange.at(-1)) || 0;
  if (!Array.isArray(arr) || !arr.length) return 0;
  return Number(arr[Math.min(rank, arr.length - 1)]) || 0;
};
// A formula number: flat, per-ability-rank, or per-CHAMPION-level. Extraction
// writes level-scaling values ("8 - 36 bonus magic damage") as {lvlRange:[lo,hi]}.
const scaleVal = (v: any, rank: number, level: number): number =>
  v && typeof v === "object" && "lvlRange" in v ? lvlRange(v, level) : rankVal(v, rank);

function targetSquishy(level: number) {
  const c = DATA.champions["Ashe"];
  const v = (k: string, d: number) => {
    const s = c?.baseStats?.[k];
    return s ? s.base + s.perLevel * (level - 1) : d;
  };
  return c
    ? { hp: v("hp", 2200), armor: v("armor", 85), mr: v("mr", 45), bonusHp: 0 }
    : { hp: 2200, armor: 85, mr: 45, bonusHp: 0 };
}
const TARGET_BRUISER = { hp: 3400, armor: 130, mr: 85, bonusHp: 1700 };

function kitAdjust(name: string): number {
  // precomputed in Python (scans full ability text) and shipped in the bundle
  return DATA.champions[name]?.kitShift ?? 0;
}

export function resolveStats(name: string, level: number, itemSlugs: string[],
                             runeNames: string[]): any {
  const c = DATA.champions[name];
  if (!c) return null;
  const bs = c.baseStats ?? {};
  const base = (k: string, d = 0) => (bs[k] ? bs[k].base + bs[k].perLevel * (level - 1) : d);

  const st: any = {
    baseAd: base("ad", 60), bonusAd: 0, ap: 0,
    hp: base("hp", 1800), bonusHp: 0,
    armor: base("armor", 60), mr: base("mr", 45),
    // The RATIO percentage bonuses multiply, not the level-1 display value.
    baseAsPct: 0, baseAs: c.asRatio || bs.attackSpeed?.base || 0.75,
    // Real base mana from the champion's stat line (Python parity): mana
    // feeds the AD/AP/HP-from-mana conversions, so a flat assumption
    // short-changed every Manamune/Archangel's/Winter's build.
    crit: 0, critMult: BASE_CRIT_MULT, critDisabled: 0, haste: 0, mana: base("mana", 0),
    flatPen: 0, pctPenFactors: [] as number[], flatMagicPen: 0, pctMagicPen: 0,
    baseMs: bs.moveSpeed?.base || 330, bonusMs: 0, tenacity: 0,
    abilityAmp: 0, damageAmp: 0, giant: 0, execute: 0, ultAmp: 0,
    spellbladeBaseAdPct: 0, spellbladePctMaxHp: 0,
    onHitPhys: 0, onHitMagic: 0, onHitPctCurrentHp: 0, onHitPctMaxHp: 0,
    procs: [] as Proc[], dotDps: 0, dotPctMaxHp: 0,
    armorShred: 0, vamp: 0, healOnHit: 0, apAmp: 0,
    mrShred: 0, mrShredFlat: 0, spellbladeApPct: 0, spellbladeMagic: 0,
    extraOnHitApplications: 0,
    critDamagePerExcessCrit: 0, hastePct: 0, cdRefundPctPerAuto: 0,
    cleaveFlat: 0, cleavePctBonusHp: 0,
    shield: 0, shieldPctBonusHp: 0, shieldPctMaxHp: 0, dr: 0,
    healShieldAmp: 0, runeHealPerSec: 0, graspPct: 0, graspEvery: 5,
    runeAllyHealPerSec: 0, allyShield: 0, autoBonusPct: 0,
    extraBolts: 0, extraBoltAdPct: 0, targetSlow: 0, itemHaste: 0,
    // Carried BY THIS BUILD and applied to whoever it is fighting.
    grievousWounds: 0, shieldCut: 0, ccRemoval: 0, stasisSec: 0,
    drMagic: 0, drPhys: 0,
    cloneAdPct: 0, cloneAsFromCritPct: 0, cloneLifetimeS: 0, cloneMaxCount: 0,
    // Carried by this build and applied to whoever is fighting IT. They reach
    // the damage path through championTarget, not from here.
    basicAttackDr: 0, targetAsSlow: 0,
    // Set by duel() from the target's own build; 1 means untouched.
    externalAsMult: 1, autoDamageMult: 1,
    lifestealPct: 0, omnivampPct: 0,
    runeOnHitFlat: 0,
  };

  // AD/AP/HP-from-mana percentages, applied after runes (see below): runes add
  // mana (Manaflow Band's 300), and a resourceless kit zeroes it later still.
  const manaConv = { ad: 0, ap: 0, hp: 0 };
  // Attack-rate estimate for stack ramp-up, from the build's own AS items.
  // Deliberately rough (ignores runes and AS passives): it only decides how
  // fast stacking items reach max, a second-order effect.
  const asPctFromItems = itemSlugs.reduce(
    (sum, s) => sum + Number(DATA.items[s]?.stats?.attackSpeed?.value ?? 0), 0);
  const atkRate = Math.min(AS_CAP, (bs.attackSpeed?.base || 0.75) * (1 + asPctFromItems / 100));
  const rngd = RANGED_CLASSES.has(c.class ?? "");
  const prefersAp = c.primaryDamage
    ? c.primaryDamage === "magic"
    : (c.scalesWith ?? []).includes("ap") && !(c.scalesWith ?? []).includes("ad");
  // Adaptive on-hits (Nashor's Gnaw): the amount scales with FINAL AD/AP, so
  // accumulation is deferred until every stat source (Overkill included) has
  // landed; the damage TYPE follows the kit like the adaptive stat grant.
  const adaptiveOnHit = { flat: 0, adPct: 0, apPct: 0 };
  const addProc = (e: Partial<Proc>) => {
    const flat = e.flat ?? 0, adRatio = e.adRatio ?? 0;
    const apRatio = e.apRatio ?? 0, pctMaxHp = e.pctMaxHp ?? 0;
    if (!flat && !adRatio && !apRatio && !pctMaxHp) return;
    st.procs.push({
      flat, adRatio, apRatio, pctMaxHp,
      type: e.type ?? "magic",
      // A missing or zero cooldown means "no repeat stated", which is charged
      // once per fight -- exactly what the engine did before this existed.
      cd: e.cd && e.cd > 0 ? e.cd : Infinity,
      arm: e.arm ?? 0, need: e.need ?? 0, label: e.label ?? "",
    });
  };
  // Crit-GATED increments (Last Whisper's "+6% Armor Penetration on Critical
  // Strike", Bloody's "+4% Physical Vamp on Critical Strike"). Deferred like the
  // adaptive on-hits above, because crit is still accumulating inside the item
  // loop: applying them inline would price them against whatever crit the
  // earlier items happened to have contributed.
  const onCrit = { pctPen: 0, physVampPct: 0 };

  for (const slug of itemSlugs) {
    const it = DATA.items[slug];
    if (!it) continue;
    for (const [k, v] of Object.entries<any>(it.stats ?? {})) {
      const val = v.value, pct = v.percent;
      if (k === "ad") st.bonusAd += val;
      else if (k === "ap") st.ap += val;
      else if (k === "hp") { st.hp += val; st.bonusHp += val; }
      else if (k === "armor") st.armor += val;
      else if (k === "mr") st.mr += val;
      else if (k === "attackSpeed") st.baseAsPct += val;
      else if (k === "crit") st.crit += val / 100;
      else if (k === "abilityHaste") st.haste += val;
      else if (k === "mana") st.mana += val;
      else if (k === "magicPen") {
        if (pct) st.pctMagicPen = 1 - (1 - st.pctMagicPen) * (1 - val / 100);
        else st.flatMagicPen += val;
      } else if (k === "magicPenFlat") st.flatMagicPen += val;
      else if (k === "physicalPen") {
        // PERCENT penetration is multiplicative against armour; FLAT subtracts.
        // Both used to land in flatPen, so Lord Dominik's "36%" was charged as
        // 36 lethality -- worth roughly triple against a 100-armour target and
        // nothing at all against a naked one. Python fixed this; the port did not.
        if (pct) st.pctPenFactors.push(val / 100);
        else st.flatPen += val;
      } else if (k === "physicalPenFlat") st.flatPen += val;
      else if (k === "physicalVamp") { st.vamp += val / 100; st.lifestealPct += val / 100; }
      else if (k === "omnivamp") { st.vamp += val / 100; st.omnivampPct += val / 100; }
      else if (k === "healShieldPower") st.healShieldAmp += val / 100;
      // Tenacity is always a percentage, but the two items that carry it disagree
      // on the flag -- Mercury's Treads is percent:false and Chainlaced Crushers
      // percent:true, both meaning 30%. So the flag is deliberately ignored here.
      else if (k === "tenacity") st.tenacity = 1 - (1 - st.tenacity) * (1 - val / 100);
      else if (k === "moveSpeed") st.bonusMs += pct ? st.baseMs * val / 100 : val;
      // manaRegen and hpRegen are read and dropped on purpose: a duel has no
      // out-of-combat regeneration channel, so they would be dead weight.
    }
    let fx = DATA.itemFx[slug] ?? {};
    // STACK RAMP-UP: attack-stacked effects (Terminus' pen, Guinsoo's AS,
    // Cleaver's shred) are not there from second zero. Scale the stack-built
    // keys by the average stack fraction over the 8s window at this build's
    // attack rate; always-on parts are untouched. Mirrors the Python engine.
    if (fx.rampAttacks) {
      const tau = Number(fx.rampAttacks) / Math.max(atkRate, 0.1);
      const ramp = Math.max(0.35, Math.min(1, tau <= 8 ? 1 - tau / 16 : 4 / tau));
      const scaled: any = { ...fx };
      for (const k of ["pctPen", "mrShredPct", "armorShredPct", "asPctPassive"]) {
        const v = fx[k];
        if (typeof v === "number") scaled[k] = v * ramp;
        else if (v && typeof v === "object" && "lvlRange" in v)
          scaled[k] = { lvlRange: v.lvlRange.map((x: number) => x * ramp) };
      }
      fx = scaled;
    }
    const g = (k: string) => (k in fx ? lvlRange(fx[k], level) : 0);
    st.flatPen += g("flatPen");
    if (fx.pctPen) st.pctPenFactors.push(g("pctPen") / 100);
    onCrit.pctPen += g("pctPenOnCrit");
    onCrit.physVampPct += g("physVampPctOnCrit");
    st.armorShred = Math.max(st.armorShred, g("armorShredPct") / 100);
    st.critMult = Math.max(st.critMult, Number(fx.critMult) || 0);
    if (fx.disablesCrit) st.critDisabled = 1;
    st.abilityAmp += g("abilityAmpPct") / 100;
    st.damageAmp += g("damageAmpPct") / 100;
    st.giant = Math.max(st.giant, g("giantSlayerPct") / 100);
    st.execute = Math.max(st.execute, g("executePct") / 100);
    st.spellbladeBaseAdPct = Math.max(st.spellbladeBaseAdPct, g("spellbladeBaseAdPct"));
    // Divine Sunderer pays ranged champions 7%, not the melee 10%.
    st.spellbladePctMaxHp = Math.max(st.spellbladePctMaxHp,
      rngd && fx.spellbladePctMaxHpRanged ? g("spellbladePctMaxHpRanged") : g("spellbladePctMaxHp"));
    // Lich Bane is "75% base AD + 45% AP" and deals MAGIC damage; the AP half
    // and the damage type were dropped by the port. spellbladeMagic is stamped
    // at export time from the item's own passive text.
    st.spellbladeApPct = Math.max(st.spellbladeApPct, g("spellbladeApPct"));
    // Dusk and Dawn's second clause: "apply on-hits to the target 1 additional
    // time", on the same spellblade proc. Worth more than its small spellblade
    // half to an on-hit build, and invisible before this key existed.
    st.extraOnHitApplications = Math.max(st.extraOnHitApplications,
      g("extraOnHitOnSpellblade"));
    // Runaan's Hurricane. The bolts hit OTHER targets, so they are tracked
    // separately and never added to single-target damage, exactly as the
    // Python engine does. The TS side had no channel, so the site could not
    // report area damage for any build.
    st.extraBolts = Math.max(st.extraBolts, g("extraBolts"));
    st.extraBoltAdPct = Math.max(st.extraBoltAdPct, g("extraBoltAdPct"));
    // Rylai's: a slow on the target is relative move speed for the one thing
    // this engine models about positioning, a melee sticking to its target.
    // Damage is deliberately untouched.
    st.targetSlow = Math.max(st.targetSlow,
      g("targetSlowPct") / 100 * (g("targetSlowUptime") || 100) / 100);
    if ((fx.spellbladeBaseAdPct || fx.spellbladeApPct) && fx.spellbladeMagic)
      st.spellbladeMagic = 1;
    st.onHitPhys += g("onHitFlatPhys");
    st.onHitMagic += g("onHitFlatMagic");
    // Wild Rift %HP on-hits pay ranged champions less (BotRK: 10% melee, 8.5%
    // ranged); prefer the "...Ranged" companion key where the item has one.
    st.onHitPctCurrentHp += (rngd && fx.onHitPctCurrentHpRanged
      ? g("onHitPctCurrentHpRanged") : g("onHitPctCurrentHp")) / 100;
    st.onHitPctMaxHp += (rngd && fx.onHitPctMaxHpRanged
      ? g("onHitPctMaxHpRanged") : g("onHitPctMaxHp")) / 100;
    addProc({ pctMaxHp: g("procMaxHpPct") / 100, label: slug,
              type: fx.procMaxHpType ?? "physical",
              cd: g("procMaxHpCdSec"), arm: g("procMaxHpArmSec") });
    addProc({ flat: g("firstHit"), label: slug, type: "physical",
              cd: g("firstHitCdSec"), arm: g("firstHitArmSec") });
    addProc({ flat: g("burstProcFlat"), apRatio: g("burstProcApPct") / 100,
              label: slug, type: fx.burstProcType ?? "magic",
              cd: g("burstProcCdSec"), arm: g("burstProcArmSec") });
    st.dotDps += g("dotDps");
    // %max-HP burns (Searing Crown) are target-scaled, so they are summed
    // here and priced at fight time. Ranged users pay the reduced rate.
    st.dotPctMaxHp += g(rngd && fx.dotPctMaxHpPerSecRanged
      ? "dotPctMaxHpPerSecRanged" : "dotPctMaxHpPerSec") / 100;
    if (fx.adaptiveOnHitFlat || fx.adaptiveOnHitBonusAdPct || fx.adaptiveOnHitApPct) {
      adaptiveOnHit.flat += g("adaptiveOnHitFlat");
      adaptiveOnHit.adPct += g("adaptiveOnHitBonusAdPct") / 100;
      adaptiveOnHit.apPct += g("adaptiveOnHitApPct") / 100;
    }
    st.vamp += (g("physVampPct") + g("omnivampPct") + g("lifestealPct")) / 100;
    st.lifestealPct += (g("physVampPct") + g("lifestealPct")) / 100;
    st.omnivampPct += g("omnivampPct") / 100;
    st.healOnHit += g("healOnHitFlat");
    st.shield += g("shieldFlat");
    st.shieldPctBonusHp += g("shieldPctBonusHp") / 100;
    st.shieldPctMaxHp += g("shieldPctMaxHp") / 100;
    // A revive is, for EHP purposes, a shield worth X% of max HP: they have
    // to kill you twice.
    st.shieldPctMaxHp += g("reviveHpPct") / 100;
    // Attack speed granted by a PASSIVE rather than the stat line (Guinsoo's
    // 32%, Youmuu's 25%): the port had no channel for it at all.
    st.baseAsPct += g("asPctPassive");
    st.critDamagePerExcessCrit += g("critDamagePerExcessCrit");
    // "Every Nth attack deals ..." (Hullbreaker, Kraken Slayer). NOT an
    // on-hit: it fires once per N autos, so it is averaged across attacks,
    // scaled by the ranged multiplier where the item has one.
    const nth = g("everyNthAttack");
    if (nth >= 2) {
      const nthMult = rngd && fx.everyNthRangedMult ? g("everyNthRangedMult") / 100 : 1;
      st.onHitPhys += g("everyNthBaseAdPct") / 100 * st.baseAd * nthMult / nth;
      st.onHitPctMaxHp += g("everyNthPctMaxHp") / 100 * nthMult / nth;
      // Flat every-Nth damage (Kraken Slayer's "Every third attack deals
      // 120-160"). There was no channel for it, so the whole value sat on the
      // once-per-fight proc list and a core marksman item paid out once in a
      // twenty-second fight instead of about seven times. Ranged users have
      // their own stated number rather than a multiplier.
      // NOT modelled: Kraken's "increased by 1% per 1% Health the target is
      // missing, up to 70%". Average missing health is not available here and
      // assuming a value would be a guess, so this is the floor of the item.
      st.onHitPhys += (rngd && fx.everyNthRangedFlat
        ? g("everyNthRangedFlat") : g("everyNthFlat")) / nth;
    }
    st.dr = Math.max(st.dr, g("drPct") / 100);
    // TYPED damage reduction. Force of Nature reduces incoming MAGIC damage
    // only; charging it through the all-damage channel would roughly double
    // its worth against a mixed enemy team.
    st.drMagic = Math.max(st.drMagic, g("drMagicPct") / 100);
    st.drPhys = Math.max(st.drPhys, g("drPhysPct") / 100);
    // "Gain 25 Attack Damage OR 50 Ability Power (Adaptive)" grants exactly
    // ONE, picked by the kit's primary damage type -- mirrors the Python
    // engine's _prefers_ap. Nashor's Tooth carried its whole AP grant here
    // and the TS port dropped it, so AP builds undervalued the item.
    if (fx.adaptiveAdFlat || fx.adaptiveApFlat) {
      if (prefersAp) st.ap += g("adaptiveApFlat");
      else st.bonusAd += g("adaptiveAdFlat");
    }
    // Rabadon's "Overkill": accumulated here, applied to TOTAL AP after
    // every other AP source has landed.
    st.apAmp += g("apAmpPct") / 100;
    st.bonusAd += g("adFlatPassive");
    st.ap += g("apFlatPassive");
    st.haste += g("hasteFlatPassive");
    st.hp += g("hpFlatPassive"); st.bonusHp += g("hpFlatPassive");
    st.bonusMs += g("msFlat") + st.baseMs * g("msPct") / 100;
    // Mana conversions are DEFERRED, not applied here: runes add mana after
    // this loop, and a resourceless kit zeroes it later still.
    manaConv.ad += g("adFromManaPct");
    manaConv.ap += g("apFromManaPct");
    manaConv.hp += g("hpFromManaPct");
    st.ap += g("apFromBonusHpPct") / 100 * st.bonusHp;
    // MR shred mirrors armour shred (Abyssal Mask, Bloodletter's Curse).
    st.mrShred = Math.max(st.mrShred, g("mrShredPct") / 100);
    st.mrShredFlat += g("mrShredFlat");
    // Percent resists from a PASSIVE (Amaranth's Endurance at average
    // in-combat stacks; the override stores the pre-averaged value).
    st.armor *= 1 + g("armorPctPassive") / 100;
    st.mr *= 1 + g("mrPctPassive") / 100;
    st.hastePct += g("hastePctPassive") / 100;
    st.cdRefundPctPerAuto += g("cdRefundPctPerAuto");
    st.cleaveFlat += g("cleaveFlat");
    st.cleavePctBonusHp += g("cleavePctBonusHp") / 100;
    st.healShieldAmp += g("healShieldAmpPct") / 100;
    // These four had no reader at all. grievousWoundsPct has been exported on
    // five items since anti-heal went in and was consumed by nothing, so the
    // Counter Builder recommended Morellonomicon and then scored it with an
    // engine that could not see healing. None of the four stack in this game,
    // so they take the best value rather than summing.
    st.grievousWounds = Math.max(st.grievousWounds, g("grievousWoundsPct") / 100);
    st.shieldCut = Math.max(st.shieldCut, g("shieldCutPct") / 100);
    st.basicAttackDr = Math.max(st.basicAttackDr, g("basicAttackDrPct") / 100);
    st.targetAsSlow = Math.max(st.targetAsSlow, g("targetAsSlowPct") / 100);
    // Spell shields and cleanses: how many instances of lockdown this build can
    // shrug off in a fight. These DO stack -- two spell shields block two
    // abilities -- so unlike the four above they sum.
    st.ccRemoval += g("ccRemoval");
    st.cloneAdPct = Math.max(st.cloneAdPct, g("cloneAdPct"));
    st.cloneAsFromCritPct = Math.max(st.cloneAsFromCritPct, g("cloneAsFromCritPct"));
    st.cloneLifetimeS = Math.max(st.cloneLifetimeS, g("cloneLifetimeS"));
    st.cloneMaxCount = Math.max(st.cloneMaxCount, g("cloneMaxCount"));
    // Their own stasis, which is time the person fighting THEM cannot deal
    // damage. Read off the target's build, not the attacker's.
    st.stasisSec = Math.max(st.stasisSec, g("stasisSec"));
  }

  // runes
  const mech: string[] = c.mechanics ?? [];
  const autoCentric = c.class === "Marksman" || mech.includes("onHit");
  let msAmp = 0;
  // Rune on-hit RATIOS, deferred: bonus AD and AP are still accumulating
  // inside this loop, so pricing them here would charge whatever happened
  // to have landed so far. Mirrors fight_engine's ragg.
  const runeOnHit = { adRatio: 0, apRatio: 0 };
  const ks = DATA.runeFx.keystones ?? {}, mn = DATA.runeFx.minors ?? {};
  for (const rn of runeNames) {
    const r = ks[rn] ?? mn[rn];
    if (!r) {
      let fx = DATA.runeEngine[rn] ?? {};
      // Ally-gated runes pay out only with an ally in range. Scaled before any
      // key is read, so every part of the rune is discounted together.
      if (ALLY_GATED_RUNES.has(rn)) {
        const up = allyUptime(name);
        const scaled: any = {};
        for (const [k, v] of Object.entries<any>(fx)) {
          if (v && typeof v === "object" && "lvlRange" in v)
            scaled[k] = { lvlRange: v.lvlRange.map((x: number) => x * up) };
          else if (typeof v === "number") scaled[k] = v * up;
          else scaled[k] = v;
        }
        fx = scaled;
      }
      if (AUTO_GATED_RUNES.has(rn) && !autoCentric) {
        const scaled: any = {};
        for (const [k, v] of Object.entries<any>(fx)) {
          if (v && typeof v === "object" && "lvlRange" in v)
            scaled[k] = { lvlRange: v.lvlRange.map((x: number) => x * 0.45) };
          else if (typeof v === "number") scaled[k] = v * 0.45;
          else scaled[k] = v;
        }
        fx = scaled;
      }
      const g = (k: string) => (k in fx ? lvlRange(fx[k], level) : 0);
      const aAd = g("adaptiveAd"), aAp = g("adaptiveAp");
      if (aAd || aAp) {
        if (st.ap >= st.bonusAd) st.ap += aAp; else st.bonusAd += aAd;
      }
      st.bonusAd += g("bonusAd");
      st.ap += g("bonusAp");
      st.haste += g("hasteFlat");
      st.hp += g("hpFlat"); st.bonusHp += g("hpFlat");
      // Mana is not a dead stat: it feeds the AD/AP-from-mana conversions
      // (Muramana, Archangel's). Manaflow Band's 300 was being dropped.
      st.mana += g("manaFlat");
      st.armor += g("armorFlat");
      st.mr += g("mrFlat");
      // Legend: Tenacity shipped as an empty {} and never reached the bundle at
      // all, so the rune the advisor picks against heavy-CC comps did nothing.
      st.tenacity = 1 - (1 - st.tenacity) * (1 - g("tenacityPct") / 100);
      st.armor *= 1 + g("armorPct") / 100;
      st.mr *= 1 + g("mrPct") / 100;
      st.abilityAmp += g("abilityAmpPct") / 100;
      // Axiom Arcanist: "Your ultimate ability has 10% increased damage ... (AoE
      // damage is reduced to a 5% increase)". Which rate applies depends on the
      // champion's own ult, so it is picked from the exported ult_shape list.
      // Python has modelled this since the rune was written; the port had no
      // ult-amp channel at all, so the keystone was worth nothing here.
      st.ultAmp += (AOE_ULTS.has(name) ? g("ultAmpPctAoe") : g("ultAmpPct")) / 100;
      st.runeOnHitFlat += g("onHitFlat");
      // Brutal reads "5 (+6% Bonus Attack Damage + 3% Ability Power)". Both
      // engines charged the flat 5 and dropped both ratios, so the rune was
      // worth a fifth of itself on a fed carry.
      runeOnHit.adRatio += g("onHitAdRatio") / 100;
      runeOnHit.apRatio += g("onHitApRatio") / 100;
      // Ingenious Hunter is a RUNE, so its ITEM haste is read here.
      st.itemHaste += g("itemHasteFlat");
      // Font of Life: a self+ally heal. Both halves were dropped.
      const fontHeal = g("healPctMaxHp") / 100 * st.hp + g("healApRatio") / 100 * st.ap;
      st.runeHealPerSec += fontHeal / FONT_PROC_EVERY;
      st.runeAllyHealPerSec += (g("allyHealPctMaxHp") / 100 * st.hp
        + g("healApRatio") / 100 * st.ap) / FONT_PROC_EVERY;
      // Fleet Footwork. Assumed once per 9 seconds, the convention the curated
      // healPerProc key uses; the rune states no cadence. Read by neither
      // engine before this, so the keystone's whole point was worth nothing.
      st.runeHealPerSec += g("healFlat") / RUNE_PROC_EVERY;
      // Guardian shields YOU and the ally, and neither half was applied, so the
      // keystone's entire effect was dropped. Bonus HP and max HP are different
      // scalings: it reads "+6% BONUS Health", and charging it off max HP
      // nearly doubles the shield.
      const runeShield = g("shieldFlat")
        + g("shieldPctMaxHp") / 100 * st.hp
        + g("shieldPctBonusHp") / 100 * st.bonusHp
        + g("shieldApRatio") / 100 * st.ap;
      st.shield += runeShield;
      st.allyShield += g("allyShieldFlat")
        + (g("allyShieldFlat") ? runeShield - g("shieldFlat") : 0);
      st.damageAmp += g("ampPct") / 100;
      if (fx.burstProcFlat || fx.burstProcApRatio || fx.burstProcAdRatio)
        addProc({
          flat: g("burstProcFlat"),
          adRatio: g("burstProcAdRatio") / 100,
          // AP scaling was being dropped outright: six generated entries carry
          // burstProcApRatio and no engine has ever read it, so every AP build
          // undervalued Aery, Arcane Comet, Tyrant and Chain Assault.
          apRatio: g("burstProcApRatio") / 100,
          type: fx.burstProcType ?? "magic", label: rn,
          cd: g("burstProcCdSec"), arm: g("burstProcArmSec"),
        });
      continue;
    }
    const gate = AUTO_GATED_RUNES.has(rn) && !autoCentric ? 0.45 : 1;
    st.bonusMs += st.baseMs * (r.msPctAvg ?? 0) / 100;
    st.haste += r.hasteFlat ?? 0;
    msAmp += (r.msAmpPct ?? 0) / 100;
    st.baseAsPct += (r.asPctAvg ?? 0) * gate;
    st.hp += r.hpFlat ?? 0; st.bonusHp += r.hpFlat ?? 0;
    st.dr = Math.max(st.dr, (r.drPct ?? 0) / 100);
    st.healShieldAmp += (r.healShieldAmpPct ?? 0) / 100;
    st.runeHealPerSec += (r.healPerSec ?? 0) + (r.healPerProc ?? 0) / 9;
    if (r.procTargetMaxHpPct) { st.graspPct += r.procTargetMaxHpPct; st.graspEvery = r.procEverySec ?? 5; }
    if (r.bonusAdPerStackRange) {
      const [lo, hi] = r.bonusAdPerStackRange;
      st.bonusAd += (lo + (hi - lo) * (level - 1) / 14) * (r.burstStacks ?? 6);
    }
    st.bonusAd += r.bonusAdAtStacks ?? 0;
    if (r.bonusAdRange) {
      const [lo, hi] = r.bonusAdRange;
      st.bonusAd += lo + (hi - lo) * (level - 1) / 14;
    }
    if (r.onHit) {
      st.runeOnHitFlat += (r.onHit.flat ?? 0) + (r.onHit.adRatio ?? 0) * st.bonusAd;
    }
    if (r.burstProc && r.burstProc.condition !== "targetBelow50") {
      const p = r.burstProc;
      const flat = p.baseRange ? p.baseRange[0] + (p.baseRange[1] - p.baseRange[0]) * (level - 1) / 14 : (p.flat ?? 0);
      const cond = p.condition === "targetBelowHalfInWindow";
      addProc({
        // Souls are a permanent stack, so they belong in the base value.
        flat: flat + (cond ? (p.perSoul ?? 0) * (p.assumedSouls ?? 0) : 0),
        // PERCENT, divided once here. This file used to store Electrocute as a
        // fraction (0.1) and Dark Harvest as a percent (10) for the same 10%,
        // and this line divided by nothing -- so Dark Harvest was charged ten
        // times bonus AD instead of a tenth of it, +1385 flat damage on a Zed
        // build, unconditionally, as unmitigated TRUE damage.
        adRatio: (p.adRatio ?? 0) / 100,
        apRatio: (p.apRatio ?? 0) / 100,
        type: p.type ?? "physical", label: rn,
        cd: lvlRange(p.cdSec, level), arm: lvlRange(p.armSec, level),
        // Dark Harvest only fires on a target under half health. The gate read
        // `!== "targetBelow50"` and the real condition string is
        // "targetBelowHalfInWindow", so it never matched and the proc was
        // granted for free. Mirrors fight_engine.py's conditionalProcs.
        need: cond ? 0.5 : 0,
      });
    }
    st.damageAmp += r.ampPct ?? 0;
  }
  st.bonusMs *= 1 + msAmp;
  // Paid once the rune loop is done and the stats it scales off are final.
  st.runeOnHitFlat += runeOnHit.adRatio * st.bonusAd + runeOnHit.apRatio * st.ap;

  // kit steroids + conversions
  const f = DATA.formulas[name]?.abilities ?? {};
  st.timedSteroids = [];
  for (const [abSlot, ab] of Object.entries<any>(f)) {
    for (const s of ab.steroids ?? []) {
      const pct = s.pct != null ? scaleVal(s.pct, 3, level) : 0;
      if (s.from === "bonusMs" && s.stat === "ad" && pct) continue;
      // Duration is structured on nine steroids and stated in prose on
      // forty-two more ("Duration: 5 seconds", "for 3 seconds"), so both are
      // read. Anything with neither is treated as permanent, which is right
      // for passives and is the existing behaviour for the rest.
      const noteS = String(s.note ?? "").match(/(\d+(?:\.\d+)?)\s*second/i);
      const durationS = typeof s.durationS === "number" ? s.durationS
        : noteS ? Number(noteS[1]) : null;
      if (durationS && durationS > 0) {
        const cds = (f[abSlot]?.cooldowns ?? []);
        st.timedSteroids.push({
          stat: s.stat,
          asPct: s.stat === "attackSpeed" ? (pct || scaleVal(s.flat, 3, level)) : 0,
          adFlat: s.stat === "ad" && s.flat ? scaleVal(s.flat, 3, level) : 0,
          durationS,
          cooldownS: cds.length ? scaleVal(cds, 3, level) : 12,
        });
      }
      if (s.stat === "attackSpeed") st.baseAsPct += pct || scaleVal(s.flat, 3, level);
      else if (s.stat === "ad" && s.flat) st.bonusAd += scaleVal(s.flat, 3, level);
      else if (s.stat === "moveSpeed" && pct) st.bonusMs += st.baseMs * pct / 100 * 0.5;
      else if ((s.stat === "armor" || s.stat === "mr") && s.flat) st[s.stat] += scaleVal(s.flat, 3, level);
      else if (s.stat === "damageReduction") {
        // Flat damage reduction from a kit (Alistar's ultimate). Takes the
        // strongest source, mirroring how the rune path treats drPct.
        st.dr = Math.max(st.dr, scaleVal(s.pct, 3, level) / 100);
      } else if (s.stat === "hp") {
        // Transform ultimates grant flat Health (Shyvana, Nasus, Volibear). It
        // is BONUS health, so shield and HP-scaling effects see it. Python has
        // applied this since transforms were modelled; the port had neither
        // this nor the damageReduction branch, so Shyvana resolved 600 less
        // bonus health than the advisor and Volibear 525 less.
        let hp = scaleVal(s.flat, 3, level);
        if (!hp && s.pct) hp = st.hp * scaleVal(s.pct, 3, level) / 100;
        st.hp += hp;
        st.bonusHp += hp;
      }
    }
  }
  for (const ab of Object.values<any>(f)) {
    for (const s of ab.steroids ?? []) {
      if (s.from === "bonusMs" && s.stat === "ad" && s.pct != null)
        st.bonusAd += st.bonusMs * scaleVal(s.pct, 3, level) / 100;
    }
  }

  // Percent CDR (Ionian boots) is not flat haste: X% CDR == 100X/(100-X) haste.
  if (st.hastePct) {
    const p = Math.min(st.hastePct, 0.9);
    st.haste += 100 * p / (1 - p);
  }
  // Navori: each auto cuts remaining cooldowns, which is haste-equivalent
  // uptime. Approximated as haste; a real model needs per-cast cooldown state.
  if (st.cdRefundPctPerAuto) st.haste += st.cdRefundPctPerAuto * 2;

  // kit mechanics (evidence-grounded): fixedAS / reload / doubleShot / noResource
  const mechs: Record<string, any> = {};
  for (const mm of DATA.formulas[name]?.mechanics ?? []) mechs[mm.kind] = mm;
  const know: any = DATA.formulas[name]?.knowledge ?? {};
  if (!mechs.noResource && (know.resource === "energy" || know.resource === "none"))
    mechs.noResource = { kind: "noResource" };
  // Mana conversions land HERE: after items, after runes (Manaflow Band's
  // 300), and after a resourceless kit has zeroed mana -- so Manamune simply
  // grants nothing on Katarina rather than being granted and subtracted back.
  if (mechs.noResource) st.mana = 0;
  if (manaConv.ad) st.bonusAd += manaConv.ad / 100 * st.mana;
  if (manaConv.ap) st.ap += manaConv.ap / 100 * st.mana;
  if (manaConv.hp) {
    const hpFromMana = manaConv.hp / 100 * st.mana;
    st.hp += hpFromMana;
    st.bonusHp += hpFromMana;
  }
  // Rabadon's "Overkill" multiplies TOTAL AP, so it must land after every AP
  // source above -- including Archangel's mana conversion just now.
  if (st.apAmp) st.ap *= 1 + st.apAmp;
  // Adaptive on-hit (Gnaw) lands with FINAL stats. The old model paid the
  // flat 15 twice (once physical, once magic) and dropped the scaling half
  // entirely, which on an AP on-hit champion is most of the item.
  if (adaptiveOnHit.flat || adaptiveOnHit.adPct || adaptiveOnHit.apPct) {
    const dmg = adaptiveOnHit.flat + adaptiveOnHit.adPct * st.bonusAd
      + adaptiveOnHit.apPct * st.ap;
    if (prefersAp) st.onHitMagic += dmg;
    else st.onHitPhys += dmg;
  }
  st.doubleShotMult = mechs.doubleShot
    ? 1 + (Number(mechs.doubleShot.secondShotPct) || 50) / 100 * 0.6 : 1;
  // multiShot: one attack fires N projectiles (Graves' shotgun, Ashe's Volley,
  // Twitch, Lulu). Each pellet rolls crit and carries on-hit, so this scales
  // the whole auto. Python has modelled it since the mechanic was extracted and
  // the port never had it at all, so the TS engine thought these champions
  // barely auto-attacked: Ashe measured 6.0% below Python over an 8s window
  // while the other seven champions tested agreed to the decimal.
  if (mechs.multiShot) {
    const shots = Number(mechs.multiShot.shots) || 1;
    const per = Number(mechs.multiShot.damagePerShotPct) || 100;
    st.doubleShotMult *= Math.max(1, shots * per / 100);
  }

  st.ad = st.baseAd + st.bonusAd;
  if (mechs.fixedAttackSpeed) {
    st.as = st.baseAs;
  } else {
    let asPct = st.baseAsPct;
    if (!mechs.reload) asPct *= know.asEfficiency ?? 1; // Tier-2, no double dip with reload
    // Attack speed GROWS with level; the port ignored that entirely and fought
    // every champion at its level-1 rate. Level bonus is innate, so
    // asEfficiency (an ITEM discount) must not touch it. Mirrors
    // fight_engine.level_as_bonus.
    const growth = Number(c.asGrowth) || 0;
    const levelBonus = growth && level > 1
      ? growth * (level - 1) * (0.7025 + 0.0175 * (level - 1)) : 0;
    st.as = Math.min(st.baseAs * (1 + levelBonus + asPct / 100), AS_CAP);
  }
  if (mechs.reload) {
    const mag = Number(mechs.reload.magazine) || 2;
    const reloadS = Number(know.reloadSeconds) || 1.0; // Tier-2 or documented default
    st.as = mag / (mag / st.as + reloadS);
  }
  // Guinsoo's Wrath: "Attacks ... no longer Critical Strike". The converted
  // magic damage already sits in the item's onHitFlatMagic, so leaving crit
  // standing paid for the same conversion twice.
  if (st.critDisabled) {
    st.crit = 0;
    st.critMult = BASE_CRIT_MULT;
    st.critDamagePerExcessCrit = 0;
  }

  // Infinity Edge "Limit Break": crit rate past 100% is wasted, so it converts
  // to crit DAMAGE. Runs once every crit source (items, runes) is summed.
  if (st.critDamagePerExcessCrit && st.crit > 1)
    st.critMult += st.critDamagePerExcessCrit * (st.crit - 1);
  st.crit = Math.min(st.crit, 1);
  // A kit whose CRIT CHANCE is a damage stat and whose critical strikes deal
  // no extra damage. Only Ashe: Frost Shot reads "bonus physical damage equal
  // to 10% (+0-75% based on critical strike chance) of the attack's damage"
  // and "critical strikes do not deal any additional damage". So crit chance
  // buys her damage and crit DAMAGE buys her nothing, which is the exact
  // opposite of every other marksman. critMult is set to 1 rather than
  // zeroing st.crit, because her attacks really do critically strike -- they
  // just pay out as the bonus above, and on-crit item clauses still fire.
  const autoBonus = (DATA.formulas[name] as any)?.autoBonus;
  if (autoBonus) {
    const ie = itemSlugs.includes("infinity-edge") ? (autoBonus.ieBonusPct ?? 0) : 0;
    st.autoBonusPct = (autoBonus.basePct ?? 0)
      + ((autoBonus.perCritPct ?? 0) + ie) * st.crit;
    if (autoBonus.critDealsNoBonus) st.critMult = 1;
  }
  // Ingenious Hunter shortens ITEM cooldowns, and it is a RUNE, so it is only
  // known after the item loop that created these procs. Applied here, and only
  // to procs whose source is an item: a keystone's cooldown is not item
  // haste's business. Expressible at all only since procs gained cooldowns.
  if (st.itemHaste) {
    const m = 100 / (100 + st.itemHaste);
    for (const pr of st.procs as Proc[]) {
      if (pr.cd !== Infinity && pr.label && DATA.items[pr.label]) pr.cd *= m;
    }
  }

  // Soul Transfer's Shadow Dance: clones that attack alongside you. A real,
  // in-combat physical damage stream that nothing modelled at all.
  //
  // Crits per second is crit rate x attack rate, each clone lives 4 seconds,
  // and at most two exist at once -- so the population is spawn rate x
  // lifetime, capped. Their damage is then folded into the on-hit bundle
  // DIVIDED BY attack speed, the same way Titanic Cleave converts a
  // per-second effect into a per-auto one: a faster attacker dilutes a
  // time-based stream across more autos rather than multiplying it.
  if (st.cloneAdPct) {
    const alive = Math.min(st.cloneMaxCount || 1, st.crit * st.as * (st.cloneLifetimeS || 0));
    const cloneAs = Math.min(AS_CAP, st.baseAs * (1 + (st.cloneAsFromCritPct || 0) / 100 * st.crit));
    const cloneDps = alive * cloneAs * (st.cloneAdPct / 100) * st.ad;
    st.onHitPhys += cloneDps / Math.max(st.as, 0.1);
  }
  // Now that crit is final, pay the crit-gated increments at the rate the build
  // actually crits. The values they replaced were folded in at 100% uptime.
  if (onCrit.pctPen) st.pctPenFactors.push(onCrit.pctPen / 100 * st.crit);
  if (onCrit.physVampPct) {
    const v = onCrit.physVampPct / 100 * st.crit;
    st.vamp += v;
    st.lifestealPct += v;
  }
  let pen = 1;
  for (const p of st.pctPenFactors) pen *= 1 - p;
  st.pctPen = 1 - pen;
  return st;
}

function mults(st: any, target: any): [number, number] {
  let armor = target.armor * (1 - st.armorShred);
  armor = armor * (1 - st.pctPen) - st.flatPen;
  // MR shred mirrors armour shred (Abyssal Mask, Bloodletter's Curse). Only
  // armour had a shred channel, so magic shred items did nothing.
  let mr = target.mr * (1 - (st.mrShred ?? 0)) - (st.mrShredFlat ?? 0);
  mr = mr * (1 - st.pctMagicPen) - st.flatMagicPen;
  return [100 / (100 + Math.max(armor, 0)), 100 / (100 + Math.max(mr, 0))];
}

/** One application of everything that fires ON HIT, by damage type. The
 *  attack's own AD is excluded: re-applying on-hits repeats Nashor's, Wit's
 *  End and the %HP on-hits, not the auto itself.
 *
 *  `kit` carries the champion's OWN on-hit components (Gwen's Thousand Cuts,
 *  Skip 'n Slash). In game "apply on-hits" includes those, and leaving them
 *  out was the conservative first cut: on an on-hit caster they are most of
 *  what a re-application is worth. */
function onHitBundle(st: any, target: any, physM: number, magicM: number,
                     kit?: [number, number, number]): [number, number, number] {
  const phys = (st.onHitPhys + st.runeOnHitFlat
    + st.onHitPctCurrentHp * target.hp * 0.7
    + st.onHitPctMaxHp * target.hp) * physM;
  return [phys + (kit?.[0] ?? 0), st.onHitMagic * magicM + (kit?.[1] ?? 0), kit?.[2] ?? 0];
}

function autoUptime(name: string, window: number, st?: any): number {
  if (window <= 4) return 1;
  if (RANGED_CLASSES.has(DATA.champions[name]?.class ?? "")) return 1;
  // move speed lets a melee stick to its target -> more attacks land
  if (!st) return MELEE_AUTO_UPTIME;
  // A slow on the target closes distance exactly as your own move speed does,
  // so it rides the same term. 330 is a champion's base move speed.
  const relativeMs = (st.bonusMs ?? 0) + (st.targetSlow ?? 0) * 330;
  return Math.min(0.93, MELEE_AUTO_UPTIME + relativeMs * 0.0016);
}

// Side outputs from the most recent rotation() call, read synchronously right
// after (safe — JS is single-threaded). Mirrors the extra keys the Python
// rotation returns: auto damage, damage-by-type, cast log, ideal auto count.
let ROT_AUTO_DMG = 0;
let ROT_BY_TYPE: Record<string, number> = { physical: 0, magic: 0, true: 0 };
let ROT_CAST_LOG: Record<string, { name: string; casts: number; max: number }> = {};
let ROT_NAUTOS = 0;
let ROT_BOLT_DMG = 0;
let ROT_BY_SLOT: Record<string, number> = {};
let ROT_NAUTOS_IDEAL = 0;

/**
 * The stat block as it averages over a fight of this length.
 *
 * Ability buffs were applied permanently: Xin Zhao's E gives +67.5% attack
 * speed for FIVE seconds and the sim used it for all twenty, inflating his auto
 * count and most of his damage with it. A buff is up for its duration once per
 * cooldown, so over a window it is worth its uptime, not its peak.
 *
 * The displayed stat block is left alone -- the player really does have that
 * attack speed while it is running. Only the simulation averages it.
 */
function forWindow(name: string, st: any, window: number, level: number): any {
  const timed = st.timedSteroids as any[] | undefined;
  if (!timed || !timed.length || window <= 0) return st;
  const hasteM = 100 / (100 + (st.haste ?? 0));
  let asPctLost = 0;
  let adLost = 0;
  for (const s of timed) {
    const cd = Math.max(0.5, (s.cooldownS || 12) * hasteM);
    const casts = 1 + Math.floor(window / cd);
    const uptime = Math.min(1, (s.durationS * casts) / window);
    asPctLost += (s.asPct || 0) * (1 - uptime);
    adLost += (s.adFlat || 0) * (1 - uptime);
  }
  if (!asPctLost && !adLost) return st;

  const adj = { ...st };
  if (adLost) {
    adj.bonusAd = Math.max(0, st.bonusAd - adLost);
    adj.ad = adj.baseAd + adj.bonusAd;
  }
  if (asPctLost) {
    // Mirrors the attack-speed maths in resolveStats, so the two cannot drift.
    const mechs = DATA.formulas[name]?.mechanics
      ? Object.fromEntries((DATA.formulas[name]!.mechanics as any[]).map((m) => [m.kind, m]))
      : {};
    const know = (DATA.formulas[name] as any)?.knowledge ?? {};
    if (!mechs.fixedAttackSpeed) {
      let asPct = Math.max(0, st.baseAsPct - asPctLost);
      if (!mechs.reload) asPct *= know.asEfficiency ?? 1;
      adj.as = Math.min(adj.baseAs * (1 + asPct / 100), AS_CAP);
      if (mechs.reload) {
        const mag = Number(mechs.reload.magazine) || 2;
        const reloadS = Number(know.reloadSeconds) || 1.0;
        adj.as = mag / (mag / adj.as + reloadS);
      }
    }
  }
  return adj;
}

export function rotation(name: string, st: any, target: any, window: number,
                         level = 13): number {
  st = forWindow(name, st, window, level);
  // An enemy Frozen Heart's Chill is a real attack-speed cut and belongs here,
  // after forWindow has finished deriving attack speed from the steroids.
  if (st.externalAsMult && st.externalAsMult !== 1) {
    st = { ...st, as: st.as * st.externalAsMult };
  }
  const f = DATA.formulas[name]?.abilities ?? {};
  const [physM, magicM] = mults(st, target);
  const giant = 1 + st.giant * Math.min(1, target.bonusHp / 1700);
  const critEv = 1 + st.crit * (st.critMult - 1);
  const hasteM = 100 / (100 + st.haste);
  let total = 0, castsTotal = 0, autoDmg = 0;
  const byType: Record<string, number> = { physical: 0, magic: 0, true: 0 };
  const castLog: Record<string, { name: string; casts: number; max: number }> = {};
  // Damage attributed to each ability slot. Only an ult-only amplifier needs
  // this, which is why the port never grew it.
  const bySlot: Record<string, number> = {};
  const addT = (t: string, v: number) => { byType[t] = (byType[t] ?? 0) + v; };

  const compDmg = (comp: any, rank: number): number => {
    let base = scaleVal(comp.base, rank, level);
    if (comp.when === "dot total" && comp.durationS) base *= comp.durationS;
    let val = base;
    for (const r of comp.ratios ?? []) {
      const pct = scaleVal(r.pct ?? 0, rank, level) / 100;
      const src: Record<string, number> = {
        ad: st.ad, bonusAd: st.bonusAd, ap: st.ap,
        targetMaxHp: target.hp, targetCurrentHp: target.hp * 0.7,
        targetMissingHp: target.hp * 0.3, ownMaxHp: st.hp, ownBonusHp: st.bonusHp,
        armor: st.armor, mr: st.mr, bonusMs: st.bonusMs, bonusArmor: 0, bonusMr: 0,
      };
      val += pct * (src[r.stat] ?? 0);
    }
    val *= Math.max(1, Math.floor(rankVal(comp.hits ?? 1, rank)) || 1);
    const m = comp.type === "physical" ? physM : comp.type === "magic" ? magicM : 1;
    return val * m * (comp.type === "physical" ? giant : 1);
  };

  // skill ranks
  const basicSlots = ["1", "2", "3"].filter((s) => s in f);
  const so = DATA.champions[name]?.skillOrder ?? {};
  const rankOf: Record<string, number> = {};
  if (Object.keys(so).length) {
    for (const s of basicSlots)
      rankOf[s] = Math.max(0, (so[s] ?? []).filter((lv: number) => lv <= level).length - 1);
  } else {
    const prio = [...basicSlots].sort((a, b) => {
      const d = (slot: string) => (f[slot].damage ?? []).filter((c: any) => !c.alt && !c.dropped)
        .reduce((acc: number, c: any) => acc + compDmg(c, 3), 0);
      return d(b) - d(a);
    });
    prio.forEach((s, i) => { rankOf[s] = level >= 14 ? 3 : i < 2 ? 3 : 1; });
  }
  rankOf["4"] = level >= 13 ? 2 : 1;

  const perAuto: any[] = [];
  const perAutoSlot = new Map<any, string>();
  const addPerAuto = (c: any, slot: string) => {
    if (perAuto.includes(c)) return;
    perAuto.push(c);
    perAutoSlot.set(c, slot);
  };
  // How often a per-auto component ACTUALLY lands, as a share of autos.
  //
  // Everything tagged "per auto" was being added to every single attack. For a
  // passive that reads "every third attack deals an additional 13 (22% AD)"
  // that is three times too much damage, and the extractor already recorded the
  // condition as an everyNHit mechanic which nothing read.
  const everyN = (DATA.formulas[name]?.mechanics ?? [])
    .find((m: any) => m.kind === "everyNHit");
  const everyNShare = (() => {
    if (!everyN) return 1;
    if (typeof everyN.n === "number" && everyN.n > 1) return 1 / everyN.n;
    // Eight champions record the mechanic without the number. The evidence
    // string usually still states it ("Every third attack deals..."), so read
    // that before falling back, or Xin Zhao and Akshan would be guesses that
    // happen to be right.
    const ev = String(everyN.evidence ?? "").toLowerCase();
    // Ordinals and cardinals both appear: "every third attack" but also
    // "every three hits from attacks and abilities".
    const words: Record<string, number> = {
      second: 2, other: 2, two: 2, third: 3, three: 3, fourth: 4, four: 4,
      fifth: 5, five: 5, sixth: 6, six: 6,
    };
    for (const [word, n] of Object.entries(words)) {
      if (ev.includes(`every ${word}`) || ev.includes(`every other`)) return 1 / n;
    }
    const digits = ev.match(/every\s+(\d+)/) ?? ev.match(/(\d+)\s+(?:consecutive\s+)?(?:attacks|hits|stacks)/);
    if (digits) {
      const n = Number(digits[1]);
      if (n > 1 && n <= 10) return 1 / n;
    }
    // No number anywhere: three is the commonest shape in this game, but it is
    // an assumption, so it is stated here rather than buried.
    return 1 / 3;
  })();
  // Abilities that empower a LIMITED number of following attacks. Xin Zhao's Q
  // empowers three and was being applied to all twenty-two autos of a long
  // fight. The count is stated in the prose the extractor could not model
  // ("Empowers next three attacks"), so it is read from there rather than
  // curated per champion.
  const WORD_N: Record<string, number> = {
    one: 1, two: 2, three: 3, four: 4, five: 5, six: 6,
  };
  const empowerLimit = new Map<string, number>();
  for (const [slot, ab] of Object.entries(DATA.formulas[name]?.abilities ?? {})) {
    // An explicit limit from the corrections overlay wins outright: when a
    // correction rewrites the damage list, the empowerment sentence leaves the
    // unmodeled prose and the regex below has nothing to read -- Camille's Q
    // then rode EVERY auto of the window.
    const explicit = (ab as any).empowerLimit;
    if (explicit) {
      empowerLimit.set(slot, Math.max(1, Number(explicit) || 1));
      continue;
    }
    for (const u of ((ab as any).unmodeled ?? [])) {
      const m = String(u).match(
        /empower\w*\s+(?:the\s+|his\s+|her\s+|their\s+)?next\s+(\w+)\s+(?:basic\s+)?attack/i);
      if (!m) continue;
      const word = m[1].toLowerCase();
      const n = WORD_N[word] ?? (Number(word) || 1);
      empowerLimit.set(slot, Math.max(1, n));
    }
  }

  // Xin Zhao's Q: "each attack reduces other ability cooldowns by 1s". Three
  // empowered attacks per cast is three seconds off W, E and R every cycle,
  // which is the difference between casting W twice in a fight and casting it
  // three times.
  let cdrPerEmpoweredHit = 0;
  let cdrSourceSlot = "";
  for (const [slot, ab] of Object.entries(DATA.formulas[name]?.abilities ?? {})) {
    for (const u of ((ab as any).unmodeled ?? [])) {
      const m = String(u).match(
        /reduc\w*\s+(?:all\s+|his\s+|her\s+|their\s+)?other\s+(?:ability\s+)?cooldowns?\s+by\s+([\d.]+)\s*s/i);
      if (m) {
        cdrPerEmpoweredHit = Number(m[1]) || 0;
        cdrSourceSlot = slot;
      }
    }
  }

  /**
   * Share of autos a per-auto component actually lands on.
   *
   * A passive that fires every Nth attack rides 1/N of them. An ability that
   * empowers N attacks per cast rides N x (its casts), capped at every auto --
   * so a Q cast twice in a fight empowers six attacks, not all of them.
   */
  // Four of these passives say the stacks come from abilities too ("Every
  // third attack OR ABILITY on the same target"). Counting only autos then
  // undercounts them, which is the opposite error to the one just fixed, so
  // ability hits are added to the denominator's input rather than ignored.
  const abilitiesStack = /abilit/i.test(String(everyN?.evidence ?? ""));
  const perAutoShare = (c: any, nAutos: number): number => {
    const slot = perAutoSlot.get(c);
    if (slot === "P") {
      if (!abilitiesStack || nAutos <= 0) return everyNShare;
      const abilityHits = Object.values(castLog).reduce((n, v: any) => n + v.casts, 0);
      // Triggers over the window, expressed per auto so the caller's `* nAutos`
      // arrives at the right total.
      return Math.min(1, everyNShare * ((nAutos + abilityHits) / nAutos));
    }
    const limit = slot ? empowerLimit.get(slot) : undefined;
    if (limit && nAutos > 0) {
      let casts = slot && castLog[slot] ? castLog[slot].casts : 0;
      if (casts <= 0 && slot) {
        // An ability whose ONLY damage is per-auto never enters the cast loop,
        // because that loop needs a component to score. Xin Zhao's Q is exactly
        // that, so reading casts alone would silently delete it instead of
        // capping it. Fall back to how often its cooldown allows a cast.
        const cds = (DATA.formulas[name]?.abilities?.[slot] as any)?.cooldowns ?? [];
        const cd = rankVal(cds.length ? cds : 12, 3) || 12;
        casts = Math.max(1, 1 + Math.floor(window / Math.max(0.5, cd * hasteM)));
      }
      return Math.min(1, (limit * casts) / nAutos);
    }
    return 1;
  };
  const comboSeq: string[] = DATA.formulas[name]?.combo ?? [];
  /** The KIT's own on-hit components, split by type. Gwen's Thousand Cuts and
   *  Skip 'n Slash are on-hit effects the champion carries, not stats, so an
   *  item that re-applies on-hits re-applies these too. Shared so the auto and
   *  the extra-application path charge exactly the same damage. */
  const kitPerAuto = (nAutos: number): [number, number, number] => {
    let p = 0, m = 0, t = 0;
    for (const comp of perAuto) {
      // A multiShot kit's shotgun is already priced by doubleShotMult, which
      // scales the WHOLE auto so the pellets crit and carry on-hit -- the
      // better model. The passive tooltip describes those same pellets again as
      // a per-auto AD ratio, so counting both charges the shotgun twice.
      // Mirrors the identical guard in fight_engine._kit_per_auto.
      if ((st.doubleShotMult ?? 1) > 1 && perAutoSlot.get(comp) === "P"
          && ((comp.ratios ?? []) as any[]).every(
            (r) => r.stat === "ad" || r.stat === "bonusAd")) continue;
      const perHit = (c: any) =>
        compDmg(c, 3) / Math.max(1, Math.floor(rankVal(c.hits ?? 1, 3)) || 1);
      let unit = perHit(comp);
      // A component with a CRIT VARIANT is charged at the build's crit rate
      // against its non-critical partner. Graves is the only kit in the roster
      // shaped this way: his shotgun fires 4 bullets for 144% AD normally and 6
      // for 280% on a crit, and the crit line is flagged alt, so it was
      // filtered out and crit never touched his actual attack at all.
      const slotOf = perAutoSlot.get(comp);
      const siblings = (DATA.formulas[name]?.abilities?.[slotOf ?? ""] as any)?.damage ?? [];
      const critVariant = siblings.find((x: any) => x.critVariantOf === comp.name);
      if (critVariant) unit = (1 - st.crit) * unit + st.crit * perHit(critVariant);
      const cd = unit * perAutoShare(comp, nAutos);
      if (comp.type === "magic") m += cd;
      else if (comp.type === "true") t += cd;
      else p += cd;
    }
    return [p, m, t];
  };
  /** Bolt damage on OTHER targets. Deliberately never added to `total`. */
  const doBolts = (nAutos: number) => {
    if (!st.extraBolts || !st.extraBoltAdPct) return 0;
    const kit = DATA.champions[name]?.repeatsOnHit ? kitPerAuto(nAutos) : undefined;
    const [bp, bm, bt] = onHitBundle(st, target, physM, magicM, kit);
    const perBolt = st.extraBoltAdPct / 100 * st.ad * critEv * physM + bp + bm + bt;
    return perBolt * st.extraBolts * nAutos;
  };
  const doAutos = (nAutos: number) => {
    // How much of the normal attack is REPLACED by a kit component rather than
    // added to. Graves' shotgun IS his attack, so charging a 100% AD auto and
    // then his 144% AD passive on top was a phantom extra swing on every hit:
    // 2.44x AD measured where the tooltip says 1.44x. Scaled by the share
    // rather than dropped outright, because Nocturne replaces one auto every
    // twelve seconds and Renekton one per cast, not all of them.
    let replacedShare = 0;
    for (const comp of perAuto) {
      if ((comp as any).replacesAuto) replacedShare += perAutoShare(comp, nAutos);
    }
    replacedShare = Math.min(1, replacedShare);
    // Frost Shot's bonus is a share OF THE ATTACK, so it multiplies the auto
    // rather than adding a flat AD term. 0 for every champion but Ashe.
    const autoBonus = 1 + (st.autoBonusPct ?? 0) / 100;
    let aPhys = st.ad * critEv * physM * giant * (1 - replacedShare) * autoBonus;
    aPhys += st.onHitPhys * physM;
    aPhys += (st.onHitPctCurrentHp * target.hp * 0.7 + st.onHitPctMaxHp * target.hp) * physM;
    aPhys += st.runeOnHitFlat * physM;
    // Titanic Cleave arms every CLEAVE_EVERY seconds, not every auto, so only
    // a fraction of attacks carry it: faster attacks dilute it, not scale it.
    if (st.cleaveFlat || st.cleavePctBonusHp) {
      const cleave = st.cleaveFlat + st.cleavePctBonusHp * st.bonusHp;
      aPhys += cleave * Math.min(1, (1 / CLEAVE_EVERY) / Math.max(st.as, 0.1)) * physM;
    }
    let aMagic = st.onHitMagic * magicM;
    let aTrue = 0;
    const [kp, km, kt] = kitPerAuto(nAutos);
    aPhys += kp; aMagic += km; aTrue += kt;
    const dsm = st.doubleShotMult ?? 1;
    // Plated Steelcaps' Block reduces BASIC ATTACK damage only, which is why
    // it rides here and not on st.dr (all damage). 1 when the target has none.
    const adm = st.autoDamageMult ?? 1;
    addT("physical", aPhys * dsm * nAutos * adm);
    addT("magic", aMagic * dsm * nAutos * adm);
    addT("true", aTrue * dsm * nAutos * adm);
    return (aPhys + aMagic + aTrue) * dsm * nAutos * adm;
  };
  /**
   * Discrete procs, charged at the rate their own descriptions state.
   *
   * `damageSoFar` is this rotation's damage before procs, read only by procs
   * gated on the target's health.
   */
  const oneTimes = (damageSoFar: number) => {
    let p = 0, m = 0, t = 0;
    for (const pr of st.procs as Proc[]) {
      // Nothing lands before the effect has armed: Electrocute needs three
      // stacks inside three seconds, Heartsteel charges for 2.5.
      if (window + 1e-9 < pr.arm) continue;
      const times = pr.cd === Infinity
        ? 1
        : 1 + Math.floor((window - pr.arm) / pr.cd);
      // A proc gated on the target's health is earned only when this
      // champion's own damage in this window actually gets them there. Tapered
      // rather than a cliff, so a 4% damage change cannot flip a keystone on
      // and send the item search chasing the discontinuity. Mirrors the
      // `reach` taper in fight_engine.py's conditionalProcs.
      const reach = pr.need
        ? Math.min(1, damageSoFar / Math.max(target.hp * pr.need, 1e-9))
        : 1;
      if (reach <= 0) continue;
      let dtype = pr.type;
      if (dtype === "adaptive") dtype = st.ap >= st.bonusAd ? "magic" : "physical";
      const val = (pr.flat + pr.adRatio * st.bonusAd + pr.apRatio * st.ap
                   + pr.pctMaxHp * target.hp) * times * reach;
      // The old routing was "physical goes through armour, everything else is
      // true damage", so every magic and adaptive proc bypassed magic resist
      // entirely -- Dark Harvest's whole contribution arrived unmitigated.
      if (dtype === "magic") m += val * magicM;
      else if (dtype === "true") t += val;
      else p += val * physM;
    }
    addT("physical", p); addT("magic", m); addT("true", t);
    return p + m + t;
  };

  if (window <= 4 && comboSeq.length) {
    const budget = Math.max(1, Math.floor(window / 0.45));
    const seq = comboSeq.slice(0, budget);
    let nAutosSeq = 0;
    for (const slot of seq) {
      if (slot === "auto") { nAutosSeq++; continue; }
      if (!(slot in f)) continue;
      const comps = (f[slot].damage ?? []).filter((c: any) => !c.alt && !c.dropped && c.when !== "per auto");
      for (const c of (f[slot].damage ?? []))
        if (!c.alt && c.when === "per auto" && !c.dropped) addPerAuto(c, slot);
      const rank = slot === "4" ? 2 : 3;
      const ampA = 1 + st.abilityAmp;
      for (const c of comps) {
        const cd = compDmg(c, rank) * ampA;
        addT(c.type, cd); total += cd;
        bySlot[slot] = (bySlot[slot] ?? 0) + cd;
      }
      castsTotal++;
    }
    const nAutos = Math.max(nAutosSeq, Math.floor(window * st.as * 0.5));
    const dAutos = doAutos(nAutos);
    total += dAutos;
    autoDmg += dAutos;
    if (st.spellbladeBaseAdPct || st.spellbladePctMaxHp || st.spellbladeApPct) {
      const procs = Math.min(castsTotal, nAutos, 1 + Math.floor(window / SPELLBLADE_CD));
      // Lich Bane is "75% base AD + 45% AP" and deals MAGIC damage; type
      // follows the item.
      const sbMagic = st.spellbladeMagic > 0;
      const sb = (st.spellbladeBaseAdPct / 100 * st.baseAd
        + st.spellbladeApPct / 100 * st.ap
        + st.spellbladePctMaxHp / 100 * target.hp) * (sbMagic ? magicM : physM) * procs;
      total += sb;
      autoDmg += sb;
      addT(sbMagic ? "magic" : "physical", sb);
      if (st.extraOnHitApplications) {
        const [ep, em, et] = onHitBundle(st, target, physM, magicM,
          DATA.champions[name]?.repeatsOnHit ? kitPerAuto(nAutos) : undefined);
        const mult = st.extraOnHitApplications * procs;
        total += (ep + em + et) * mult;
        autoDmg += (ep + em + et) * mult;
        addT("physical", ep * mult);
        addT("magic", em * mult);
        addT("true", et * mult);
      }
    }
    total += oneTimes(total);
    if (st.dotDps || st.dotPctMaxHp) {
    const d = (st.dotDps + st.dotPctMaxHp * target.hp) * window * magicM;
    total += d; addT("magic", d);
  }
    if (st.graspPct) {
      const d = st.graspPct / 100 * target.hp * magicM * (1 + Math.floor(window / st.graspEvery));
      total += d; addT("magic", d);
    }
  // Kit amplification: a percentage bonus on damage ALREADY counted, which no
  // per-ability formula can express. Amumu's Cursed Touch turns his own magic
  // damage into extra true damage (worth 8.5% of his rotation), Kayn's Shadow
  // Assassin adds magic to everything for 3 seconds, Smolder empowers three
  // abilities. Values and the reasoning behind them live in data/kit_amps.json
  // and were read by the Python engine only.
  {
    // Captured BEFORE the loop, so an "all" entry cannot be paid on a bonus an
    // earlier entry just added. fight_engine passes total_now the same way.
    const totalNow = total;
    let kitBonus = 0;
    for (const entry of ((DATA.kitAmps?.[name]?.amps ?? []) as any[])) {
      const pct = lvlRange(entry.pct, level) / 100;
      if (!pct) continue;
      const src = entry.slot ? (bySlot[entry.slot] ?? 0)
        : entry.appliesTo === "all" ? totalNow
        : (byType[entry.appliesTo ?? "magic"] ?? 0);
      // A stated duration is a real limit, not a guess: a 3s effect inside an
      // 8s fight earns three eighths of it.
      const dur = Number(entry.durationS) || 0;
      const bonus = src * pct * (dur ? Math.min(1, dur / Math.max(window, 1e-9)) : 1);
      if (!bonus) continue;
      addT(entry.dealtAs ?? "magic", bonus);
      kitBonus += bonus;
    }
    total += kitBonus;
  }
  // Ultimate-only amplification (Axiom Arcanist). Mirrors fight_engine, which
  // charges it as magic and before the whole-rotation damage amp.
  if (st.ultAmp && bySlot["4"]) {
    const ultBonus = bySlot["4"] * st.ultAmp;
    total += ultBonus;
    addT("magic", ultBonus);
  }
    const amp = 1 + st.damageAmp;
    ROT_AUTO_DMG = autoDmg * amp;
    ROT_BY_TYPE = { physical: byType.physical * amp, magic: byType.magic * amp, true: byType.true * amp };
    ROT_CAST_LOG = {};
    ROT_NAUTOS = nAutos;
    ROT_BOLT_DMG = doBolts(nAutos) * (1 + st.damageAmp);
    ROT_BY_SLOT = { ...bySlot };
    ROT_NAUTOS_IDEAL = Math.max(1, Math.floor(window * st.as));
    return total * amp;
  }

  let castBudget = Math.max(1, Math.floor(window / 0.45));
  const slots = Object.keys(f).sort((a, b) => (a === "4" ? -1 : 0) - (b === "4" ? -1 : 0));
  for (const slot of slots) {
    const ab = f[slot];
    const comps = (ab.damage ?? []).filter((c: any) => !c.alt && !c.dropped);
    const dmgComps = comps.filter((c: any) => c.when !== "per auto");
    for (const c of comps) if (c.when === "per auto" && !c.dropped) addPerAuto(c, slot);
    // An ability whose damage is ALL per-auto still gets cast -- that is what
    // empowers the attacks. Skipping it here left Xin Zhao's Q out of the cast
    // log entirely, so the combo said "press Q" and the fight reported W, E and
    // R only. It also forced the empowered-auto cap onto a cooldown estimate
    // when a real cast count was available.
    // Slot P excluded: a passive is not cast, and listing "Passive x5" in the
    // abilities used reads as an action the player took.
    const empowersAutos = slot !== "P" && comps.some((c: any) => c.when === "per auto" && !c.dropped);
    if ((!dmgComps.length && !empowersAutos) || castBudget <= 0) continue;
    const cds = ab.cooldowns ?? [];
    const rank = rankOf[slot] ?? 3;
    const cdIdx = cds.length ? Math.min(rank, cds.length - 1) : 0;
    let cd = (cds.length ? cds[cdIdx] : 8) * hasteM;
    if (cdrPerEmpoweredHit && slot !== cdrSourceSlot && window > 0) {
      // Seconds of cooldown removed across the window, spread evenly. Capped at
      // half, so a long fight cannot drive a cooldown to nothing.
      const empowered = empowerLimit.get(cdrSourceSlot) ?? 0;
      const srcCd = Math.max(0.5, rankVal(
        (DATA.formulas[name]?.abilities?.[cdrSourceSlot] as any)?.cooldowns ?? 12, 3) * hasteM);
      const srcCasts = 1 + Math.floor(window / srcCd);
      const seconds = cdrPerEmpoweredHit * empowered * srcCasts;
      cd = Math.max(cd * 0.5, cd - seconds / Math.max(1, window / Math.max(cd, 0.75)));
    }
    let casts = cd ? 1 + Math.floor(window / Math.max(cd, 0.75)) : 1;
    if (slot === "4") casts = 1;
    const maxCasts = casts;
    casts = Math.min(casts, castBudget);
    castBudget -= casts;
    castsTotal += casts;
    castLog[slot] = { name: ab.name ?? slot, casts, max: maxCasts };
    const ampA = 1 + st.abilityAmp;
    for (const c of dmgComps) {
      const cd2 = compDmg(c, rank) * casts * ampA;
      addT(c.type, cd2); total += cd2;
      bySlot[slot] = (bySlot[slot] ?? 0) + cd2;
    }
  }
  const nAutos = Math.max(1, Math.floor(window * st.as * autoUptime(name, window, st)));
  const dAutos = doAutos(nAutos);
  total += dAutos;
  autoDmg += dAutos;
  if (st.spellbladeBaseAdPct || st.spellbladePctMaxHp || st.spellbladeApPct) {
    const procs = Math.min(castsTotal, nAutos, 1 + Math.floor(window / SPELLBLADE_CD));
    const sbMagic = st.spellbladeMagic > 0;
    const sb = (st.spellbladeBaseAdPct / 100 * st.baseAd
      + st.spellbladeApPct / 100 * st.ap
      + st.spellbladePctMaxHp / 100 * target.hp) * (sbMagic ? magicM : physM) * procs;
    total += sb;
    autoDmg += sb;
    addT(sbMagic ? "magic" : "physical", sb);
    if (st.extraOnHitApplications) {
      const [ep, em, et] = onHitBundle(st, target, physM, magicM,
        DATA.champions[name]?.repeatsOnHit ? kitPerAuto(nAutos) : undefined);
      const mult = st.extraOnHitApplications * procs;
      total += (ep + em + et) * mult;
      autoDmg += (ep + em + et) * mult;
      addT("physical", ep * mult);
      addT("magic", em * mult);
      addT("true", et * mult);
    }
  }
  total += oneTimes(total);
  if (st.dotDps || st.dotPctMaxHp) {
    const d = (st.dotDps + st.dotPctMaxHp * target.hp) * window * magicM;
    total += d; addT("magic", d);
  }
  if (st.graspPct) {
    const d = st.graspPct / 100 * target.hp * magicM * (1 + Math.floor(window / st.graspEvery));
    total += d; addT("magic", d);
  }
  // Kit amplification: a percentage bonus on damage ALREADY counted, which no
  // per-ability formula can express. Amumu's Cursed Touch turns his own magic
  // damage into extra true damage (worth 8.5% of his rotation), Kayn's Shadow
  // Assassin adds magic to everything for 3 seconds, Smolder empowers three
  // abilities. Values and the reasoning behind them live in data/kit_amps.json
  // and were read by the Python engine only.
  {
    // Captured BEFORE the loop, so an "all" entry cannot be paid on a bonus an
    // earlier entry just added. fight_engine passes total_now the same way.
    const totalNow = total;
    let kitBonus = 0;
    for (const entry of ((DATA.kitAmps?.[name]?.amps ?? []) as any[])) {
      const pct = lvlRange(entry.pct, level) / 100;
      if (!pct) continue;
      const src = entry.slot ? (bySlot[entry.slot] ?? 0)
        : entry.appliesTo === "all" ? totalNow
        : (byType[entry.appliesTo ?? "magic"] ?? 0);
      // A stated duration is a real limit, not a guess: a 3s effect inside an
      // 8s fight earns three eighths of it.
      const dur = Number(entry.durationS) || 0;
      const bonus = src * pct * (dur ? Math.min(1, dur / Math.max(window, 1e-9)) : 1);
      if (!bonus) continue;
      addT(entry.dealtAs ?? "magic", bonus);
      kitBonus += bonus;
    }
    total += kitBonus;
  }
  // Ultimate-only amplification (Axiom Arcanist). Mirrors fight_engine, which
  // charges it as magic and before the whole-rotation damage amp.
  if (st.ultAmp && bySlot["4"]) {
    const ultBonus = bySlot["4"] * st.ultAmp;
    total += ultBonus;
    addT("magic", ultBonus);
  }
  const amp = 1 + st.damageAmp;
  ROT_AUTO_DMG = autoDmg * amp;
  ROT_BY_TYPE = { physical: byType.physical * amp, magic: byType.magic * amp, true: byType.true * amp };
  ROT_CAST_LOG = castLog;
  ROT_NAUTOS = nAutos;
  ROT_BOLT_DMG = doBolts(nAutos) * (1 + st.damageAmp);
  ROT_BY_SLOT = { ...bySlot };
  ROT_NAUTOS_IDEAL = Math.max(1, Math.floor(window * st.as));
  return total * amp;
}

export interface RotationDetail {
  damage: number;
  autoDamage: number;
  /** Damage attributed to each ability slot, which a heal can scale off. */
  bySlot: Record<string, number>;
  /**
   * Damage Runaan’s bolts deal to OTHER targets. Not part of `damage`: a
   * single-target duel never sees it, and adding it there would inflate
   * every time-to-kill. This is the site’s first area-damage readout.
   */
  boltDamage: number;
  byType: { physical: number; magic: number; true: number };
  /** Per ability: how many times it was cast in the window, and the cap. */
  casts: Record<string, { name: string; casts: number; max: number }>;
  autos: number;
  autosIdeal: number;
}

/**
 * `rotation` plus everything it worked out along the way.
 *
 * rotation() returns only a damage total and leaves the rest in module-level
 * variables for the caller to read afterwards, which is safe exactly until two
 * callers interleave -- there is already a `rotation(...) // restore stashes`
 * line in analyzeBuild working around it. Reading them here, in the same
 * synchronous breath as the call, is the one moment nothing else can have
 * overwritten them, so new callers get a value instead of a landmine.
 */
export function rotationDetail(name: string, st: any, target: any, window: number,
                               level = 13): RotationDetail {
  const damage = rotation(name, st, target, window, level);
  return {
    damage,
    autoDamage: ROT_AUTO_DMG,
    bySlot: { ...ROT_BY_SLOT },
    boltDamage: ROT_BOLT_DMG,
    byType: { physical: ROT_BY_TYPE.physical, magic: ROT_BY_TYPE.magic, true: ROT_BY_TYPE.true },
    casts: JSON.parse(JSON.stringify(ROT_CAST_LOG)),
    autos: ROT_NAUTOS,
    autosIdeal: ROT_NAUTOS_IDEAL,
  };
}

const STYLE_HINT_TS: Record<string, string> = {
  "basic-attack": "attack speed, crit, on-hit and lethality; autos carry the damage",
  "ability-caster": "ability haste, penetration and big AD/AP ratios; abilities carry the damage",
  hybrid: "both matter: some attack speed alongside ability haste and penetration",
};

/** Auto-vs-ability classification for a custom build, mirroring the Python
 *  `attack_profile`: blend the simulated auto-share with the LLM asEfficiency
 *  cross-check, trusting the sim less where ability components are unmodeled. */
export function attackProfile(name: string, items: string[], runes: string[],
                              level = 15): AttackStyleLive | null {
  const st = resolveStats(name, level, items, runes);
  if (!st) return null;
  const total = rotation(name, st, TARGET_BRUISER, 8, level) || 1;
  const measured = Math.max(0, Math.min(1, ROT_AUTO_DMG / total));
  const fm = DATA.formulas[name] ?? {};
  const ase = fm.knowledge?.asEfficiency;
  const ab = fm.abilities ?? {};
  const unmodeled = Object.values(ab).reduce(
    (a: number, v: any) => a + (v.unmodeled?.length ?? 0), 0);
  let autoness = measured, quality = "measured-only";
  if (ase != null) {
    const knowAuto = Math.max(0, Math.min(1, (Number(ase) - 0.2) / 0.8));
    const w = 1 / (1 + unmodeled / 6);
    autoness = w * measured + (1 - w) * knowAuto;
    quality = Math.abs(measured - knowAuto) > 0.35 ? "flagged" : "ok";
  }
  const style = autoness >= 0.55 ? "basic-attack"
    : autoness <= 0.35 ? "ability-caster" : "hybrid";
  return { style, autoness: Math.round(autoness * 1000) / 1000,
    measuredAutoShare: Math.round(measured * 1000) / 1000,
    asEfficiency: ase ?? null, dataQuality: quality, buildHint: STYLE_HINT_TS[style] };
}

// Early-game weighting (mirrors Python): score a build across purchase stages,
// weighted toward the first 2-3 items that decide Wild Rift games.
const STAGE_PLAN: [number | null, number][] = [[1, 0.10], [2, 0.30], [3, 0.35], [4, 0.15], [5, 0.07], [6, 0.03]];
const PREFIX_LEVELS_TS = [8, 10, 12, 13, 14, 15];

function buildOrder(items: string[]): string[] {
  const o = [...items];
  return o.length >= 2 ? [o[0], o[o.length - 1], ...o.slice(1, -1)] : o;
}

function valueAt(name: string, items: string[], runes: string[], variant: string, level: number): number {
  const st = resolveStats(name, level, items, runes);
  if (!st) return 0;
  const burst3 = rotation(name, st, targetSquishy(level), 3, level);
  const dps8 = rotation(name, st, TARGET_BRUISER, 8, level) / 8;
  let shield = st.shield + st.shieldPctBonusHp * st.bonusHp + st.shieldPctMaxHp * st.hp;
  shield *= 1 + st.healShieldAmp;
  const mixed = mixedTaken(st);
  const ehp = (st.hp + shield) / mixed / (st.dr < 1 ? 1 - st.dr : 1);
  const sustain = st.vamp * dps8 * 8 + st.runeHealPerSec * 8 * (1 + st.healShieldAmp);
  let [wOff] = VARIANT_WEIGHTS[variant] ?? [0.6, 0.4];
  wOff = Math.max(0.15, Math.min(0.9, wOff + kitAdjust(name)));
  const off = BURSTY.has(variant) ? burst3 / REF_BURST : dps8 / REF_DPS;
  const deff = durabilityTerm(ehp, sustain);
  return 100 * (wOff * off + (1 - wOff) * deff) * Math.pow(buildEfficiency(name, items), EFFICIENCY_ALPHA);
}

function stagedScore(name: string, items: string[], runes: string[], variant: string): number {
  const order = buildOrder(items);
  let acc = 0, tw = 0;
  for (const [n, w] of STAGE_PLAN) {
    const prefix = n === null ? order : order.slice(0, Math.min(n, order.length));
    if (!prefix.length) continue;
    const lvl = PREFIX_LEVELS_TS[Math.min(prefix.length - 1, PREFIX_LEVELS_TS.length - 1)];
    acc += w * valueAt(name, prefix, runes, variant, lvl);
    tw += w;
  }
  return tw ? acc / tw : 0;
}

export function liveMetrics(name: string, items: string[], runes: string[],
                            variant: string, level = 15): LiveMetrics | null {
  const st = resolveStats(name, level, items, runes);
  if (!st) return null;
  const squishy = targetSquishy(level);
  const burst3 = rotation(name, st, squishy, 3, level);
  const dmg8 = rotation(name, st, TARGET_BRUISER, 8, level);
  const dps8 = dmg8 / 8;

  const need = squishy.hp * (1 - st.execute);
  let ttk: number | null = null;
  for (let t = 0.25; t <= 12; t += 0.25) {
    if (rotation(name, st, squishy, t, level) >= need) { ttk = t; break; }
  }
  let shield = st.shield + st.shieldPctBonusHp * st.bonusHp + st.shieldPctMaxHp * st.hp;
  shield *= 1 + st.healShieldAmp;
  const mixed = mixedTaken(st);
  const ehp = (st.hp + shield) / mixed / (st.dr < 1 ? 1 - st.dr : 1);
  const sustain = st.vamp * dmg8 + st.runeHealPerSec * 8 * (1 + st.healShieldAmp);

  const m = { burst3: Math.round(burst3), dps8: Math.round(dps8), ttk,
    ehp: Math.round(ehp), sustain: Math.round(sustain),
    ad: Math.round(st.ad), ap: Math.round(st.ap), hp: Math.round(st.hp),
    armor: Math.round(st.armor), mr: Math.round(st.mr),
    moveSpeed: Math.round(st.baseMs + st.bonusMs),
    attackSpeed: Math.round(st.as * 100) / 100, haste: Math.round(st.haste),
    crit: Math.round(st.crit * 100), mana: Math.round(st.mana) };

  // build-quality score is early-game-weighted across purchase stages
  const score = Math.round(stagedScore(name, items, runes, variant) * 10) / 10;
  return { ...m, score };
}

// ---- Full simulator readout (mirrors Python analyze_build / win_score) ----

function targetProfiles(level: number): Record<string, any> {
  return {
    adc: targetSquishy(level),
    mage: { hp: 2400, armor: 80, mr: 80, bonusHp: 500 },
    fighter: { hp: 3000, armor: 110, mr: 70, bonusHp: 1200 },
    bruiser: { hp: 3400, armor: 130, mr: 85, bonusHp: 1700 },
    tank: { hp: 5000, armor: 250, mr: 180, bonusHp: 3200 },
  };
}

const INCOMING_DPS: Record<string, number> = { adc: 900, bruiser: 650, tank: 400 };

function ttkOf(name: string, st: any, target: any, level: number, cap = 15): number | null {
  const need = target.hp * (1 - st.execute);
  for (let t = 0.25; t <= cap; t += 0.25)
    if (rotation(name, st, target, t, level) >= need) return Math.round(t * 100) / 100;
  return null;
}

function cleanLabel(label: string): string {
  let base = label.split(" x")[0];
  if (base.startsWith("[")) base = base.split("] ").slice(1).join("] ");
  return base ? base[0].toUpperCase() + base.slice(1) : base;
}

/** Full multi-dimensional readout for a custom build, matching the precomputed
 *  BuildAnalysis shape so the same SimReadout renders live in the customizer. */
/**
 * Share of incoming damage that gets through, against a 50/50 enemy split.
 *
 * Typed damage reduction is applied to its OWN half: Force of Nature cuts
 * magic damage by 20% and nothing else, so folding it into the all-damage term
 * would price it against physical damage it cannot touch. Mirrors
 * fight_engine._mixed_taken.
 */
function mixedTaken(st: any): number {
  const phys = 100 / (100 + st.armor) * (1 - (st.drPhys ?? 0));
  const magic = 100 / (100 + st.mr) * (1 - (st.drMagic ?? 0));
  return 0.5 * phys + 0.5 * magic;
}

export function analyzeBuild(name: string, items: string[], runes: string[],
                            level = 15): BuildAnalysis | null {
  const st = resolveStats(name, level, items, runes);
  if (!st) return null;
  const profs = targetProfiles(level);
  const bruiser = TARGET_BRUISER;

  // keys match the Python shape: "0.5","1.0","2.0","3.0"
  const burstK: Record<string, number> = {
    "0.5": Math.round(rotation(name, st, profs.adc, 0.5, level)),
    "1.0": Math.round(rotation(name, st, profs.adc, 1, level)),
    "2.0": Math.round(rotation(name, st, profs.adc, 2, level)),
    "3.0": Math.round(rotation(name, st, profs.adc, 3, level)),
  };
  const winDmg: Record<number, number> = {};
  for (const w of [3, 5, 10, 20]) winDmg[w] = rotation(name, st, bruiser, w, level);
  const dps: Record<string, number> = { "5": Math.round(winDmg[5] / 5), "10": Math.round(winDmg[10] / 10), "20": Math.round(winDmg[20] / 20) };

  const ttk: Record<string, number | null> = {};
  for (const [k, t] of Object.entries(profs)) ttk[k] = ttkOf(name, st, t, level);

  // composition over the 8s bruiser fight
  const tot = rotation(name, st, bruiser, 8, level) || 1;
  const bt = ROT_BY_TYPE, autoD = ROT_AUTO_DMG, clog = ROT_CAST_LOG;
  const nAutos = ROT_NAUTOS, nAutosIdeal = ROT_NAUTOS_IDEAL;
  const byTypePct = {
    physical: Math.round(100 * bt.physical / tot),
    magic: Math.round(100 * bt.magic / tot),
    true: Math.round(100 * bt.true / tot),
  };
  const bySource = { auto: Math.round(autoD), ability: Math.round(Math.max(0, tot - autoD)) };

  // per-ability from the parts is not exposed here; recompute a light byAbility
  // by ablation-free tagging is unnecessary for the card, so leave {} (filled by
  // the precomputed builds; live card doesn't show it).
  const byAbility: Record<string, number> = {};

  // ablation attribution
  const itemAttr: { slug: string; name: string; dmg: number }[] = [];
  for (const slug of items) {
    if (!DATA.items[slug]) continue;
    const sub = items.filter((s) => s !== slug);
    const st2 = resolveStats(name, level, sub, runes);
    const d2 = st2 ? rotation(name, st2, bruiser, 8, level) : tot;
    itemAttr.push({ slug, name: DATA.items[slug].name, dmg: Math.round(tot - d2) });
  }
  const runeAttr: { name: string; dmg: number }[] = [];
  for (const rn of runes) {
    const sub = runes.filter((r) => r !== rn);
    const st2 = resolveStats(name, level, items, sub);
    const d2 = st2 ? rotation(name, st2, bruiser, 8, level) : tot;
    runeAttr.push({ name: rn, dmg: Math.round(tot - d2) });
  }
  itemAttr.sort((a, b) => b.dmg - a.dmg);
  runeAttr.sort((a, b) => b.dmg - a.dmg);
  // re-run the 8s bruiser sim so the module stashes reflect the full build again
  rotation(name, st, bruiser, 8, level);

  // survivability + mitigation + gold efficiency
  let shieldVal = st.shield + st.shieldPctBonusHp * st.bonusHp + st.shieldPctMaxHp * st.hp;
  shieldVal *= 1 + st.healShieldAmp;
  // Typed damage reduction rides its own half here too, and this site knows
  // the enemy's ACTUAL damage split rather than assuming 50/50.
  const physTaken = 100 / (100 + st.armor) * (1 - (st.drPhys ?? 0));
  const magicTaken = 100 / (100 + st.mr) * (1 - (st.drMagic ?? 0));
  const dr = st.dr < 1 ? st.dr : 0.99;
  const ehp = Math.round((st.hp + shieldVal) / (0.5 * physTaken + 0.5 * magicTaken) / (1 - dr));
  const ehpSplit = {
    physical: Math.round((st.hp + shieldVal) / physTaken / (1 - dr)),
    magic: Math.round((st.hp + shieldVal) / magicTaken / (1 - dr)),
  };
  const survivalTime: Record<string, number | null> = {};
  for (const k of ["adc", "bruiser", "tank"]) survivalTime[k] = INCOMING_DPS[k] ? Math.round(100 * ehp / INCOMING_DPS[k]) / 100 : null;

  const phys8 = bt.physical;
  const healing = {
    lifesteal: Math.round(st.lifestealPct * phys8),
    omnivamp: Math.round(st.omnivampPct * tot),
    onHit: Math.round(st.healOnHit * nAutos),
    rune: Math.round(st.runeHealPerSec * 8 * (1 + st.healShieldAmp)),
    total: 0,
  };
  healing.total = healing.lifesteal + healing.omnivamp + healing.onHit + healing.rune;
  const reactive = st.shieldPctMaxHp > 0 || st.shieldPctBonusHp > 0;
  const shields = { value: Math.round(shieldVal), avgUptime: reactive ? 0.45 : (shieldVal ? 0.7 : 0), amp: Math.round(st.healShieldAmp * 100) };

  const rawIn = INCOMING_DPS.bruiser * 8, physRaw = rawIn * 0.5, magicRaw = rawIn * 0.5;
  const damagePrevented = {
    armor: Math.round(physRaw * (1 - physTaken)),
    mr: Math.round(magicRaw * (1 - magicTaken)),
    dr: Math.round((physRaw * physTaken + magicRaw * magicTaken) * dr),
    shield: Math.round(shieldVal),
    total: 0,
  };
  damagePrevented.total = damagePrevented.armor + damagePrevented.mr + damagePrevented.dr + damagePrevented.shield;

  const used = Object.values(clog).reduce((a, v) => a + v.casts, 0);
  const capC = Object.values(clog).reduce((a, v) => a + v.max, 0) || 1;
  const cooldownUtil = { efficiency: Math.round(100 * used / capC) };

  const perAuto = nAutos ? autoD / nAutos : 0;
  const ttkSq = ttk.adc;
  let overkill = 0;
  if (ttkSq) {
    const dealt = rotation(name, st, profs.adc, ttkSq, level);
    overkill = Math.round(Math.max(0, dealt - profs.adc.hp * (1 - st.execute)));
    rotation(name, st, bruiser, 8, level); // restore stashes
  }
  const damageLost = {
    autoUptimePct: Math.round(100 * nAutos / Math.max(1, nAutosIdeal)),
    autoDmgLost: Math.round(Math.max(0, nAutosIdeal - nAutos) * perAuto),
    overkill,
  };

  const gold = items.reduce((a, s) => a + (DATA.items[s]?.cost ?? 0), 0);
  const goldEff = {
    gold,
    dmgPerGold: gold ? Math.round(winDmg[3] / gold * 100) / 100 : null,
    ehpPerGold: gold ? Math.round(ehp / gold * 100) / 100 : null,
  };

  const analysis: BuildAnalysis = {
    winScore: 0, preset: "default", burst: burstK, dps, ttk, byTypePct, bySource,
    byAbility, items: itemAttr, runes: runeAttr, ehp, ehpSplit, survivalTime,
    goldEff, healing, shields, damagePrevented, cooldownUtil, damageLost,
  };
  const ws = winScore(analysis, "default", DATA.champions[name]?.class ?? "");
  analysis.winScore = ws.score;
  analysis.preset = ws.preset;
  return analysis;
}

const WIN_PRESETS: Record<string, Record<string, number>> = {
  assassin: { ttk: 0.30, dps: 0.10, burst: 0.35, surv: 0.15, heal: 0.05, util: 0.05 },
  adc: { ttk: 0.30, dps: 0.40, burst: 0.05, surv: 0.15, heal: 0.05, util: 0.05 },
  mage: { ttk: 0.25, dps: 0.20, burst: 0.35, surv: 0.10, heal: 0.05, util: 0.05 },
  bruiser: { ttk: 0.30, dps: 0.25, burst: 0.10, surv: 0.25, heal: 0.05, util: 0.05 },
  tank: { ttk: 0.10, dps: 0.15, burst: 0.05, surv: 0.50, heal: 0.10, util: 0.10 },
  default: { ttk: 0.40, dps: 0.25, burst: 0.15, surv: 0.10, heal: 0.05, util: 0.05 },
};
const CLASS_PRESET: Record<string, string> = {
  Assassin: "assassin", Marksman: "adc", Mage: "mage",
  Fighter: "bruiser", Tank: "tank", Support: "default",
};
const REF_TTK = 4, REF_SURV = 6, REF_HEAL = 1500;
/** Effective health past which durability stops paying. See durabilityTerm. */
const REF_DURABILITY_CUT = 14000;

/**
 * Survivability, as a SATURATING term rather than a linear one.
 *
 * An unbounded linear effective-health term means an optimiser can always buy
 * more score with more health, so it does: the engine's best Malphite build
 * was four lifeline shields stacked, each once per fight, several conditional,
 * all treated as permanently present and additive.
 *
 * What replaces it is minimum sufficient durability: stop paying for effective
 * health beyond what the reference fight demands. Surviving the fight is worth
 * everything; surviving it twice over is worth no more, so the rest of the
 * score has to be won with damage. The plateau above the cut is deliberate.
 *
 * The cut is its OWN constant rather than REF_SURV seconds against a reference
 * attacker. Expressed that way it came to 3,900 effective health, below the
 * squishiest build in the game, so this returned exactly 1.0 for every legal
 * five-item build and the defensive 40% of the score cancelled out of every
 * comparison. 14,000 was picked by sweeping it against captured top-50 builds.
 *
 * Mirrors fight_engine.durability_term, which carries the measurements and the
 * known limit for bruisers.
 */
function durabilityTerm(ehp: number, sustain: number): number {
  return Math.min(1, (ehp + 0.5 * sustain) / REF_DURABILITY_CUT);
}

export function winScore(a: BuildAnalysis, preset = "default", champClass = ""): { score: number; preset: string } {
  if (preset === "default" && champClass) preset = CLASS_PRESET[champClass] ?? "default";
  const w = WIN_PRESETS[preset] ?? WIN_PRESETS.default;
  const ttkB = a.ttk.bruiser, survB = a.survivalTime?.bruiser ?? 0;
  const sub: Record<string, number> = {
    ttk: ttkB ? REF_TTK / ttkB : 0,
    dps: (a.dps["10"] ?? 0) / REF_DPS,
    burst: (a.burst["3.0"] ?? 0) / REF_BURST,
    surv: (survB ?? 0) / REF_SURV,
    heal: (a.healing?.total ?? 0) / REF_HEAL,
    util: 0.5,
  };
  const score = Math.round(1000 * Object.keys(w).reduce((acc, k) => acc + w[k] * sub[k], 0)) / 10;
  return { score, preset };
}

// ---- Monte Carlo (mirrors Python monte_carlo / _ttk_stochastic) ----

/** Seeded PRNG (mulberry32) so a report is reproducible run-to-run. */
function mulberry32(seed: number) {
  let a = seed >>> 0;
  return () => {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function gauss(rng: () => number, mean: number, sd: number): number {
  const u = Math.max(1e-9, rng()), v = rng();
  return mean + sd * Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

/** One randomized time-to-kill: realized crit rate, auto misses and small
 *  timing jitter vary around the deterministic expectation. */
function ttkStochastic(name: string, st: any, target: any, level: number,
                       rng: () => number, cap = 15): number {
  const baseCrit = st.crit;
  const nRef = Math.max(1, Math.floor(cap * st.as));
  let realized = 0;
  if (baseCrit > 0) {
    const sd = Math.sqrt(Math.max(baseCrit * (1 - baseCrit) / nRef, 0));
    realized = Math.min(1, Math.max(0, gauss(rng, baseCrit, sd)));
  }
  const miss = rng() * 0.08;
  const jitter = 0.92 + rng() * 0.16;
  const trial = { ...st, crit: realized, as: st.as * (1 - miss) };
  const need = target.hp * (1 - st.execute);
  for (let i = 1; i <= Math.floor(cap / 0.25); i++) {
    const t = i * 0.25;
    if (rotation(name, trial, target, t * jitter, level) >= need) return Math.round(t * 1000) / 1000;
  }
  return cap;
}

export interface MonteCarloResult {
  target: string; trials: number;
  meanTtk: number; bestTtk: number; worstTtk: number;
  ci95: [number, number]; stdev: number;
  samples: number[];
}

/** Thousands of randomized fights -> a TTK distribution for one build. */
export function monteCarlo(name: string, items: string[], runes: string[],
                           opts: { targetKind?: string; trials?: number; level?: number } = {}): MonteCarloResult | null {
  const { targetKind = "bruiser", trials = 300, level = 15 } = opts;
  const st = resolveStats(name, level, items, runes);
  if (!st) return null;
  const target = targetProfiles(level)[targetKind] ?? TARGET_BRUISER;
  const rng = mulberry32(0xC0FFEE);
  const samples: number[] = [];
  for (let i = 0; i < trials; i++) samples.push(ttkStochastic(name, st, target, level, rng));
  samples.sort((a, b) => a - b);
  const mean = samples.reduce((a, b) => a + b, 0) / samples.length;
  const variance = samples.reduce((a, b) => a + (b - mean) ** 2, 0) / samples.length;
  const pct = (p: number) => samples[Math.min(samples.length - 1, Math.floor(p * samples.length))];
  return {
    target: targetKind, trials,
    meanTtk: Math.round(mean * 100) / 100,
    bestTtk: Math.round(samples[0] * 100) / 100,
    worstTtk: Math.round(samples[samples.length - 1] * 100) / 100,
    ci95: [Math.round(pct(0.025) * 100) / 100, Math.round(pct(0.975) * 100) / 100],
    stdev: Math.round(Math.sqrt(variance) * 1000) / 1000,
    samples,
  };
}

export interface MonteCarloCompare {
  a: MonteCarloResult; b: MonteCarloResult; winRateA: number;
}

/** Head-to-head: race two builds over the same randomized fights and report the
 *  fraction where build A's kill lands first. */
export function monteCarloCompare(
  buildA: { name: string; items: string[]; runes: string[] },
  buildB: { name: string; items: string[]; runes: string[] },
  opts: { targetKind?: string; trials?: number; level?: number } = {},
): MonteCarloCompare | null {
  const { targetKind = "bruiser", trials = 300, level = 15 } = opts;
  const a = monteCarlo(buildA.name, buildA.items, buildA.runes, opts);
  const b = monteCarlo(buildB.name, buildB.items, buildB.runes, opts);
  if (!a || !b) return null;
  const sa = resolveStats(buildA.name, level, buildA.items, buildA.runes);
  const sb = resolveStats(buildB.name, level, buildB.items, buildB.runes);
  if (!sa || !sb) return null;
  const target = targetProfiles(level)[targetKind] ?? TARGET_BRUISER;
  const rng = mulberry32(0xBEEF);
  let wins = 0;
  for (let i = 0; i < trials; i++) {
    const mine = ttkStochastic(buildA.name, sa, target, level, rng);
    const theirs = ttkStochastic(buildB.name, sb, target, level, rng);
    if (mine < theirs) wins++;
  }
  return { a, b, winRateA: Math.round(1000 * wins / trials) / 10 };
}

// ---- Engine-scored counter swaps vs a specific enemy comp ----

export interface CompScore {
  ttkCarry: number | null; // seconds to kill the enemy carry
  ehpVsComp: number;       // effective HP weighted by the enemy's AD/AP split
  score: number;           // combined, defense-leaning (counters are defensive)
}

export interface CompTarget {
  name: string; hp: number; armor: number; mr: number; bonusHp: number;
  // Same optional enrichment DuelTarget carries, and for the same reason: the
  // Counter Builder scores its swaps through scoreVsComp, so anti-heal,
  // shield-cut and crowd control have to be visible HERE too or the builder
  // recommends Morellonomicon and then ranks it with an engine that cannot see
  // healing. All default to zero, so an un-enriched comp scores as before.
  sustainPerSec?: number;
  shield?: number;
  ccDepth?: number;
  ccSeconds?: number;
  basicAttackDr?: number;
  asSlow?: number;
  stasisSec?: number;
}

/** Score a build against a specific enemy comp: how fast it kills their carry
 *  and how much effective HP it has versus their actual damage mix. */
export function scoreVsComp(name: string, items: string[], runes: string[],
                            opts: { carry: CompTarget; adShare: number; apShare: number; level?: number }): CompScore {
  const { carry, adShare, apShare, level = 15 } = opts;
  const st = resolveStats(name, level, items, runes);
  if (!st) return { ttkCarry: null, ehpVsComp: 0, score: 0 };
  // Mirrors duel(): the carry's shielding and sustain are part of what has to
  // be removed, and their crowd control is time this build is not acting.
  const foe = (carry.basicAttackDr || carry.asSlow)
    ? { ...st,
        autoDamageMult: 1 - (carry.basicAttackDr ?? 0),
        externalAsMult: 1 - (carry.asSlow ?? 0) }
    : st;
  const fixedNeed = carry.hp * (1 - st.execute)
    + (carry.shield ?? 0) * (1 - (st.shieldCut ?? 0));
  const healRate = (carry.sustainPerSec ?? 0) * (1 - (st.grievousWounds ?? 0));
  const ccLeft = Math.max(0, (carry.ccDepth ?? 0) - (st.ccRemoval ?? 0));
  const lockdown = ccLeft * (carry.ccSeconds ?? 1.5) * (1 - (st.tenacity ?? 0))
    + (carry.stasisSec ?? 0);
  let ttk: number | null = null;
  for (let t = 0.25; t <= 15; t += 0.25) {
    const acting = Math.max(0, t - lockdown);
    if (acting > 0
        && rotation(name, foe, carry, acting, level) >= fixedNeed + healRate * t) {
      ttk = Math.round(t * 100) / 100; break;
    }
  }
  let shield = st.shield + st.shieldPctBonusHp * st.bonusHp + st.shieldPctMaxHp * st.hp;
  shield *= 1 + st.healShieldAmp;
  // Typed damage reduction rides its own half here too, and this site knows
  // the enemy's ACTUAL damage split rather than assuming 50/50.
  const physTaken = 100 / (100 + st.armor) * (1 - (st.drPhys ?? 0));
  const magicTaken = 100 / (100 + st.mr) * (1 - (st.drMagic ?? 0));
  const taken = adShare * physTaken + apShare * magicTaken || 1;
  const dr = st.dr < 1 ? st.dr : 0.99;
  const ehpVsComp = Math.round((st.hp + shield) / taken / (1 - dr));
  const off = ttk ? REF_TTK / ttk : 0;
  // Same saturating curve as everywhere else. This one matters most: it is
  // what the Counter Builder ranks its swaps on, and an unbounded term here
  // means the answer to every enemy comp drifts toward "buy more health".
  const def = durabilityTerm(ehpVsComp, 0);
  return { ttkCarry: ttk, ehpVsComp, score: Math.round(1000 * (0.45 * off + 0.55 * def)) / 10 };
}

export interface CounterSwap {
  add: string; addName: string; remove: string; removeName: string;
  before: number; after: number; delta: number;
  ehpBefore: number; ehpAfter: number;
  ttkBefore: number | null; ttkAfter: number | null;
}

/** Best single item swap from a candidate counter pool: which counter to add and
 *  which current item it should replace, judged by the vs-comp score. Boots swap
 *  only for boots. Returns null when no candidate beats the current build. */
export function bestCounterSwap(name: string, items: string[], runes: string[],
                                candidates: string[],
                                opts: { carry: CompTarget; adShare: number; apShare: number; level?: number; protect?: string[] }): CounterSwap | null {
  const base = scoreVsComp(name, items, runes, opts);
  const meta = new Map(engineItems().map((i) => [i.slug, i]));
  const isBoots = (s: string) => meta.get(s)?.category === "Boots";
  const protect = new Set(opts.protect ?? []);
  let best: CounterSwap | null = null;
  for (const add of candidates) {
    if (items.includes(add) || !meta.has(add)) continue;
    for (const remove of items) {
      if (protect.has(remove)) continue; // never replace a core item
      if (isBoots(remove) !== isBoots(add)) continue;
      const next = items.map((s) => (s === remove ? add : s));
      if (buildIssues(next).length) continue;
      const s = scoreVsComp(name, next, runes, opts);
      const delta = Math.round((s.score - base.score) * 10) / 10;
      if (!best || delta > best.delta) {
        best = {
          add, addName: meta.get(add)?.name ?? add,
          remove, removeName: meta.get(remove)?.name ?? remove,
          before: base.score, after: s.score, delta,
          ehpBefore: base.ehpVsComp, ehpAfter: s.ehpVsComp,
          ttkBefore: base.ttkCarry, ttkAfter: s.ttkCarry,
        };
      }
    }
  }
  return best && best.delta > 0.1 ? best : null;
}

export interface AbilityInfo {
  slot: string; name: string; rank: number; dmg: number; type: string; scaling: string;
}

const STAT_LABEL: Record<string, string> = {
  ad: "AD", bonusAd: "bonus AD", ap: "AP", ownMaxHp: "max HP", ownBonusHp: "bonus HP",
  targetMaxHp: "target max HP", targetCurrentHp: "target HP", targetMissingHp: "missing HP",
  armor: "armor", mr: "MR", bonusMs: "bonus MS",
};

/** Per-ability damage and scaling at a given level, with the current build's
 *  stats — for the customizer's ability panel. Damage is raw (pre-mitigation). */
export function abilityBreakdown(name: string, items: string[], runes: string[], level: number): AbilityInfo[] {
  const st = resolveStats(name, level, items, runes);
  if (!st) return [];
  const f = DATA.formulas[name]?.abilities ?? {};
  const so = DATA.champions[name]?.skillOrder ?? {};
  const src: Record<string, number> = {
    ad: st.ad, bonusAd: st.bonusAd, ap: st.ap, ownMaxHp: st.hp, ownBonusHp: st.bonusHp,
    armor: st.armor, mr: st.mr, bonusMs: st.bonusMs,
    targetMaxHp: 0, targetCurrentHp: 0, targetMissingHp: 0,
  };
  const out: AbilityInfo[] = [];
  for (const slot of Object.keys(f).sort()) {
    const ab = f[slot];
    const comps = (ab.damage ?? []).filter((c: any) => !c.alt && !c.dropped && c.when !== "per auto");
    if (!comps.length) continue;
    const levelsTaken = (so[slot] ?? []).filter((lv: number) => lv <= level).length;
    const rank = so[slot] ? Math.max(0, levelsTaken - 1)
      : slot === "4" ? (level >= 13 ? 2 : level >= 9 ? 1 : 0)
      : Math.min(3, Math.max(0, Math.floor((level - 1) / 3)));
    if (so[slot] && levelsTaken === 0) continue; // not yet learned
    let dmg = 0; const scale = new Set<string>();
    for (const c of comps) {
      let val = scaleVal(c.base, rank, level);
      if (c.when === "dot total" && c.durationS) val *= c.durationS;
      for (const r of c.ratios ?? []) {
        const pct = scaleVal(r.pct ?? 0, rank, level);
        if (!pct) continue;
        val += (pct / 100) * (src[r.stat] ?? 0);
        scale.add(`${Math.round(pct)}% ${STAT_LABEL[r.stat] ?? r.stat}`);
      }
      val *= Math.max(1, Math.floor(rankVal(c.hits ?? 1, rank)) || 1);
      dmg += val;
    }
    out.push({ slot, name: ab.name ?? slot, rank: rank + 1, dmg: Math.round(dmg), type: comps[0].type, scaling: [...scale].join(" + ") });
  }
  return out;
}

/** Legality check for custom builds: mutex groups + duplicates. */
export function buildIssues(items: string[]): string[] {
  const out: string[] = [];
  const set = new Set(items);
  if (set.size !== items.length) out.push("duplicate item");
  for (const [gname, group] of Object.entries<any>(DATA.mutex)) {
    const hit = items.filter((s) => (group as string[]).includes(s));
    if (hit.length > 1)
      out.push(`${hit.map((s) => DATA.items[s]?.name ?? s).join(" + ")} share the '${gname}' passive`);
  }
  return out;
}

export interface ChampionBehavior {
  spellCastRate?: number; fightFrequency?: number; tradeFrequency?: number;
  objectiveDamage?: number; waveclear?: number; jungleClear?: number;
  roamFrequency?: number; avgFightLength?: number; confidence?: string;
}

/** The A3 behaviour model for a champion (0..1 per metric), or null. */
export function championBehavior(name: string): ChampionBehavior | null {
  const b = DATA.formulas[name]?.behavior;
  return b ? (b as ChampionBehavior) : null;
}

/**
 * Mean stated duration of one of this champion's hard-CC abilities, in seconds.
 * 82 champions state one in their ability text; the rest fall back to the
 * median of the 112 stated figures across the roster.
 */
export function championCcSeconds(name: string): number {
  return Number(DATA.champions[name]?.ccSeconds)
    || Number(DATA.ccMedianSeconds) || 1.5;
}

/**
 * Ally value a build provides over a fight: the healing and shielding it puts
 * on allies, plus the damage and mitigation its items hand them.
 *
 * A port of fight_engine.support_value. Without it this engine scores an
 * enchanter on her own damage and survival and picks nonsense, because every
 * support item looks like a weak stat stick. A self-heal is deliberately NOT
 * ally value: counting Swain's Demonic Ascension here gave him 255 points of
 * support he never provided.
 */
export function supportValue(name: string, items: string[], runes: string[] = [],
                             level = 13): number {
  const st = resolveStats(name, level, items, runes);
  if (!st) return 0;
  const amp = 1 + st.healShieldAmp;
  let total = 0;
  total += kitSustain(name, st, level, SUPPORT_WINDOW, "ally");
  total += st.runeAllyHealPerSec * SUPPORT_WINDOW * amp;
  total += st.allyShield * amp;
  for (const slug of items) {
    const fx = DATA.itemFx[slug] ?? {};
    const g = (k: string) => (k in fx ? lvlRange(fx[k], level) : 0);
    total += (g("allyHealFlat") + g("allyShieldFlat")) * 3 * amp;  // a few casts a fight
    // Percentage-of-max-health ally healing (Radiant Virtue). The item ally
    // path had flat keys only, so a percentage heal had nowhere to land.
    total += g("allyHealPctMaxHp") / 100 * st.hp * amp;
    total += g("allyOnHitFlatMagic") * ALLY_AUTOS;                 // Ardent Censer
    total += g("allyProcFlat") * 2;                                // Imperial Mandate
    total += g("allyApFlat") * AP_TO_ALLY_DAMAGE;                  // Staff of Flowing Water
    total += g("allyAdFlat") * AD_TO_ALLY_DAMAGE;
    total += ALLY_DAMAGE * g("allyAmpPct") / 100;
    total += ALLY_INCOMING * g("allyDrPct") / 100;                 // Knight's Vow
  }
  return total;
}

export function engineChampions(): string[] {
  return Object.keys(DATA.champions);
}
export function engineItems(): { slug: string; name: string; icon: string; cost: number; category: string }[] {
  return Object.entries<any>(DATA.items)
    .filter(([, v]) => v.category !== "Enchantment")
    .map(([slug, v]) => ({ slug, name: v.name, icon: v.icon, cost: v.cost, category: v.category }));
}
export function engineRunes(): { name: string; icon: string; tree: string; type: string; slot: number }[] {
  return Object.entries<any>(DATA.runes)
    .map(([name, v]) => ({ name, icon: v.icon, tree: v.tree, type: v.type, slot: v.slot }));
}

// ---------------------------------------------------------------------------
// Duel: what happens when this build fights that one
// ---------------------------------------------------------------------------

/**
 * Fold the fully-scaled contributions into the engine's stat block.
 *
 * build-scaling.ts owns what "fully scaled" means -- stacking items at max
 * stacks, ramping passives paid off -- and reports the deltas. Only the ones
 * that change damage are applied here; move speed and vamp do not move a
 * damage number and would just be noise.
 */
function applyScaling(name: string, items: string[], runes: string[],
                      level: number, st: any): void {
  const contributions =
    scaledBuildStats(name, items, level, runes, false)?.contributions ?? [];
  for (const c of contributions) {
    const amount = Number(c.amount) || 0;
    if (!amount) continue;
    switch (c.stat) {
      case "ad": st.bonusAd += amount; st.ad = st.baseAd + st.bonusAd; break;
      case "ap": st.ap += amount; break;
      case "haste": st.haste += amount; break;
      case "attackSpeedPct": st.baseAsPct += amount; break;
      case "hp": st.hp += amount; st.bonusHp += amount; break;
      default: break;
    }
  }
  if (contributions.some((c) => c.stat === "attackSpeedPct")) {
    st.as = Math.min(st.baseAs * (1 + st.baseAsPct / 100), AS_CAP);
  }
}

/** Seconds of fight the sustain rate below is linearised against. */
const SUSTAIN_REF_WINDOW = 8;
/** A fixed block to measure a kit’s own damage against, for damageDealt and
 *  target-scaled heals. Deliberately NOT the real opponent: this is sustain
 *  as a property of the champion, and feeding it whoever they happen to be
 *  fighting would make Aatrox heal more against a tank purely via resists. */
const SUSTAIN_REF_TARGET = { label: "ref", hp: 2600, armor: 90, mr: 60, bonusHp: 900 };

/**
 * Healing and shielding this kit produces for `audience` over a fight.
 *
 * A port of fight_engine.kit_heal, which the TS engine simply did not have: it
 * knew 85 champions carry a heal or shield component and could not evaluate
 * one, so an enemy's own sustain did not exist and Grievous Wounds -- exported
 * on five items and read by nothing -- had nothing to deny.
 */
export function kitSustain(name: string, st: any, level: number,
                           window: number, audience: "self" | "ally",
                           dmgBySlot?: Record<string, number>,
                           foe?: { hp: number }): number {
  const f = DATA.formulas[name]?.abilities ?? {};
  const amp = 1 + st.healShieldAmp;
  const hasteM = 100 / (100 + st.haste);
  const who = (DATA.healTargets?.[name] ?? {}) as Record<string, string>;
  let total = 0;
  for (const [slot, ab] of Object.entries<any>(f)) {
    // Hand-verified list; anything unlisted keeps the ally-facing read.
    const aud = who[slot] ?? "ally";
    if (aud !== "both" && aud !== audience) continue;
    const comps = (ab.defensive ?? []).filter(
      (c: any) => !c.alt && (c.kind === "heal" || c.kind === "shield"));
    if (!comps.length) continue;
    const cds = ab.cooldowns ?? [];
    const cd = (cds.length ? rankVal(cds, 3) : 8) * hasteM;
    const casts = slot === "4" ? 1
      : Math.max(1, 1 + Math.floor(window / Math.max(cd, 0.75)));
    for (const c of comps) {
      let v = scaleVal(c.base, 3, level);
      for (const r of c.ratios ?? []) {
        const pct = scaleVal(r.pct ?? 0, 3, level) / 100;
        const src: Record<string, number> = {
          ap: st.ap, ad: st.ad, bonusAd: st.bonusAd,
          ownMaxHp: st.hp, ownBonusHp: st.bonusHp, bonusHp: st.bonusHp,
          // Darius heals off MISSING health, which only exists once he has
          // been hurt.
          ownMissingHp: st.hp * MISSING_HP_IN_FIGHT,
          missingHp: st.hp * MISSING_HP_IN_FIGHT,
          // Amumu's Tantrum heals off his own resistances.
          armor: st.armor, mr: st.mr,
          // Aatrox, Viego and Rhaast heal for a share of the TARGET's health.
          // Nine components across eight champions used a ratio stat NEITHER
          // engine resolved, so they were silently worth their flat base and
          // nothing more, and Aatrox, whose entire sustain is one of them,
          // measured exactly zero.
          targetMaxHp: foe?.hp ?? 0,
          targetMissingHp: (foe?.hp ?? 0) * MISSING_HP_IN_FIGHT,
          // NOT resolved, on purpose: Yasuo's shield reads "(+100% Critical
          // Rate)", which is a multiplier on the shield and not an additive
          // ratio. The schema can only express the latter, so charging it as
          // one would be inventing a number. It keeps its flat base.
        };
        // Heals for a share of what THIS ability dealt. Deliberately the
        // ability's own damage, not the champion's total: reading Warwick's
        // passive percentage against everything he does gave him more healing
        // than his health bar.
        const source = r.stat === "damageDealt"
          ? (dmgBySlot?.[slot] ?? 0)
          : (src[r.stat] ?? 0);
        v += pct * source;
      }
      if (c.when === "dot total" && c.durationS) v *= Number(c.durationS);
      total += v * casts;
    }
  }
  return total * amp;
}

export interface DuelTarget {
  label: string;
  hp: number;
  armor: number;
  mr: number;
  /** Health from items only. Some kits scale off the bonus, not the total. */
  bonusHp: number;
  // ---- Everything below is optional and defaults to zero, so every target
  // built before these existed produces exactly the numbers it always did.
  /**
   * Health this champion restores per second of fight, from their own kit and
   * from healing items. Vamp is NOT in here: it needs their damage output,
   * which a one-way calculator does not have. mutualDuel adds it, because
   * there both sides are simulated.
   */
  sustainPerSec?: number;
  /** Shielding their kit puts up across a fight. */
  shield?: number;
  /** Hard-CC abilities in their kit, 0-4, from web/advisor/hardcc.py. */
  ccDepth?: number;
  /** Their tenacity, 0..1, which shortens the lockdown they inflict. */
  tenacity?: number;
  /** Plated Steelcaps: YOUR basic attacks deal this much less to them. */
  basicAttackDr?: number;
  /** Frozen Heart: their Chill cuts YOUR attack speed by this fraction. */
  asSlow?: number;
  /** Mean stated duration of one of their hard-CC abilities, in seconds. */
  ccSeconds?: number;
  /** Zhonya's / Seeker's: seconds they spend untargetable. */
  stasisSec?: number;
}

export interface DuelResult {
  target: DuelTarget;
  /** The champion's own opening sequence, as slots and "auto". */
  combo: string[];
  /** Seconds to take the target from full to zero, or null if it never gets there. */
  ttk: number | null;
  /** Damage in the window that killed, or the full cap window if it did not. */
  damage: number;
  autos: number;
  /** Autos the attack speed allowed, so "landed 6 of a possible 9" is visible. */
  autosIdeal: number;
  casts: { slot: string; name: string; casts: number }[];
  byType: { physical: number; magic: number; true: number };
  /** Damage past the kill: high overkill means the last cast was wasted. */
  overkill: number;
  dps: number;
  /**
   * Seconds of this fight spent unable to act: the target's hard CC, minus
   * what this build cleanses, shortened by tenacity, plus their stasis.
   */
  lockdown: number;
}

/** A champion as a target: their real defensive stats at a level and build. */
export function championTarget(name: string, level: number, items: string[],
                               runes: string[] = []): DuelTarget | null {
  const withBuild = resolveStats(name, level, items, runes);
  if (!withBuild) return null;
  // Bonus health is what the items added, so it has to be measured against the
  // same champion at the same level with nothing equipped.
  const naked = resolveStats(name, level, [], []);
  const st = withBuild;
  // Kit heals are linearised against a reference fight: cast counts are not
  // linear in window length, so this is a rate, not an exact integral.
  const refDmg = rotationDetail(name, st, SUSTAIN_REF_TARGET, SUSTAIN_REF_WINDOW, level);
  const kit = kitSustain(name, st, level, SUSTAIN_REF_WINDOW, "self",
                         refDmg.bySlot, SUSTAIN_REF_TARGET) / SUSTAIN_REF_WINDOW;
  const bonusHp = Math.max(0, withBuild.hp - (naked?.hp ?? withBuild.hp));
  return {
    label: name,
    hp: Math.round(withBuild.hp),
    armor: Math.round(withBuild.armor),
    mr: Math.round(withBuild.mr),
    bonusHp: Math.round(bonusHp),
    // Their own sustain, so an attacker's Grievous Wounds finally has
    // something to deny. Vamp is excluded on purpose -- see DuelTarget.
    sustainPerSec: Math.max(0, kit + st.runeHealPerSec + st.healOnHit * st.as),
    // Item shielding, so a shield-cut item has something to cut. Sterak's,
    // Maw, Kaenic Rookern and Guardian Angel's revive all land here.
    shield: Math.max(0, st.shield + st.shieldPctBonusHp * bonusHp
                        + st.shieldPctMaxHp * withBuild.hp),
    ccDepth: Number(DATA.champions[name]?.ccDepth) || 0,
    // 82 champions state a duration in their ability text; the rest fall back
    // to the corpus median of those 112 stated figures.
    ccSeconds: Number(DATA.champions[name]?.ccSeconds)
      || Number(DATA.ccMedianSeconds) || 1.5,
    stasisSec: st.stasisSec ?? 0,
    tenacity: st.tenacity ?? 0,
    basicAttackDr: st.basicAttackDr ?? 0,
    asSlow: st.targetAsSlow ?? 0,
  };
}

/** A plain practice-tool dummy: no build, only the numbers you give it. */
export function dummyTarget(hp: number, armor = 0, mr = 0): DuelTarget {
  return { label: "Practice dummy", hp, armor, mr, bonusHp: 0 };
}

/**
 * Fight a target with a build and report what it took.
 *
 * This is a DAMAGE CALCULATOR against a stationary target, not a duel: the
 * target does not move, dodge, heal, itemise reactively or fight back. It is
 * the practice-tool dummy players already know, given a real champion's
 * defensive stats. Presenting it as anything more would turn every modelling
 * gap into a bug report.
 */
export function duel(name: string, items: string[], runes: string[],
                     target: DuelTarget, level = 15, cap = 20,
                     scaled = false): DuelResult | null {
  const st = resolveStats(name, level, items, runes);
  if (!st) return null;
  // "Fully scaled" is not a display mode: stacking items and ramping passives
  // genuinely change how hard a build hits, so the fight has to see them too.
  // A build shown as fully scaled that then fights at its guaranteed stats
  // would be quietly contradicting the panel directly above it.
  if (scaled) applyScaling(name, items, runes, level, st);

  // What the target's own build does to MY output. Both default to no change,
  // so a target built before these fields existed fights exactly as before.
  const foe = (target.basicAttackDr || target.asSlow)
    ? { ...st,
        autoDamageMult: 1 - (target.basicAttackDr ?? 0),
        externalAsMult: 1 - (target.asSlow ?? 0) }
    : st;

  // Health that has to be removed BEFORE their sustain is counted: the bar
  // itself, less any execute, plus shielding my build cannot strip.
  const fixedNeed = target.hp * (1 - (st.execute ?? 0))
    + (target.shield ?? 0) * (1 - (st.shieldCut ?? 0));
  // ...and the part that grows with the fight, because a target who heals is
  // a moving target. This is what Grievous Wounds is for.
  const healRate = (target.sustainPerSec ?? 0) * (1 - (st.grievousWounds ?? 0));

  // CROWD CONTROL, as dead time.
  //
  // The engine had no concept of it anywhere: zero references to stun, root,
  // knockup, stasis, spell shield, cleanse or tenacity across 1821 lines. So
  // Mercury's Treads was health and magic resist, Legend: Tenacity was inert,
  // and Banshee's, Quicksilver, Mercurial and Sterak's bought nothing at all.
  //
  // The honest minimum is that lockdown is time you are not acting. Each of
  // the target's hard-CC abilities lands once, for the duration its own text
  // states; the cleanses and spell shields in this build remove that many
  // instances outright; tenacity shortens what is left; and their stasis is
  // added on top, because an untargetable enemy is dead time for the same
  // reason. Hard CC only -- slows are deliberately excluded, matching
  // web/advisor/hardcc.py, because a slow is not what tenacity is for.
  const ccLeft = Math.max(0, (target.ccDepth ?? 0) - (st.ccRemoval ?? 0));
  const lockdown = ccLeft * (target.ccSeconds ?? 1.5) * (1 - (st.tenacity ?? 0))
    + (target.stasisSec ?? 0);

  let ttk: number | null = null;
  // 0.25s steps match ttkOf, so this agrees with the number shown elsewhere.
  for (let t = 0.25; t <= cap; t += 0.25) {
    // At wall-clock t this champion has only been ACTING for t - lockdown.
    const acting = Math.max(0, t - lockdown);
    if (acting > 0
        && rotation(name, foe, target, acting, level) >= fixedNeed + healRate * t) {
      ttk = Math.round(t * 100) / 100;
      break;
    }
  }

  const window = ttk ?? cap;
  const acting = Math.max(0.25, window - lockdown);
  const need = fixedNeed + healRate * window;
  const detail = rotationDetail(name, foe, target, acting, level);
  const casts = Object.entries(detail.casts)
    .map(([slot, v]) => ({ slot, name: v.name, casts: v.casts }))
    .filter((c) => c.casts > 0)
    .sort((a, b) => a.slot.localeCompare(b.slot));

  return {
    target,
    // The rotation the champion is actually meant to use, which the data
    // already carries for 137 champions and nothing was showing.
    combo: (DATA.formulas[name]?.combo ?? []) as string[],
    ttk,
    damage: Math.round(detail.damage),
    autos: detail.autos,
    autosIdeal: detail.autosIdeal,
    casts,
    byType: {
      physical: Math.round(detail.byType.physical),
      magic: Math.round(detail.byType.magic),
      true: Math.round(detail.byType.true),
    },
    overkill: Math.max(0, Math.round(detail.damage - need)),
    // Damage per second of WALL CLOCK, not per second of acting: a fight you
    // spent half of stunned really did take that long.
    dps: Math.round(detail.damage / window),
    lockdown: Math.round(lockdown * 100) / 100,
  };
}

export interface MutualDuelResult {
  /** Your rotation against them, exactly as the one-sided duel reports it. */
  you: DuelResult;
  /** Their rotation against you, same calculator pointed the other way. */
  them: DuelResult;
  /**
   * "you" or "them": that side's kill lands first. "trade": both kills land
   * inside the same quarter-second tick, so the fight is decided by whoever
   * actually engages first, and saying anything more confident would be
   * inventing precision the model does not have. "stalemate": neither
   * rotation reaches a kill inside the window.
   */
  verdict: "you" | "them" | "trade" | "stalemate";
  /** Seconds between the two kill clocks when both sides would get there. */
  margin: number | null;
  /** Winner's remaining health fraction (0..1) at the moment the loser dies. */
  survivorHp: number | null;
}

/**
 * Both champions run their combo at once, and the clocks race.
 *
 * The one-sided duel answers "how fast do I kill a target that stands still".
 * This runs that same calculator in both directions and compares the two kill
 * times, which is the honest version of "the enemy fights back": nobody is
 * dodging, kiting, healing or holding cooldowns in either direction, so the
 * symmetry is fair and every number in it is one the one-sided panel already
 * defends.
 *
 * Sequencing, which is the whole subtlety: a combo that kills at 3.2s beats a
 * combo that kills at 5.4s regardless of order, so by default both rotations
 * start at t=0 and the smaller clock simply wins. `headStart` shifts the OTHER
 * side's clock later by that many seconds (positive = A engaged first) for the
 * cases where the caller wants initiative made explicit. When the two clocks
 * land within one 0.25s tick of each other the verdict is "trade", because at
 * that distance the model cannot tell you who dies -- the engage does.
 */
export function mutualDuel(
  aName: string, aItems: string[], aRunes: string[],
  bName: string, bItems: string[], bRunes: string[],
  level = 15, cap = 20, scaled = false, headStart = 0,
): MutualDuelResult | null {
  const targetB = championTarget(bName, level, bItems, bRunes);
  const targetA = championTarget(aName, level, aItems, aRunes);
  if (!targetA || !targetB) return null;
  // The same scaling switch applies to both sides: a fully-scaled build racing
  // a guaranteed-stats build would be comparing two different moments in time.
  const you = duel(aName, aItems, aRunes, targetB, level, cap, scaled);
  const them = duel(bName, bItems, bRunes, targetA, level, cap, scaled);
  if (!you || !them) return null;

  // Kill CLOCKS, not kill times: the side that engaged late has its whole
  // rotation shifted, so its kill lands later on the shared clock.
  const yourClock = you.ttk == null ? null : you.ttk + Math.max(0, -headStart);
  const theirClock = them.ttk == null ? null : them.ttk + Math.max(0, headStart);

  let verdict: MutualDuelResult["verdict"];
  let margin: number | null = null;
  if (yourClock == null && theirClock == null) verdict = "stalemate";
  else if (theirClock == null) verdict = "you";
  else if (yourClock == null) verdict = "them";
  else {
    margin = Math.round(Math.abs(yourClock - theirClock) * 100) / 100;
    verdict = margin <= 0.25 ? "trade" : yourClock < theirClock ? "you" : "them";
  }

  // How much health the winner keeps: the loser's rotation ran only until the
  // winner's kill landed, minus any time the loser lost to a late engage.
  let survivorHp: number | null = null;
  if (verdict === "you" || verdict === "them") {
    const winClock = (verdict === "you" ? yourClock : theirClock) as number;
    const loserDelay = verdict === "you" ? Math.max(0, headStart) : Math.max(0, -headStart);
    const fought = winClock - loserDelay;
    const winnerTarget = verdict === "you" ? targetA : targetB;
    let dealt = 0;
    if (fought >= 0.25) {
      const partial = verdict === "you"
        ? duel(bName, bItems, bRunes, targetA, level, fought, scaled)
        : duel(aName, aItems, aRunes, targetB, level, fought, scaled);
      dealt = partial?.damage ?? 0;
    }
    survivorHp = Math.max(0, Math.round(((winnerTarget.hp - dealt) / winnerTarget.hp) * 1000) / 1000);
  }

  return { you, them, verdict, margin, survivorHp };
}
