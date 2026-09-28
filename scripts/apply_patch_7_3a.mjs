import fs from 'node:fs';
import path from 'node:path';
const root = process.cwd(), dir = path.join(root, 'data');
const read = (n) => JSON.parse(fs.readFileSync(path.join(dir, n), 'utf8'));
const write = (n, v) => fs.writeFileSync(path.join(dir, n), JSON.stringify(v, null, 2) + '\n');
const set = (o, ks, v) => { let x = o; for (const k of ks.slice(0, -1)) x = x[k]; x[ks.at(-1)] = v; };
const formulas = read('ability_formulas.json');
const champions = read('champions_wr.json');
const byName = Object.fromEntries(champions.map((c) => [c.name, c]));
const asData = read('champion_attack_speed.json');
const items = read('items.json');
const bySlug = Object.fromEntries(items.map((i) => [i.slug, i]));
const itemFx = read('item_engine_overrides.json');

const h = formulas.Hwei;
h.hwei.patch = '7.3a';
h.abilities.P.damage[0].base = { lvlRange: [40, 285] };
h.abilities.P.damage[0].ratios[0].pct = 30;
h.abilities['1'].damage[0].base = [50, 85, 120, 155];
h.abilities['1'].damage[0].ratios[0].pct = 70;
h.abilities['4'].damage[0].base = [200, 300, 400];
h.abilities['4'].damage[0].ratios[0].pct = 70;
h.hwei.passive = { ...h.hwei.passive, base: [40, 285], ap: 0.30 };
h.hwei.spells.QQ = { ...h.hwei.spells.QQ, base: [50, 85, 120, 155], ap: 0.70 };
h.hwei.spells.QW.missingHealthPct = [1, 1.5, 2, 2.5];
h.hwei.spells.R = { ...h.hwei.spells.R, base: [200, 300, 400], ap: 0.70 };

const s = Object.fromEntries(champions.map((c) => [c.name, c.baseStats]));
s.Samira.hp = { ...s.Samira.hp, perLevel: 136, lvl15: 2534 };
s.Samira.armor = { ...s.Samira.armor, perLevel: 5.5, lvl15: 112 };
s.Samira.mr = { ...s.Samira.mr, perLevel: 2, lvl15: 58 };
s.Rammus.armor = { ...s.Rammus.armor, base: 40, lvl15: 96 };
s.Caitlyn.attackSpeed = { ...s.Caitlyn.attackSpeed, perLevel: 0.025, lvl15: 1.15 };
s.Senna.attackSpeed = { ...s.Senna.attackSpeed, base: 0.3, perLevel: 0.025, lvl15: 0.65 };

set(formulas, ['Samira','abilities','1','damage',0,'ratios',0,'pct'], 125);
set(formulas, ['Samira','abilities','4','damage',0,'ratios',0,'pct'], 50);
set(formulas, ['Rammus','abilities','2','steroids',0,'note'], 'plus 30/40/50/60% armor');
set(formulas, ['Malphite','abilities','2','damage',0,'ratios',1,'pct'], 15);
set(formulas, ['Malphite','abilities','3','damage',0,'ratios',0,'pct'], 40);
set(formulas, ['Draven','abilities','1','damage',0,'ratios',0,'pct'], 90);
set(formulas, ['Draven','abilities','2','steroids',0,'pct'], [25,30,35,40]);
set(formulas, ['Draven','abilities','4','damage',0,'ratios',0,'pct'], 150);
set(formulas, ['Tristana','abilities','1','steroids',0,'flat'], [0.6,0.8,1,1.2]);
set(formulas, ['Tristana','abilities','2','cooldowns'], [20,18,16,14]);
set(formulas, ['Tristana','abilities','3','damage',0,'base'], [80,110,140,170]);
set(formulas, ['Tristana','abilities','3','damage',0,'ratios',0,'pct'], 120);
set(formulas, ['Swain','abilities','3','damage',0,'ratios',0,'pct'], 40);
set(formulas, ['Viego','abilities','1','damage',0,'ratios',0,'pct'], [3,4,5,6]);
formulas.Swain.abilities.P.defensive[0].ratios = [
  { stat: 'ownMaxHp', pct: [4.5, 5, 5.5, 6] }, { stat: 'ap', pct: 0.2 },
];
formulas.Syndra.abilities['2'].damage[0].ratios[0].pct = 50;
formulas.Syndra.abilities.P.unmodeled = [...(formulas.Syndra.abilities.P.unmodeled ?? []), '7.3a evolution thresholds: 50/75/100/125/150 Splinters.'];
formulas.Senna.abilities.P.unmodeled = [...(formulas.Senna.abilities.P.unmodeled ?? []), '7.3a attack-speed benefit rate 0.3; base AS 0.3; base bonus AS 1.1; AS growth 0.025.'];

