import type { Metadata } from "next";
import { Container } from "@/components/ui";
import { ItemsExplorer } from "@/components/items-explorer";

export const metadata: Metadata = {
  title: "Wild Rift Items | Stats, Passives & Costs",
  description:
    "Every Wild Rift item on patch 7.2: costs, stats and passive effects. Filter by physical, magic, defense, boots, active and support items.",
  alternates: { canonical: "/items" },
};

export default function ItemsPage() {
  return (
    <Container className="py-12">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Items</h1>
      </div>
      <p className="mt-2 max-w-2xl text-muted">
        Every item on the current patch with its stats, passives and cost. Search by name,
        stat or effect, or filter by category.
      </p>
      <div className="mt-8">
        <ItemsExplorer />
      </div>
    </Container>
  );
}
