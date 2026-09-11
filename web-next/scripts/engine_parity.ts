/** TS half of scripts/engine_parity.py -- resolves the shared battery and
 *  writes the stats for the Python side to diff. Run via the Python script. */
import { resolveStats, rotationDetail, supportValue, championTarget, duel,
         scoreVsComp } from "../src/lib/engine";
import * as fs from "fs";
import * as path from "path";

const ROOT = path.resolve(__dirname, "..", "..");
const battery: [string, string[], string[]][] = JSON.parse(
  fs.readFileSync(path.join(ROOT, "scripts", "engine_parity_battery.json"), "utf-8"));
const FIELDS = ["ap", "bonusAd", "hp", "bonusHp", "mana", "haste", "crit", "critMult",
  "onHitPhys", "onHitMagic", "onHitPctMaxHp", "onHitPctCurrentHp",
  "mrShred", "mrShredFlat", "spellbladeApPct", "spellbladeMagic",
  "cleaveFlat", "cleavePctBonusHp", "healShieldAmp", "shieldPctMaxHp", "apAmp",
  "armor", "mr", "dotPctMaxHp", "extraOnHitApplications", "as", "baseAs",
  // See the note on the Python half: these cover penetration, vamp and tenacity,
  // where the two engines silently disagreed on every single item.
  "flatPen", "pctPen", "flatMagicPen", "pctMagicPen",
  "vamp", "lifestealPct", "omnivampPct", "tenacity",
  "dr", "giant", "execute", "armorShred",
  "grievousWounds", "shieldCut", "basicAttackDr", "targetAsSlow",
  "ccRemoval", "stasisSec", "drMagic", "drPhys", "ehp",
  // See the note on the Python half: the damage path itself, not only the
  // stats feeding it.
  "rot8", "rot8Autos",
  // See the Python half: `bonusAd` was compared and `ad` was not.
  "ad", "baseAd", "baseAs",
  "runeAllyHealPerSec", "allyShield", "shield", "support", "rot8Bolts",
  // See the Python half: the fight surface, ported to Python on 2026-09-11.
  "tgtHp", "tgtArmor", "tgtMr", "tgtBonusHp", "tgtSustain", "tgtShield",
  "tgtCcDepth", "tgtCcSeconds",
  "duelTtk", "duelDamage", "duelDps", "duelLockdown", "duelOverkill",
  "duelAutos", "duelPhys", "duelMagic",
  "compTtk", "compEhp", "compScore"];

/** Must match PARITY_TARGET in scripts/engine_parity.py. */
const PARITY_TARGET = { label: "parity", hp: 2600, armor: 90, mr: 60, bonusHp: 900 };
/** Must match DUEL_FOE in scripts/engine_parity.py. */
const DUEL_FOE = { label: "foe", hp: 4100, armor: 180, mr: 70, bonusHp: 1400,
  sustainPerSec: 90, shield: 1100, ccDepth: 2, ccSeconds: 1.5, stasisSec: 0,
  tenacity: 0, basicAttackDr: 0.12, asSlow: 0.15 };
/** Must match COMP_CARRY in scripts/engine_parity.py. */
const COMP_CARRY = { name: "carry", hp: 2900, armor: 95, mr: 60, bonusHp: 950,
  sustainPerSec: 40, shield: 300, ccDepth: 1, ccSeconds: 1.5,
  basicAttackDr: 0, asSlow: 0, stasisSec: 0 };
const NO_KILL = -1;
const out: Record<string, Record<string, number>> = {};
for (const [champ, items, runes] of battery) {
  const st: any = resolveStats(champ, 15, items, runes);
  if (st) {
    const rot = rotationDetail(champ, st, PARITY_TARGET, 8, 15);
    st.rot8 = Math.round(rot.damage * 100) / 100;
    st.rot8Autos = Math.round(rot.autoDamage * 100) / 100;
    st.support = Math.round(supportValue(champ, items, runes, 15) * 100) / 100;
    const sh = (st.shield + st.shieldPctBonusHp * st.bonusHp
      + st.shieldPctMaxHp * st.hp) * (1 + st.healShieldAmp);
    const phys = 100 / (100 + st.armor) * (1 - (st.drPhys ?? 0));
    const magic = 100 / (100 + st.mr) * (1 - (st.drMagic ?? 0));
    const dr = st.dr < 1 ? st.dr : 0.99;
    st.ehp = Math.round((st.hp + sh) / (0.5 * phys + 0.5 * magic) / (1 - dr) * 100) / 100;
    st.rot8Bolts = Math.round(rot.boltDamage * 100) / 100;
    // ---- the fight surface ----------------------------------------------
    const tgt: any = championTarget(champ, 15, items, runes) ?? {};
    const d: any = duel(champ, items, runes, { ...DUEL_FOE }, 15) ?? {};
    const comp: any = scoreVsComp(champ, items, runes,
      { carry: { ...COMP_CARRY }, adShare: 0.6, apShare: 0.4, level: 15 });
    st.tgtHp = tgt.hp ?? 0; st.tgtArmor = tgt.armor ?? 0; st.tgtMr = tgt.mr ?? 0;
    st.tgtBonusHp = tgt.bonusHp ?? 0;
    st.tgtSustain = Math.round((tgt.sustainPerSec ?? 0) * 100) / 100;
    st.tgtShield = Math.round((tgt.shield ?? 0) * 100) / 100;
    st.tgtCcDepth = tgt.ccDepth ?? 0; st.tgtCcSeconds = tgt.ccSeconds ?? 0;
    st.duelTtk = d.ttk == null ? NO_KILL : d.ttk;
    st.duelDamage = d.damage ?? 0; st.duelDps = d.dps ?? 0;
    st.duelLockdown = d.lockdown ?? 0; st.duelOverkill = d.overkill ?? 0;
    st.duelAutos = d.autos ?? 0;
    st.duelPhys = d.byType?.physical ?? 0; st.duelMagic = d.byType?.magic ?? 0;
    st.compTtk = comp.ttkCarry == null ? NO_KILL : comp.ttkCarry;
    st.compEhp = comp.ehpVsComp ?? 0; st.compScore = comp.score ?? 0;
  }
  out[`${champ}|${items.join("+")}|${runes.join("+")}`] = Object.fromEntries(
    FIELDS.map((f) => [f, Math.round((Number(st?.[f]) || 0) * 10000) / 10000]));
}
fs.writeFileSync(path.join(ROOT, "scratch_ts_stats.json"), JSON.stringify(out, null, 1));
console.log("ts side:", Object.keys(out).length, "cases");
