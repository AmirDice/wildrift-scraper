import itemsData from "@/data/items.json";

export interface ItemStat {
  value: number;
  percent: boolean;
}

export interface Item {
  slug: string;
  name: string;
  cost: number;
  icon: string | null;
  category: string;
  categories: string[];
  tags: string[];
  stats: Record<string, ItemStat>;
  passives: string[];
}

export const ITEMS = itemsData as unknown as Item[];

/** Display order for the category filter; matches the scraped categories. */
export const ITEM_CATEGORIES = ["Physical", "Magic", "Defense", "Boots", "Active", "Support"] as const;

// stat key -> readable label, in a sensible display order
const STAT_LABELS: Record<string, string> = {
  ad: "Attack Damage",
  ap: "Ability Power",
  hp: "Health",
  armor: "Armor",
  mr: "Magic Resist",
  attackSpeed: "Attack Speed",
  crit: "Crit Chance",
  abilityHaste: "Ability Haste",
  moveSpeed: "Move Speed",
  lethality: "Lethality",
  physicalPen: "Armor Pen",
  magicPen: "Magic Pen",
  mana: "Mana",
  manaRegen: "Mana Regen",
  hpRegen: "Health Regen",
  lifesteal: "Life Steal",
  physVamp: "Physical Vamp",
  omnivamp: "Omnivamp",
  healShield: "Heal & Shield",
  tenacity: "Tenacity",
};

const STAT_ORDER = Object.keys(STAT_LABELS);

export function statLabel(key: string): string {
  return STAT_LABELS[key] ?? key.replace(/([a-z])([A-Z])/g, "$1 $2").replace(/^./, (c) => c.toUpperCase());
}

/** Item stats as ordered "+55 Attack Damage" / "+25% Crit Chance" lines. */
export function statLines(stats: Record<string, ItemStat>): { key: string; label: string; text: string }[] {
  return Object.entries(stats)
    .sort((a, b) => {
      const ia = STAT_ORDER.indexOf(a[0]);
      const ib = STAT_ORDER.indexOf(b[0]);
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
    })
    .map(([key, s]) => ({
      key,
      label: statLabel(key),
      text: `+${s.value % 1 === 0 ? s.value : s.value.toFixed(1)}${s.percent ? "%" : ""} ${statLabel(key)}`,
    }));
}
