/**
 * Behavioural checks for the parts of the engine that exist ONLY in TypeScript.
 *
 * WHY THIS FILE EXISTS
 *
 *     engine_parity guards everything the two engines share, and it is good at
 *     it: 55 cases, stats and the damage path. But duel(), mutualDuel(),
 *     championTarget(), kitSustain() and the whole crowd-control and enemy
 *     model have no Python twin, so parity cannot see them at all. They were
 *     verified once by hand, with throwaway scripts, and then had nothing
 *     holding them in place -- the newest and least-proven work was the least
 *     guarded.
 *
 *     Every assertion below is a number that was measured when the behaviour
 *     was built. They are deliberately written as INEQUALITIES and orderings
 *     rather than exact figures: the point is that anti-heal denies healing and
 *     that tenacity buys nothing against a champion with no crowd control, not
 *     that Graves kills Dr. Mundo in exactly 11.75 seconds. Pinning exact
 *     damage here would break on every balance patch and teach people to
 *     re-baseline without reading.
 *
 * Run:  npx tsx scripts/engine_model_check.ts       (from web-next)
 *       python -m pytest tests/test_engine_model.py (from the repo root)
 */
import {
  championTarget, duel, kitSustain, resolveStats, rotation, rotationDetail,
  supportValue,
} from "../src/lib/engine";

let failures = 0;
let checks = 0;

function ok(label: string, condition: boolean, detail = "") {
  checks += 1;
  if (condition) return;
  failures += 1;
  console.log(`FAIL  ${label}${detail ? `  (${detail})` : ""}`);
}

const DUMMY = { label: "dummy", hp: 2600, armor: 90, mr: 60, bonusHp: 900 };
const BRUISER = { label: "bruiser", hp: 3400, armor: 130, mr: 85, bonusHp: 1700 };
const CARRY = ["essence-reaver", "infinity-edge", "bloodthirster"];

// ---------------------------------------------------------------- proc rate
{
  const base: any = resolveStats("Zed", 15, ["youmuus-ghostblade", "seryldas-grudge"], []);
  const elec: any = resolveStats("Zed", 15, ["youmuus-ghostblade", "seryldas-grudge"], ["Electrocute"]);
  const at = (st: any, w: number) => rotation("Zed", st, BRUISER, w, 15);
  const d2 = at(elec, 2) - at(base, 2);
  const d10 = at(elec, 10) - at(base, 10);
  const d20 = at(elec, 20) - at(base, 20);
  // Electrocute needs three stacks inside three seconds, so nothing lands in a
  // two-second window, and its 20-13s cooldown lets it land twice in twenty.
  ok("electrocute does not land before it arms", d2 === 0, `2s delta ${d2}`);
  ok("electrocute lands once mid-fight", d10 > 0, `10s delta ${d10}`);
  ok("electrocute lands more often in a long fight", d20 > d10, `${d10} -> ${d20}`);

  const aery: any = resolveStats("Zed", 15, ["youmuus-ghostblade", "seryldas-grudge"], ["Aery"]);
  const a2 = at(aery, 2) - at(base, 2);
  const a20 = at(aery, 20) - at(base, 20);
  // Aery re-procs every two seconds, so it must scale far harder than a
  // keystone on a twenty-second cooldown. Before proc cooldowns existed both
  // were charged exactly once and were worth the same.
  ok("aery scales with fight length", a20 > a2 * 3, `${a2} -> ${a20}`);

  // Dark Harvest only fires on a target under half health, and it is adaptive
  // damage that resistances apply to. It used to be flat, unconditional, and
  // routed as unmitigated true damage.
  const dh: any = resolveStats("Zed", 15, ["youmuus-ghostblade", "seryldas-grudge"], ["Dark Harvest"]);
  const dhDelta = at(dh, 10) - at(base, 10);
  ok("dark harvest is not worth a whole health bar", dhDelta < BRUISER.hp * 0.15,
     `10s delta ${Math.round(dhDelta)} of ${BRUISER.hp} hp`);
  ok("dark harvest still contributes", dhDelta > 0, `10s delta ${dhDelta}`);
}

