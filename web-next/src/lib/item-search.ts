/**
 * Item search that understands what players type.
 *
 * Nobody searches "Blade of the Ruined King"; they type "botrk". Every item
 * picker used to match the full name only, so the abbreviations the whole
 * community uses found nothing. An item now matches on:
 *
 *   - its name, as before ("blade" finds Blade of the Ruined King)
 *   - a known abbreviation or nickname (ITEM_ALIASES), exactly or by prefix
 *   - the initials of a multi-word name, automatically ("ldr", "ie", "ga")
 *
 * "mr" is deliberately not Mortal Reminder: it means magic resist to anyone
 * typing it.
 */
export const ITEM_ALIASES: Record<string, string[]> = {
  "abyssal-mask": ["abyssal"],
  "amaranths-twinguard": ["twinguard", "amaranth"],
  "archangels-staff": ["archangel", "aa staff", "tear"],
  "ardent-censer": ["ardent", "censer"],
  "armorcrusher-boots": ["armorcrusher"],
  "armored-advance": ["armored advance"],
  "banshees-veil": ["banshee", "banshees", "bv"],
  "berserkers-greaves": ["zerks", "zerkers", "berserkers", "berserker"],
  "black-cleaver": ["bc", "cleaver"],
  "black-mist-scythe": ["bms", "scythe"],
  "blackfire-torch": ["bft", "torch", "blackfire"],
  "blade-of-the-ruined-king": ["botrk", "bork", "brk", "ruined king"],
  "bloodletters-curse": ["bloodletter", "bloodletters"],
  "bloodthirster": ["bt"],
  "boots-of-dynamism": ["dynamism"],
  "boots-of-mana": ["mana boots"],
  "bulwark-of-the-mountain": ["bulwark"],
  "chainlaced-crushers": ["crushers", "chainlaced"],
  "chempunk-chainsword": ["chempunk", "chainsword", "cpc"],
  "cosmic-drive": ["cosmic"],
  "crimson-lucidity": ["crimson"],
  "cryptbloom": ["crypt"],
  "dead-mans-plate": ["dmp", "deadmans", "dead man"],
  "deaths-dance": ["dd", "deaths"],
  "diadem-of-songs": ["diadem"],
  "divine-sunderer": ["sunderer", "divine", "ds"],
  "dusk-and-dawn": ["dnd", "dusk"],
  "duskblade-of-draktharr": ["duskblade", "draktharr", "db"],
  "echoes-of-helia": ["helia"],
  "edge-of-night": ["eon"],
  "essence-reaver": ["er", "reaver"],
  "experimental-hexplate": ["hexplate"],
  "fiendhunter-bolts": ["fiendhunter", "bolts"],
  "fimbulwinter": ["fimbul"],
  "force-of-nature": ["fon"],
  "frozen-heart": ["fh"],
  "galeforce": ["gale"],
  "gargoyle-stoneplate": ["gargoyle", "stoneplate"],
  "gluttonous-greaves": ["gluttonous"],
  "goredrinker": ["gore"],
  "guardian-angel": ["ga"],
  "guinsoos-rageblade": ["guinsoo", "guinsoos", "rageblade", "rb"],
  "gunmetal-greaves": ["gunmetal"],
  "harmonic-echo": ["harmonic"],
  "heartsteel": ["hs"],
  "hexoptics-c44": ["hexoptics", "c44"],
  "hextech-rocketbelt": ["rocketbelt", "belt"],
  "hollow-radiance": ["hollow"],
  "horizon-focus": ["horizon", "hf"],
  "hullbreaker": ["hull"],
  "iceborn-gauntlet": ["iceborn", "ibg", "gauntlet"],
  "immortal-shieldbow": ["shieldbow"],
  "immortal-treads": ["immortal treads"],
  "imperial-mandate": ["mandate"],
  "infinity-edge": ["ie"],
  "infinity-orb": ["orb"],
  "ionian-boots-of-lucidity": ["lucidity", "ionian", "cdr boots", "haste boots"],
  "kaenic-rookern": ["kaenic", "rookern"],
  "knights-vow": ["kv", "knights"],
  "kraken-slayer": ["kraken"],
  "liandrys-torment": ["liandry", "liandrys"],
  "lich-bane": ["lich"],
  "locket-of-the-iron-solari": ["locket", "solari"],
  "lord-dominiks-regard": ["ldr", "dominik", "dominiks", "lord dominik"],
  "ludens-echo": ["luden", "ludens"],
  "mantle-of-the-twelfth-hour": ["mantle", "twelfth hour"],
  "maw-of-malmortius": ["maw", "malmortius"],
  "mercurial-scimitar": ["qss", "scimitar", "mercurial"],
  "mercurys-treads": ["mercs", "merc treads", "mercury"],
  "mikaels-blessing": ["mikael", "mikaels"],
  "morellonomicon": ["morello"],
  "mortal-reminder": ["mortal"],
  "nashors-tooth": ["nashor", "nashors"],
  "navori-quickblades": ["navori", "quickblades"],
  "oceanids-trident": ["oceanid", "trident"],
  "overlords-bloodmail": ["bloodmail", "overlord"],
  "phantom-dancer": ["pd"],
  "plated-steelcaps": ["steelcaps", "tabis", "caps"],
  "quicksilver-sash": ["sash", "qss"],
  "rabadons-deathcap": ["rabadon", "rabadons", "deathcap", "dcap", "cap"],
  "radiant-virtue": ["radiant"],
  "randuins-omen": ["randuin", "randuins"],
  "rapid-firecannon": ["rfc", "firecannon"],
  "redemption": ["redemption", "salvation"],
  "riftmaker": ["rift"],
  "rod-of-ages": ["roa"],
  "runaans-hurricane": ["runaan", "runaans", "hurricane"],
  "rylais-crystal-scepter": ["rylai", "rylais"],
  "seekers-armguard": ["seekers", "armguard"],
  "seraphs-embrace": ["seraph", "seraphs"],
  "serpents-fang": ["fang", "serpent"],
  "seryldas-grudge": ["serylda", "seryldas", "grudge"],
  "shurelyas-battlesong": ["shurelya", "shurelyas", "battlesong"],
  "spear-of-shojin": ["shojin", "sos"],
  "spellslingers-shoes": ["sorcs", "sorc shoes", "spellslinger", "magic pen boots"],
  "staff-of-flowing-water": ["sofw", "flowing water"],
  "statikk-shiv": ["shiv", "statikk"],
  "steraks-gage": ["sterak", "steraks"],
  "stormrazor": ["razor"],
  "stormsurge": ["surge"],
  "stridebreaker": ["stride"],
  "sundered-sky": ["sundered", "sky"],
  "sunfire-aegis": ["sunfire"],
  "the-collector": ["collector"],
  "titanic-hydra": ["titanic", "hydra", "th"],
  "trinity-force": ["tf", "triforce", "trinity"],
  "unending-despair": ["despair"],
  "void-staff": ["void"],
  "warmogs-armor": ["warmog", "warmogs"],
  "whispering-circlet": ["circlet"],
  "winters-approach": ["winters", "wa"],
  "wits-end": ["wits", "wits end"],
  "youmuus-ghostblade": ["youmuu", "youmuus", "ghostblade", "yg"],
  "yun-tal-wildarrows": ["yun tal", "yuntal", "wildarrows"],
  "zekes-convergence": ["zeke", "zekes"],
  "zhonyas-hourglass": ["zhonya", "zhonyas", "hourglass"],
};

/** Lowercase, apostrophes dropped, everything else to single spaces. */
export function normalizeItemQuery(value: string): string {
  return value.toLowerCase().replace(/['’]/g, "").replace(/[^a-z0-9]+/g, " ").trim();
}

/** "Blade of the Ruined King" -> "botrk". Single-word names have none. */
function initials(name: string): string {
  const words = normalizeItemQuery(name).split(" ").filter(Boolean);
  return words.length > 1 ? words.map((word) => word[0]).join("") : "";
}

/** Does this item answer to what the player typed? */
export function itemMatches(item: { slug?: string; name: string }, query: string): boolean {
  const q = normalizeItemQuery(query);
  if (!q) return true;
  if (normalizeItemQuery(item.name).includes(q)) return true;
  if (q.length >= 2 && initials(item.name) === q.replace(/ /g, "")) return true;
  const aliases = item.slug ? ITEM_ALIASES[item.slug] ?? [] : [];
  return aliases.some((alias) => alias === q || (q.length >= 3 && alias.startsWith(q)));
}
