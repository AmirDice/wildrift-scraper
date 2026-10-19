// Run: node scripts/test_meta_global.cjs (from web-next).
// Use the installed compiler so this test needs no additional dependencies.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const Module = require("node:module");
const ts = require("typescript");
const root = path.resolve(__dirname, "..");
const resolve = Module._resolveFilename;
Module._resolveFilename = function (request, ...args) {
  return resolve.call(this, request.startsWith("@/") ? path.join(root, "src", request.slice(2)) : request, ...args);
};
require.extensions[".ts"] = (module, filename) => {
  const source = fs.readFileSync(filename, "utf8");
  module._compile(ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true,
  } }).outputText, filename);
};
const { combineUsage, globalUsage, isMinorRune, leastUsedRows, finishedItemRows } = require("../src/lib/global-usage.ts");
const { getGlobalChampions } = require("../src/lib/cn.ts");
const { metaHeadline, tierDistribution } = require("../src/lib/meta-stats.ts");
const source = (count, games, wrGames) => ({
  nPlayers: count, nBuilds: count, nChampions: 1, generatedAt: "2026-10-16",
  champions: { nilah: {} },
  itemAll: [{ name: "Test item", slug: "test", count, games, wrGames, wr: null }],
  treeMeta: [], keystoneAll: [], minorMeta: [], spellAll: [{ pair: "Flash + Smite", count }],
});
const combined = combineUsage([source(10, 100, 6000), source(1, 900, 45000)]);
assert.equal(combined.itemAll[0].count, 11);
assert.equal(combined.itemAll[0].wr, 51); // game weights, NOT mean 55 or build-weighted 59.1
assert.equal(combined.nChampions, 1);
assert.equal(combined.spellMeta[0].count, 11);
assert.equal(combineUsage([source(2, 199, 10000)]).itemAll[0].wr, null);
assert.equal(combineUsage([source(2, 200, 10000)]).itemAll[0].wr, 50);
assert.throws(() => combineUsage([]));
assert.throws(() => combineUsage([source(1, undefined, undefined)]), /Rebuild/);
assert.throws(() => combineUsage([source(1, 100, 11000)]), /Rebuild/);
const catalogue = require("../../data/wrmeta_runes.json");
const polluted = source(1, 200, 10000);
polluted.minorMeta = catalogue.filter((r) => r.type === "Keystone")
  .map((r) => ({ ...r, count: 1, games: 200, wrGames: 10000, wr: 50 }));
polluted.minorMeta.push({ name: "Brutal", tree: "Precision", count: 7, games: 200, wrGames: 10000, wr: 50 });
assert.deepEqual(combineUsage([polluted]).minorMeta.map((r) => r.name), ["Brutal"]);
const unordered = [{ name: "Zulu", count: 3 }, { name: "Alpha", count: 3 }, { name: "Zero", count: 0 }, { name: "First", count: 1 }];
assert.deepEqual(leastUsedRows(unordered, 3).map((r) => r.name), ["First", "Alpha", "Zulu"]);
assert.equal(unordered[0].name, "Zulu"); // sorting must not mutate cached source data
const pulses = ["ladder_pulse.json", "ladder_pulse_na.json", "ladder_pulse_cn.json"]
  .map((name) => require(path.join(root, "src/data", name)));
const usage = globalUsage();
assert.equal(usage.nBuilds, pulses.reduce((n, p) => n + p.nBuilds, 0));
for (const key of ["treeMeta", "keystoneAll", "minorMeta", "itemAll"]) {
  assert.equal(usage[key].reduce((n, r) => n + r.count, 0),
    pulses.reduce((n, p) => n + p[key].filter((r) => key !== "minorMeta" || isMinorRune(r))
      .reduce((s, r) => s + r.count, 0), 0));
}
for (const row of usage.minorMeta) {
  assert.equal(catalogue.find((r) => r.name === row.name)?.type, "Minor");
  assert.equal(row.count, pulses.reduce((n, p) => n + p.minorMeta
    .filter((r) => r.name === row.name && isMinorRune(r)).reduce((s, r) => s + r.count, 0), 0));
}
const finished = finishedItemRows(usage.itemAll);
const itemCatalogue = require("../src/data/items.json");
assert(finished.length > 10);
assert(finished.every((r) => !itemCatalogue.find((i) => i.slug === r.slug).categories.includes("MidTier")));
assert(finished.every((r) => !itemCatalogue.find((i) => i.slug === r.slug).removedIn));
assert(!finished.some((r) => ["magnetic-blaster", "searing-crown", "soul-transfer"].includes(r.slug)));
const leastItems = leastUsedRows(finished, 10);
assert.equal(leastItems[0].count, Math.min(...finished.filter((r) => r.count > 0).map((r) => r.count)));
for (const row of leastItems) {
  assert.equal(row.count, pulses.reduce((n, p) => n + (p.itemAll.find((r) => r.slug === row.slug)?.count ?? 0), 0));
}
const champs = getGlobalChampions();
assert.equal(metaHeadline().nChampions, champs.length);
assert.equal(tierDistribution().reduce((n, t) => n + t.count, 0), champs.length);
for (const champ of champs) {
  const boards = ["site.json", "site_na.json", "site_cn.json"]
    .map((name) => require(path.join(root, "src/data", name)).champions.find((c) => c.slug === champ.slug))
    .filter((c) => c && Number.isFinite(c.wr));
  assert.equal(champ.globalParts, boards.length);
  assert.equal(champ.wr, Math.round(boards.reduce((n, c) => n + c.wr, 0) / boards.length * 10) / 10);
}
if (require.main === module) console.log(JSON.stringify({ result: "PASS", champions: champs.length,
  globalBuilds: usage.nBuilds, headline: metaHeadline(), topItems: usage.itemAll.slice(0, 3),
  leastMinors: leastUsedRows(usage.minorMeta, 8).map(({ name, count }) => ({ name, count })),
  leastItems: leastItems.map(({ name, count }) => ({ name, count })),
}, null, 2));