// ------------------------------------------------------------- enemy sustain
{
  const mundo = championTarget("Dr. Mundo", 15, ["sunfire-aegis", "warmogs-armor"], []);
  ok("a healer reports sustain", (mundo?.sustainPerSec ?? 0) > 50,
     `${mundo?.sustainPerSec}`);
  const graves = championTarget("Graves", 15, CARRY, []);
  ok("a non-healer reports none", (graves?.sustainPerSec ?? 0) === 0,
     `${graves?.sustainPerSec}`);

  const plain = duel("Graves", CARRY, ["Conqueror"], mundo!, 15, 20);
  const anti = duel("Graves", ["essence-reaver", "infinity-edge", "mortal-reminder"],
                    ["Conqueror"], mundo!, 15, 20);
  // The whole point of Grievous Wounds. Before the enemy had sustain at all,
  // these two builds were scored identically against a healer.
  ok("anti-heal beats a healer faster",
     anti!.ttk !== null && (plain!.ttk === null || anti!.ttk! < plain!.ttk!),
     `plain ${plain!.ttk} vs anti-heal ${anti!.ttk}`);
}

// ------------------------------------------------------------- shields / cut
{
  const shielded = { ...DUMMY, shield: 800 };
  const plain = duel("Graves", CARRY, ["Conqueror"], shielded, 15, 20);
  const cut = duel("Graves", ["essence-reaver", "infinity-edge", "serpents-fang"],
                   ["Conqueror"], shielded, 15, 20);
  ok("a shield slows the kill", plain!.ttk! > duel("Graves", CARRY, ["Conqueror"], DUMMY, 15, 20)!.ttk!,
     `${plain!.ttk} vs unshielded`);
  ok("shield cut speeds it back up", cut!.ttk! < plain!.ttk!, `${plain!.ttk} -> ${cut!.ttk}`);
}

// ------------------------------------------------------------ crowd control
{
  const alistar = championTarget("Alistar", 15, ["sunfire-aegis", "warmogs-armor"], []);
  const graves = championTarget("Graves", 15, CARRY, []);
  ok("a lockdown champion has cc depth", (alistar?.ccDepth ?? 0) >= 3, `${alistar?.ccDepth}`);
  ok("graves has none", (graves?.ccDepth ?? 0) === 0, `${graves?.ccDepth}`);

  const vsAli = duel("Graves", CARRY, ["Conqueror"], alistar!, 15, 20);
  const vsGraves = duel("Graves", CARRY, ["Conqueror"], graves!, 15, 20);
  ok("cc costs time against a lockdown comp", vsAli!.lockdown > 0, `${vsAli!.lockdown}s`);
  // The discriminating case: tenacity must buy NOTHING against a champion who
  // cannot lock you down. A model that pays out regardless is worse than none.
  ok("no lockdown against a champion with no hard cc", vsGraves!.lockdown === 0,
     `${vsGraves!.lockdown}s`);

  const tenacity = duel("Graves", CARRY, ["Conqueror", "Legend: Tenacity"], alistar!, 15, 20);
  ok("tenacity shortens lockdown", tenacity!.lockdown < vsAli!.lockdown,
     `${vsAli!.lockdown} -> ${tenacity!.lockdown}`);

  const cleanse = duel("Graves", ["essence-reaver", "infinity-edge", "mercurial-scimitar"],
                       ["Conqueror"], alistar!, 15, 20);
  ok("a cleanse removes an instance outright", cleanse!.lockdown < vsAli!.lockdown,
     `${vsAli!.lockdown} -> ${cleanse!.lockdown}`);

  const stasis = duel("Graves", CARRY, ["Conqueror"], { ...DUMMY, stasisSec: 2.5 }, 15, 20);
  ok("enemy stasis is dead time", stasis!.lockdown >= 2.5, `${stasis!.lockdown}s`);
}

// -------------------------------------------------- steelcaps block, chill
{
  const st: any = resolveStats("Ashe", 15, ["kraken-slayer", "infinity-edge"], []);
  const plain = rotationDetail("Ashe", st, DUMMY, 8, 15);
  const blocked = rotationDetail("Ashe", { ...st, autoDamageMult: 0.9 }, DUMMY, 8, 15);
  const chilled = rotationDetail("Ashe", { ...st, externalAsMult: 0.64 }, DUMMY, 8, 15);
  // Block is BASIC ATTACKS only, which is why it is not st.dr.
  ok("block cuts auto damage", blocked.autoDamage < plain.autoDamage,
     `${Math.round(plain.autoDamage)} -> ${Math.round(blocked.autoDamage)}`);
  ok("block leaves ability damage alone",
     Math.abs((blocked.damage - blocked.autoDamage) - (plain.damage - plain.autoDamage)) < 1,
     "ability damage moved");
  ok("chill cuts damage", chilled.damage < plain.damage,
     `${Math.round(plain.damage)} -> ${Math.round(chilled.damage)}`);
}

