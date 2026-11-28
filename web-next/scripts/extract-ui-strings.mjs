// List every translatable UI key: <T>{"..."}</T> and t("...") calls.
//   node scripts/extract-ui-strings.mjs > keys.json
import fs from "node:fs";
import path from "node:path";

const keys = new Set();
const T_RE = /<T(?:\s+vars=\{\{[^}]*\}\})?>\{"((?:[^"\\]|\\.)*)"\}<\/T>/g;
const CALL_RE = /\bt\("((?:[^"\\]|\\.)*)"/g;

const walk = (dir) => {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p);
    else if (/\.(tsx|ts)$/.test(e.name)) {
      const s = fs.readFileSync(p, "utf8");
      for (const m of s.matchAll(T_RE)) keys.add(JSON.parse(`"${m[1]}"`));
      for (const m of s.matchAll(CALL_RE)) keys.add(JSON.parse(`"${m[1]}"`));
    }
  }
};
walk("src");
// Keys passed to t() as variables, so no regex sees them: roles, regions,
// lane names and difficulty labels.
for (const k of ["Baron", "Jungle", "Mid", "Dragon", "Support", "Baron Lane", "Mid Lane", "Dragon Lane",
  "EU", "NA", "China", "Easy", "Moderate", "Hard", "Very Hard", "Overview", "Runes", "Counters",
  "Global", "Europe", "North America", "Tier", "Win rate", "Ceiling WR", "Median games", "Rising", "Cooling", "Stable", "Collecting",
  "Mage", "Fighter", "Tank", "Marksman", "Assassin", "Bruiser", "Enchanter", "Controller",
  "Playstyle", "Abilities", "History", "Skins",
  "Core items", "Cores", "Rune pages", "Boots", "Summoner spells", "Spells", "Matchups", "Best partners", "Partners", "Duo partners", "Duos"]) keys.add(k);
console.log(JSON.stringify([...keys].sort(), null, 1));
