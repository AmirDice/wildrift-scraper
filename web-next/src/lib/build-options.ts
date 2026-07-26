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
