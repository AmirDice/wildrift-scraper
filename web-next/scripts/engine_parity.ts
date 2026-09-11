/** TS half of scripts/engine_parity.py -- resolves the shared battery and
 *  writes the stats for the Python side to diff. Run via the Python script. */
import { resolveStats } from "../src/lib/engine";
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
  "ccRemoval", "stasisSec"];
const out: Record<string, Record<string, number>> = {};
for (const [champ, items, runes] of battery) {
  const st = resolveStats(champ, 15, items, runes);
  out[`${champ}|${items.join("+")}|${runes.join("+")}`] = Object.fromEntries(
    FIELDS.map((f) => [f, Math.round((Number(st?.[f]) || 0) * 10000) / 10000]));
}
fs.writeFileSync(path.join(ROOT, "scratch_ts_stats.json"), JSON.stringify(out, null, 1));
console.log("ts side:", Object.keys(out).length, "cases");