const repl = {
  Hwei: [['33 - 333','40 - 285'],['33% Ability Power','30% Ability Power'],['50 / 90 / 130 / 170','50 / 85 / 120 / 155'],['75% Ability Power','70% Ability Power'],['250 / 350 / 450','200 / 300 / 400']],
  Samira: [['110% Attack Damage','125% Attack Damage'],['40%','50%']], Rammus: [['Armor: 45','Armor: 40'],['45% / 50% / 55% / 60%','30% / 40% / 50% / 60%']],
  Malphite: [['20%','15%'],['45%','40%'],['75 / 70 / 65','85 / 80 / 75']], Tristana: [['50 / 75 / 100 / 125%','60 / 80 / 100 / 120%'],['22 / 20 / 18 / 16','20 / 18 / 16 / 14']],
  Draven: [['80 / 90 / 100 / 110%','90 / 100 / 110 / 120%'],['20 / 25 / 30 / 35%','25 / 30 / 35 / 40%'],['130%','150%']], Caitlyn: [['0.04','0.025'],['60% - 100%','60% - 90%']],
  Syndra: [['40 / 60 / 80 / 100 / 120','50 / 75 / 100 / 125 / 150'],['60%','50%'],['20% / 25% / 30% / 35%','25%']], Swain: [['3% - 4.5%','4.5% - 6%'],['0.5% Ability Power','0.2% Ability Power'],['25%','40%']],
  Yuumi: [['8%/9%/10%/11% + 0.02%','6%/7%/8%/9% + 0.01%']], Viego: [['2%/3%/4%/5%','3%/4%/5%/6%'],['80%','85%'],['50%','70%']],
};
for (const [name, rs] of Object.entries(repl)) for (const a of (byName[name]?.abilities ?? [])) if (a.text) for (const [x,y] of rs) a.text = a.text.replaceAll(x,y);

bySlug['yun-tal-wildarrows'].stats.attackSpeed.value = 35;
bySlug['yun-tal-wildarrows'].passives[1] = bySlug['yun-tal-wildarrows'].passives[1].replace('25% Attack Speed','35% Attack Speed').replace('20s Cooldown','25s Cooldown');
for (const slug of ['whispering-circlet','diadem-of-songs']) bySlug[slug].passives[0] = bySlug[slug].passives[0].replace('0.5%','0.25%');
bySlug['deaths-dance'].cost = 3300;
itemFx['yun-tal-wildarrows'] = { ...(itemFx['yun-tal-wildarrows'] ?? {}), asPctPassive: 35, flurryCooldownSec: 25 };
asData.patch = '7.3a'; asData.champions.Caitlyn.attackSpeedPerLevel = 0.025; asData.champions.Senna = { ...asData.champions.Senna, baseAttackSpeed:0.3, attackSpeedRatio:0.3, baseBonusAttackSpeed:1.1, attackSpeedPerLevel:0.025 };
for (const n of ['Syndra', 'Senna']) for (const slot of Object.values(formulas[n].abilities)) for (const k of ['unmodeled']) if (Array.isArray(slot[k])) slot[k] = [...new Set(slot[k])];

write('ability_formulas.json', formulas); write('champions_wr.json', champions); write('champion_attack_speed.json', asData); write('items.json', items); write('item_engine_overrides.json', itemFx);
const detailsPath = path.join(root, 'web-next', 'src', 'data', 'champion_details.json');
const details = JSON.parse(fs.readFileSync(detailsPath, 'utf8'));
for (const [name, rs] of Object.entries(repl)) {
  const key = Object.keys(details).find((k) => k.toLowerCase() === name.toLowerCase());
  if (!key) continue;
  for (const a of (details[key].abilities ?? [])) if (a.text) for (const [x, y] of rs) a.text = a.text.replaceAll(x, y);
}
fs.writeFileSync(detailsPath, JSON.stringify(details, null, 2) + '\n');
console.log('Applied 7.3a source data.');
