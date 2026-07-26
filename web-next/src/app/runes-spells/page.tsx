import type { Metadata } from "next";
import engineData from "@/data/engine.json";
import spellsData from "@/data/spells.json";
import { Container } from "@/components/ui";
import { RuneSpellExplorer, type RuneEntry, type SpellEntry } from "@/components/rune-spell-explorer";

export const metadata: Metadata = {
  title: "Wild Rift Runes & Summoner Spells",
  description: "Search every tracked Wild Rift rune and summoner spell, with current effects, rune trees, slots, cooldowns, and practical use cases.",
  alternates: { canonical: "/runes-spells" },
};

export default function RunesSpellsPage() {
  const runes = Object.entries((engineData as { runes: Record<string, Omit<RuneEntry, "name">> }).runes)
    .map(([name, rune]) => ({ name, ...rune }))
    .sort((a, b) => (a.type === "Keystone" ? -1 : b.type === "Keystone" ? 1 : a.tree.localeCompare(b.tree) || a.slot - b.slot || a.name.localeCompare(b.name)));
  const spells = spellsData as SpellEntry[];
  return (
    <Container className="py-8 sm:py-10">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent">Loadout reference</p>
      <h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">Runes & summoner spells</h1>
      <p className="mb-7 mt-3 max-w-2xl text-sm leading-relaxed text-muted">Explore what each rune and spell does before choosing a loadout. Filter by rune tree, search by effect, and expand a card for the full description and practical use.</p>
      <RuneSpellExplorer runes={runes} spells={spells} />
    </Container>
  );
}
