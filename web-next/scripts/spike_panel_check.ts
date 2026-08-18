/**
 * Replays build-stages.tsx's exact math (stages, spike, order check,
 * early-swap check) outside React, so the panel's verdicts can be verified
 * without burning generation quota. Same modules, same thresholds -- if this
 * prints it, the UI renders it.
 */
import { duel, dummyTarget, resolveStats } from "../src/lib/engine";
import { blockedItems } from "../src/lib/customizer-data";
import { roster } from "../src/lib/threat";
import engineData from "../src/data/engine.json";

const DATA = engineData as {
  items?: Record<string, { name?: string; icon?: string; cost?: number; category?: string }>;
};
const itemName = (slug: string) => DATA.items?.[slug]?.name ?? slug;
const cost = (slug: string) => DATA.items?.[slug]?.cost ?? 3000;

type Case = {
  name: string; items: string[]; boots: string; bootsUpgrade: string;
  bootsUpgradeAfter: number; runeNames: string[]; powerCurve: string;
  candidates: string[];
};

const CASES: Case[] = [
  {
    name: "Gwen",
    items: ["nashors-tooth", "riftmaker", "rabadons-deathcap", "infinity-orb", "void-staff"],
    boots: "boots-of-mana", bootsUpgrade: "spellslingers-shoes", bootsUpgradeAfter: 1,
    runeNames: ["Conqueror", "Battle Zeal", "Cut Down", "Legend: Bloodline", "Sudden Impact"],
    powerCurve: "early",
    candidates: ["nashors-tooth", "riftmaker", "rabadons-deathcap", "infinity-orb", "void-staff",
      "dusk-and-dawn", "bloodletters-curse", "cosmic-drive", "liandrys-torment", "oceanids-trident",
      "cryptbloom", "banshees-veil", "stormsurge", "amaranths-twinguard", "zhonyas-hourglass",
      "morellonomicon"],
  },
  {
    name: "Lillia",
    items: ["liandrys-torment", "riftmaker", "cosmic-drive", "bloodletters-curse", "rabadons-deathcap"],
    boots: "boots-of-mana", bootsUpgrade: "spellslingers-shoes", bootsUpgradeAfter: 2,
    runeNames: ["Phase Rush", "Manaflow Band", "Transcendence", "Scorch", "Brutal"],
    powerCurve: "early",
    candidates: ["liandrys-torment", "riftmaker", "cosmic-drive", "bloodletters-curse",
      "rabadons-deathcap", "blackfire-torch", "infinity-orb", "banshees-veil", "zhonyas-hourglass",
      "stormsurge", "morellonomicon", "oceanids-trident", "rylais-crystal-scepter", "ludens-echo"],
  },
  {
    // Tank fixture: the spike must track HP jumps, not DPS.
    name: "Malphite",
    items: ["sunfire-aegis", "thornmail", "force-of-nature", "warmogs-armor", "randuins-omen"],
    boots: "", bootsUpgrade: "", bootsUpgradeAfter: 0,
    runeNames: [], powerCurve: "balanced", candidates: [],
  },
];

