import { writeFile } from "node:fs/promises";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

/**
 * Fetch every champion's skin list from ddragon into a static catalogue.
 *
 * The build card lets a player pick which skin's splash art backs their card:
 * ddragon serves splashes as {Key}_{num}.jpg, and the num->name mapping lives
 * only in the per-champion data JSON. This pulls it once into
 * web-next/src/data/champion_skins.json keyed by OUR slug, carrying the
 * ddragon KEY as well, because slug and key disagree exactly where it hurts
 * (wukong -> MonkeyKing, kai-sa -> Kaisa, nunu-willump -> Nunu).
 *
 * The ddragon key is recovered from the loading-art URL each champion already
 * stores in site.json, so there is no hand-written slug->key table to rot.
 * Champions whose art is a local override fall back to trying their name.
 *
 * Rerun after a new champion ships:
 *     node scripts/fetch_champion_skins.mjs
 */

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const SITE = resolve(ROOT, "web-next", "src", "data", "site.json");
const OUT = resolve(ROOT, "web-next", "src", "data", "champion_skins.json");

const site = (await import(`file://${SITE}`, { with: { type: "json" } })).default;

const versions = await (await fetch("https://ddragon.leagueoflegends.com/api/versions.json")).json();
const ver = versions[0];
console.log(`ddragon data version: ${ver}`);

const out = {};
let ok = 0, miss = 0;
for (const champ of site.champions) {
  const fromUrl = (champ.splash || "").match(/\/loading\/([A-Za-z]+)_\d+\.jpg/);
  const key = fromUrl ? fromUrl[1] : champ.name.replace(/[^A-Za-z]/g, "");
  try {
    const res = await fetch(`https://ddragon.leagueoflegends.com/cdn/${ver}/data/en_US/champion/${key}.json`);
    if (!res.ok) throw new Error(String(res.status));
    const data = await res.json();
    const skins = data.data[key].skins.map((s) => ({
      num: s.num,
      name: s.name === "default" ? "Base" : s.name,
    }));
    out[champ.slug] = { key, skins };
    ok += 1;
  } catch (error) {
    console.log(`  MISS ${champ.name} (key ${key}): ${error.message}`);
    miss += 1;
  }
}

await writeFile(OUT, JSON.stringify(out, null, 1), "utf-8");
const skinCount = Object.values(out).reduce((n, c) => n + c.skins.length, 0);
console.log(`wrote ${OUT}`);
console.log(`${ok} champions, ${skinCount} skins, ${miss} misses`);