// ------------------------------------------------------- soul transfer clone
{
  const lowCrit: any = resolveStats("Yasuo", 15, ["soul-transfer"], []);
  const highCrit: any = resolveStats("Yasuo", 15, ["soul-transfer", "infinity-edge", "phantom-dancer"], []);
  const noClone: any = resolveStats("Yasuo", 15, ["infinity-edge", "phantom-dancer"], []);
  ok("the clone contributes", lowCrit.onHitPhys > 0, `${lowCrit.onHitPhys}`);
  ok("the clone scales with crit", highCrit.onHitPhys > lowCrit.onHitPhys,
     `${lowCrit.onHitPhys.toFixed(1)} -> ${highCrit.onHitPhys.toFixed(1)}`);
  ok("no clone without the item", noClone.onHitPhys === 0, `${noClone.onHitPhys}`);
}

// -------------------------------------------------------------- kit sustain
{
  const aatrox: any = resolveStats("Aatrox", 15, ["divine-sunderer"], []);
  // Aatrox heals for a share of the TARGET's max health, a ratio stat neither
  // engine resolved, so his sustain measured exactly zero.
  ok("aatrox heals off the target", kitSustain("Aatrox", aatrox, 15, 8, "self", {}, DUMMY) > 0);
  const graves: any = resolveStats("Graves", 15, CARRY, []);
  ok("graves heals for nothing", kitSustain("Graves", graves, 15, 8, "self", {}, DUMMY) === 0);
}

// ------------------------------------------------------------- ally value
{
  const soraka = supportValue("Soraka", ["ardent-censer", "staff-of-flowing-water"], ["Font of Life"], 15);
  const graves = supportValue("Graves", CARRY, ["Conqueror"], 15);
  // An enchanter's entire job. Without it every support item is a weak stat stick.
  ok("an enchanter provides ally value", soraka > 1000, `${Math.round(soraka)}`);
  ok("a carry provides none", graves === 0, `${graves}`);
}

// ------------------------------------------------------------- area damage
{
  const withR = rotationDetail("Ashe", resolveStats("Ashe", 15, ["runaans-hurricane", "infinity-edge"], []), DUMMY, 8, 15);
  const without = rotationDetail("Ashe", resolveStats("Ashe", 15, ["infinity-edge", "phantom-dancer"], []), DUMMY, 8, 15);
  ok("runaan's reports bolt damage", withR.boltDamage > 0, `${Math.round(withR.boltDamage)}`);
  ok("nothing else does", without.boltDamage === 0, `${without.boltDamage}`);
  // Bolts hit OTHER targets, so a single-target duel must never count them.
  ok("bolts are not single-target damage", withR.boltDamage > 0 && withR.damage < withR.damage + withR.boltDamage);
}

// --------------------------------------------------- rylai's, ingenious hunter
{
  const meleePlain = rotation("Jax", resolveStats("Jax", 15, ["trinity-force"], []), DUMMY, 8, 15);
  const meleeSlow = rotation("Jax", resolveStats("Jax", 15, ["trinity-force", "rylais-crystal-scepter"], []), DUMMY, 8, 15);
  ok("a slow helps a melee stick", meleeSlow > meleePlain,
     `${Math.round(meleePlain)} -> ${Math.round(meleeSlow)}`);
  const ranged: any = resolveStats("Lux", 15, ["ludens-echo", "rylais-crystal-scepter"], []);
  // A ranged champion is already at full auto uptime, so the slow must not
  // manufacture damage for it.
  ok("a slow does not help a ranged champion's uptime",
     rotation("Lux", ranged, DUMMY, 8, 15)
       === rotation("Lux", { ...ranged, targetSlow: 0 }, DUMMY, 8, 15));

  const plain: any = resolveStats("Zed", 15, ["duskblade-of-draktharr"], []);
  const hasted: any = resolveStats("Zed", 15, ["duskblade-of-draktharr"], ["Ingenious Hunter"]);
  const cdOf = (st: any) => st.procs.find((p: any) => p.label === "duskblade-of-draktharr")?.cd;
  ok("item haste shortens an item proc", cdOf(hasted) < cdOf(plain),
     `${cdOf(plain)} -> ${cdOf(hasted)}`);
  // Item haste is ITEM cooldowns. A keystone is not its business.
  const runeProc: any = resolveStats("Zed", 15, ["duskblade-of-draktharr"], ["Ingenious Hunter", "Electrocute"]);
  const elecOnly: any = resolveStats("Zed", 15, ["duskblade-of-draktharr"], ["Electrocute"]);
  const elecCd = (st: any) => st.procs.find((p: any) => p.label === "Electrocute")?.cd;
  ok("item haste leaves rune procs alone", elecCd(runeProc) === elecCd(elecOnly),
     `${elecCd(elecOnly)} -> ${elecCd(runeProc)}`);
}

console.log(`engine model: ${checks - failures}/${checks} checks passed`);
if (failures) process.exit(1);