for (const c of CASES) {
  const { name, items, boots, bootsUpgrade, bootsUpgradeAfter, runeNames, powerCurve, candidates } = c;
  const level = 15;

  // ---- stages (mirrors the stages memo): every purchase its own step
  const t2 = boots || "";
  const t3 = bootsUpgrade || "";
  const upgradeAt = t3
    ? (bootsUpgradeAfter && bootsUpgradeAfter > 0
        ? Math.min(bootsUpgradeAfter, items.length) : 2)
    : 0;
  const t3Delta = t3 ? Math.max(300, cost(t3) - (t2 ? cost(t2) : 0)) : 0;
  type Purchase = { kind: string; slug: string; costG: number; itemCount: number };
  const purchasesFor = (order: string[], at: number): Purchase[] => {
    const seq: Purchase[] = [];
    order.forEach((slug, i) => {
      seq.push({ kind: "item", slug, costG: cost(slug), itemCount: i + 1 });
      if (i === 0 && t2) seq.push({ kind: "t2", slug: t2, costG: cost(t2), itemCount: i + 1 });
      if (i + 1 === at && t3) seq.push({ kind: "t3", slug: t3, costG: t3Delta, itemCount: i + 1 });
    });
    return seq;
  };
  const target = dummyTarget(3000, 60, 45);
  const seqRows = purchasesFor(items, upgradeAt);
  const ownedAcc: string[] = [];
  let goldAcc = 0;
  const rows = seqRows.map((purchase, i) => {
    if (purchase.kind === "t3" && t2) {
      const at = ownedAcc.indexOf(t2);
      if (at >= 0) ownedAcc.splice(at, 1);
    }
    ownedAcc.push(purchase.slug);
    goldAcc += purchase.costG;
    const slugs = [...ownedAcc];
    const st = resolveStats(name, level, slugs, runeNames);
    const fight = duel(name, slugs, runeNames, target, level, 20, false);
    const label = purchase.kind === "item"
      ? `${purchase.itemCount} item${purchase.itemCount > 1 ? "s" : ""}`
      : purchase.kind === "t2" ? "Boots" : "T3 boots";
    return { count: i + 1, label, slugs, gold: goldAcc, minute: Math.round(goldAcc / 650),
      hp: st ? Math.round(st.hp) : 0, dps: fight?.dps ?? 0 };
  });
  const isTank = roster()[name]?.class === "Tank";
  const REACHABLE_GOLD = 10500;
  let spike = 1; let best = 0;
  for (let i = 1; i < rows.length; i += 1) {
    if (rows[i].gold > REACHABLE_GOLD) break;
    const gain = isTank ? rows[i].hp - rows[i - 1].hp : rows[i].dps - rows[i - 1].dps;
    if (gain > best) { best = gain; spike = i + 1; }
  }

  console.log(`\n===== ${name} (${powerCurve}) =====`);
  for (const r of rows) {
    const mark = r.count === spike ? "  <-- SPIKE" : (r.minute > 16 ? "  (dimmed)" : "");
    console.log(`${r.label.padEnd(8)} ~min ${String(r.minute).padStart(2)}  ${r.gold}g  dps ${Math.round(r.dps)}  hp ${r.hp}  [${itemName(r.slugs[r.slugs.length - 1])}]${mark}`);
  }
  console.log(`spike metric: ${isTank ? "durability" : "damage"}`);

  // ---- order check (mirrors the orderCheck memo)
  const [CHECKPOINTS, WEIGHTS] =
    powerCurve === "early" ? [[3000, 5000, 7500], [3, 2, 1]]
    : powerCurve === "mid" ? [[4500, 7000, 9500], [1, 3, 2]]
    : powerCurve === "late" ? [[6000, 9500, 13000], [1, 2, 3]]
    : [[3000, 6000, 9000], [2, 2, 1]];
  const valueCache = new Map<string, number>();
  const dpsOf = (owned: string[]): number => {
    if (!owned.length) return 0;
    const key = [...owned].sort().join(",");
    let v = valueCache.get(key);
    if (v === undefined) {
      v = isTank
        ? Number(resolveStats(name, level, owned, runeNames)?.hp ?? 0)
        : (duel(name, owned, runeNames, target, level, 20, false)?.dps ?? 0);
      valueCache.set(key, v);
    }
    return v;
  };
  const score = (ord: string[], at = upgradeAt): number => {
    const seq = purchasesFor(ord, at);
    let total = 0;
    CHECKPOINTS.forEach((gold, i) => {
      const owned: string[] = [];
      let spent = 0;
      for (const purchase of seq) {
        spent += purchase.costG;
        if (spent > gold) break;
        if (purchase.kind === "t3" && t2) {
          const idx = owned.indexOf(t2);
          if (idx >= 0) owned.splice(idx, 1);
        }
        owned.push(purchase.slug);
      }
      total += dpsOf(owned) * WEIGHTS[i];
    });
    return total;
  };

  if (t3) {
    const shownTiming = score(items, upgradeAt);
    let bestAt = upgradeAt;
    let bestScore = shownTiming;
    for (let at = 0; at <= items.length; at += 1) {
      if (at === upgradeAt) continue;
      const sc = score(items, at);
      if (sc > bestScore) { bestScore = sc; bestAt = at; }
    }
    const timingGain = (bestScore - shownTiming) / shownTiming;
    if (bestAt !== upgradeAt && timingGain >= 0.04) {
      console.log(`boots timing: T3 after ${bestAt} beats shown (after ${upgradeAt}) by +${Math.round(timingGain * 100)}%`);
    } else {
      console.log(`boots timing: shown (after ${upgradeAt}) is optimal (best alt ${(timingGain * 100).toFixed(1)}%)`);
    }
  }
  const bestOf = (set: string[]): { score: number; order: string[] } => {
    const perms: string[][] = [];
    const permute = (rest: string[], acc: string[]) => {
      if (!rest.length) { perms.push(acc); return; }
      for (let i = 0; i < rest.length; i += 1) {
        permute([...rest.slice(0, i), ...rest.slice(i + 1)], [...acc, rest[i]]);
      }
    };
    permute(set, []);
    let bestScore = -1; let bestOrder = set;
    for (const perm of perms) {
      const sc = score(perm);
      if (sc > bestScore) { bestScore = sc; bestOrder = perm; }
    }
    return { score: bestScore, order: bestOrder };
  };

  const shown = score(items);
  const own = bestOf(items);
  const gain = (own.score - shown) / shown;
  if (gain < 0.04) {
    console.log(`order check: OPTIMAL (best possible reorder gain ${(gain * 100).toFixed(1)}%)`);
  } else {
    console.log(`order check: REORDER +${Math.round(gain * 100)}% -> ${own.order.map(itemName).join(" > ")}`);
  }

  // ---- early-swap substitution check
  let swap: { out: string; in: string; gainPct: number } | null = null;
  if (powerCurve === "early" && candidates.length) {
    const targets = items.filter((slug) => cost(slug) >= 3200);
    const pool = candidates.filter((slug) => slug && !items.includes(slug)
      && DATA.items?.[slug] && DATA.items[slug].category !== "Boots");
    console.log(`swap targets (>=3200g): ${targets.map((t) => `${itemName(t)} ${cost(t)}g`).join(", ") || "none"}`);
    for (const tgt of targets) {
      const rest = items.filter((s) => s !== tgt);
      for (const cand of pool) {
        if (cost(cand) > cost(tgt) - 200) continue;
        if (blockedItems([...rest])[cand]) continue;
        const sub = bestOf([...rest, cand]);
        const subGain = (sub.score - own.score) / own.score;
        if (subGain >= 0.05 && (!swap || sub.score > own.score * (1 + swap.gainPct / 100))) {
          swap = { out: tgt, in: cand, gainPct: Math.round(subGain * 100) };
        }
        if (subGain > -1) {
          console.log(`  try ${itemName(tgt)} -> ${itemName(cand)} (${cost(cand)}g): ${(subGain * 100).toFixed(1)}%`);
        }
      }
    }
  }
  console.log(swap
    ? `early-swap: SWAP ${itemName(swap.out)} -> ${itemName(swap.in)} (+${swap.gainPct}%)`
    : "early-swap: no swap beats the build's own items (>=5% threshold)");
}
