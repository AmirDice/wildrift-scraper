// Run the installed TypeScript compiler in-memory: no npx downloads or output files.
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');
const root = path.resolve(__dirname, '..');
const original = Module._resolveFilename;
Module._resolveFilename = function (name, parent, ...rest) {
  return original.call(this, name.startsWith('@/') ? path.join(root, 'src', name.slice(2)) : name, parent, ...rest);
};
require.extensions['.ts'] = (module, filename) => module._compile(ts.transpileModule(
  fs.readFileSync(filename, 'utf8'), {compilerOptions: {module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020, esModuleInterop: true}}).outputText, filename);
const engine = require('../src/lib/engine.ts');
const {hweiTimeline} = require('../src/lib/hwei.ts');
const kit = require('../../data/hwei_kit.json');
const cases = JSON.parse(fs.readFileSync(0, 'utf8'));
const target = {hp:4000,armor:90,mr:60,bonusHp:1000};
const out = cases.map(c => {
  const st = engine.resolveStats('Hwei', c.level, c.items, c.runes);
  st.hweiChoices = c.choices;
  return {timeline:hweiTimeline(kit,st,target,c.window,c.level),
    rotation:engine.rotationDetail('Hwei',st,target,c.window,c.level),
    shield:engine.kitSustain('Hwei',st,c.level,c.window,'self'),
    stats:{hp:st.hp,mana:st.mana,ap:st.ap,as:st.as,armor:st.armor,mr:st.mr}};
});
process.stdout.write(JSON.stringify(out));
