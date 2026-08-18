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
  "armor", "mr", "dotPctMaxHp"];
const out: Record<string, Record<string, number>> = {};
for (const [champ, items, runes] of battery) {
  const st = resolveStats(champ, 15, items, runes);
  out[`${champ}|${items.join("+")}`] = Object.fromEntries(
    FIELDS.map((f) => [f, Math.round((Number(st?.[f]) || 0) * 10000) / 10000]));
}
fs.writeFileSync(path.join(ROOT, "scratch_ts_stats.json"), JSON.stringify(out, null, 1));
console.log("ts side:", Object.keys(out).length, "cases");
