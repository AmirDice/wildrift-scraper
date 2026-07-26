import fs from "node:fs";

const files = ["data/items.json", "web-next/src/data/items.json"];

for (const file of files) {
  const rows = JSON.parse(fs.readFileSync(file, "utf8"));
  const by = Object.fromEntries(rows.map((item) => [item.slug, item]));
  const has = (slug, text) =>
    (by[slug]?.passives || []).some((passive) => passive.includes(text));

  const checks = {
    "legacy typo slugs removed":
      !by["hextech-roketbelt"] && !by["immortal-treds"],
    "Rocketbelt spelling":
      by["hextech-rocketbelt"]?.name === "Hextech Rocketbelt",
    "Immortal Treads spelling":
      by["immortal-treads"]?.name === "Immortal Treads",
    "Shojin basic-ability haste":
      has("spear-of-shojin", "20 Basic Ability Haste") &&
      !has("spear-of-shojin", "+20% Ability Haste") &&
      by["spear-of-shojin"]?.scopedStats?.basicAbilityHaste?.value === 20,
    "Experimental Hexplate ultimate haste":
      by["experimental-hexplate"]?.scopedStats?.ultimateAbilityHaste?.value === 20,
    "Malignance ultimate haste":
      by["malignance"]?.scopedStats?.ultimateAbilityHaste?.value === 20,
    "Plated Steelcaps 7.2 stats/passive":
      by["plated-steelcaps"]?.stats?.armor?.value === 25 &&
      has("plated-steelcaps", "6% reduced"),
    "Armored Advance 7.2 shield":
      has("armored-advance", "20-140") && has("armored-advance", "5%"),
    "Chainlaced Crushers 7.2 shield":
      has("chainlaced-crushers", "20-140") &&
      has("chainlaced-crushers", "5%"),
    "Gunmetal Greaves ranged movement speed":
      has("gunmetal-greaves", "10% for ranged"),
    "Crimson Lucidity summoner-spell haste":
      has("crimson-lucidity", "20% Summoner Spell Haste") &&
      by["crimson-lucidity"]?.scopedStats?.summonerSpellHaste?.value === 20,
    "Ionian Boots summoner-spell haste":
      has("ionian-boots-of-lucidity", "15% Summoner Spell Haste") &&
      by["ionian-boots-of-lucidity"]?.scopedStats?.summonerSpellHaste?.value === 15,
    "Quicksilver Sash magic resist":
      by["quicksilver-sash"]?.stats?.mr?.value === 30,
    "Seeker's Armguard cost": by["seekers-armguard"]?.cost === 1400,
    "Zhonya cooldown": has("zhonyas-hourglass", "120s Cooldown"),
    "Shurelya ability power":
      by["shurelyas-battlesong"]?.stats?.ap?.value === 35,
    "Goredrinker structured omnivamp and AD wording":
      by["goredrinker"]?.stats?.omnivamp?.value === 8 &&
      has("goredrinker", "175% Attack Damage"),
    "Bloodthirster structured physical vamp":
      by["bloodthirster"]?.stats?.physicalVamp?.value === 8,
    "BotRK structured omnivamp":
      by["blade-of-the-ruined-king"]?.stats?.omnivamp?.value === 10,
    "Flat armor penetration is structured":
      by["youmuus-ghostblade"]?.stats?.physicalPenFlat?.value === 15 &&
      by["duskblade-of-draktharr"]?.stats?.physicalPenFlat?.value === 18 &&
      by["edge-of-night"]?.stats?.physicalPenFlat?.value === 8 &&
      by["serpents-fang"]?.stats?.physicalPenFlat?.value === 15 &&
      by["the-collector"]?.stats?.physicalPenFlat?.value === 10,
    "Percent armor penetration is structured":
      by["mortal-reminder"]?.stats?.physicalPen?.value === 30 &&
      by["seryldas-grudge"]?.stats?.physicalPen?.value === 33,
    "Boot omnivamp is structured":
      by["gluttonous-greaves"]?.stats?.omnivamp?.value === 5 &&
      by["immortal-treads"]?.stats?.omnivamp?.value === 5,
    "BotRK 7.2a and clean current-health wording":
      has("blade-of-the-ruined-king", "Melee attacks deal 8.5%") &&
      !has("blade-of-the-ruined-king", "7% [ad]"),
    "Manamune 7.2a": has("manamune", "max Mana by 14"),
    "Muramana 7.2a": has("muramana", "4.5%"),
    "Seraph 7.2a": has("seraphs-embrace", "16%"),
    "Armorcrusher Boots 7.2a":
      by["armorcrusher-boots"]?.stats?.ad?.value === 20 &&
      by["armorcrusher-boots"]?.stats?.physicalPenFlat?.value === 10,
    "Black Cleaver + Shojin effective haste split": (() => {
      const slugs = ["black-cleaver", "spear-of-shojin"];
      const general = slugs.reduce(
        (sum, slug) => sum + (by[slug]?.stats?.abilityHaste?.value || 0),
        0,
      );
      const basic = general + slugs.reduce(
        (sum, slug) => sum + (by[slug]?.scopedStats?.basicAbilityHaste?.value || 0),
        0,
      );
      const ultimate = general + slugs.reduce(
        (sum, slug) => sum + (by[slug]?.scopedStats?.ultimateAbilityHaste?.value || 0),
        0,
      );
      return general === 20 && basic === 40 && ultimate === 20;
    })(),
  };

  const failed = Object.entries(checks)
    .filter(([, passed]) => !passed)
    .map(([label]) => label);
  if (failed.length) {
    throw new Error(`${file}: ${failed.join(", ")}`);
  }
  console.log(`${file}: ${Object.keys(checks).length} checks passed`);
}
