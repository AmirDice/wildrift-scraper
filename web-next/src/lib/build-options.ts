export const GAME_PHASES = [
  { key: "balanced", label: "Balanced", description: "A practical curve for the full 15–20 minute match." },
  { key: "early", label: "Early game", description: "Prioritize the first purchase, clear speed, lane pressure, and first objectives." },
  { key: "mid", label: "Mid game", description: "Prioritize the two-to-three item spike for grouped fights and major objectives." },
  { key: "late", label: "Late game", description: "Prioritize the strongest realistic finished build and scaling." },
] as const;

export const DAMAGE_PATHS = [
  { key: "standard", label: "Standard", description: "Let the builder choose the most practical damage profile." },
  { key: "ad", label: "AD", description: "Commit to a coherent Attack Damage path." },
  { key: "ap", label: "AP", description: "Commit to a coherent Ability Power path." },
  { key: "hybrid", label: "Hybrid", description: "Use both AD and AP/on-hit scaling when the kit converts both efficiently." },
] as const;

/** How the damage is delivered, independent of AD/AP. Offered for every
 *  champion: an explicit pick overrules the curated "never" for that path only
 *  (crit Riven, on-hit Riven), which is what web/build_advisor.py DAMAGE_STYLES
 *  tells the model. */
export const DAMAGE_STYLES = [
  { key: "auto", label: "Auto", description: "Let the builder choose how the damage is delivered." },
  { key: "crit", label: "Crit", description: "A critical strike path: at least three crit items, even where it is not this champion's usual build." },
  { key: "onhit", label: "On-hit", description: "Attack speed and on-hit effects, scaled with the chosen damage path." },
  { key: "lethality", label: "Lethality", description: "Flat armor penetration burst, front-loaded for an early spike." },
  { key: "ability", label: "Abilities", description: "Spell damage: ability haste and items that fire on ability hits." },
] as const;

/** Champions whose AD and AP paths are both standard. No longer gates the
 *  damage path selector (every champion can ask for AD, AP or hybrid); kept
 *  for what "Standard" explores on its own. */
export const HYBRID_DAMAGE_CHAMPIONS = new Set([
  "Akali", "Corki", "Ezreal", "Jax", "Kai'Sa", "Katarina", "Kayle",
  "Shyvana", "Teemo", "Twitch", "Varus", "Volibear", "Warwick",
]);

export const KAYN_FORMS = [
  {
    key: "shadow-assassin",
    label: "Shadow Assassin",
    shortLabel: "Blue Kayn",
    description: "Burst, roaming, and fast access to ranged or fragile targets.",
  },
  {
    key: "rhaast",
    label: "Rhaast",
    shortLabel: "Darkin / Red Kayn",
    description: "Sustained physical damage, healing, crowd control, and max-Health damage.",
  },
] as const;
