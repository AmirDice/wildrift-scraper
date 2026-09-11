/** TS half of scripts/engine_parity.py -- resolves the shared battery and
 *  writes the stats for the Python side to diff. Run via the Python script. */
import { resolveStats, rotationDetail, supportValue } from "../src/lib/engine";
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
  "runeAllyHealPerSec", "allyShield", "shield", "support", "rot8Bolts"];

/** Must match PARITY_TARGET in scripts/engine_parity.py. */
const PARITY_TARGET = { label: "parity", hp: 2600, armor: 90, mr: 60, bonusHp: 900 };
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
  }
  out[`${champ}|${items.join("+")}|${runes.join("+")}`] = Object.fromEntries(
    FIELDS.map((f) => [f, Math.round((Number(st?.[f]) || 0) * 10000) / 10000]));
}
fs.writeFileSync(path.join(ROOT, "scratch_ts_stats.json"), JSON.stringify(out, null, 1));
console.log("ts side:", Object.keys(out).length, "cases");
