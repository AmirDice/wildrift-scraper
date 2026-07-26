import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

const ROOT = resolve(import.meta.dirname, "..");
const readJson = async (path) => JSON.parse(await readFile(resolve(ROOT, path), "utf8"));
const close = (actual, expected, tolerance = 0.011) => Math.abs(actual - expected) <= tolerance;
const assertClose = (label, actual, expected, tolerance) => {
  if (!close(actual, expected, tolerance)) throw new Error(`${label}: expected ${expected}, received ${actual}`);
};

const items = await readJson("web-next/src/data/items.json");
const rules = await readJson("web-next/src/data/stat_rules.json");
const itemBySlug = new Map(items.map((item) => [item.slug, item]));
const itemStat = (slugs, stat) => slugs.reduce((sum, slug) => sum + Number(itemBySlug.get(slug)?.stats?.[stat]?.value ?? 0), 0);
const at15 = (champion, stat) => {
  const value = rules.champions[champion].baseStats[stat];
  return value.base + value.perLevel * 14;
};

const pantheon = ["trinity-force", "blade-of-the-ruined-king", "lord-dominiks-regard", "duskblade-of-draktharr", "kaenic-rookern", "armorcrusher-boots"];
assertClose("Pantheon AD", at15("Pantheon", "ad") + itemStat(pantheon, "ad"), 284.4);
assertClose("Pantheon mana", at15("Pantheon", "mana"), 882);
assertClose("Pantheon armor", at15("Pantheon", "armor"), 117.8);
assertClose("Pantheon attack speed", 1.01 + rules.champions.Pantheon.statRules.attackSpeedRatio * itemStat(pantheon, "attackSpeed") / 100, 1.439);
assertClose("Pantheon health regen", at15("Pantheon", "hpRegen") * (1 + itemStat(pantheon, "hpRegen") / 100), 38);
assertClose("Pantheon mana regen", at15("Pantheon", "manaRegen"), 22);
assertClose("Pantheon percent armor penetration", itemStat(pantheon, "physicalPen") + 30, 72);
assertClose("Pantheon magic vamp", itemStat(pantheon, "omnivamp"), 10);

const lucian = ["essence-reaver", "infinity-edge", "lord-dominiks-regard", "duskblade-of-draktharr", "the-collector", "immortal-treads"];
assertClose("Lucian AD", 114 + itemStat(lucian, "ad") + 12, 356);
assertClose("Lucian mana", at15("Lucian", "mana"), 1076);
assertClose("Lucian magic resist", at15("Lucian", "mr"), 51);
assertClose("Lucian health regen", at15("Lucian", "hpRegen"), 21);
assertClose("Lucian mana regen", at15("Lucian", "manaRegen"), 28);
assertClose("Lucian critical damage", rules.items["infinity-edge"].always[0].set, 205);
assertClose("Lucian magic vamp", itemStat(lucian, "omnivamp"), 5);

console.log("Verified Pantheon standard and Lucian crit stat fixtures passed.");
