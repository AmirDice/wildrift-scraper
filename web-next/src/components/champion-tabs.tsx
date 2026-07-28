"use client";

import { useState, type ReactNode } from "react";

const TABS = [
  { key: "overview", label: "Overview" },
  { key: "playstyle", label: "Playstyle" },
  { key: "abilities", label: "Abilities" },
  { key: "history", label: "History" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

export function ChampionTabs({ panels }: { panels: Record<TabKey, ReactNode> }) {
  const [active, setActive] = useState<TabKey>("overview");
  return (
    <div className="mt-6">
      <div className="glass sticky top-2 z-20 -mx-1 overflow-x-auto rounded-xl border border-line/70 p-1 shadow-xl shadow-black/10" role="tablist" aria-label="Champion information">
        {/* The 420px minimum was wider than any phone, so the strip always
            overflowed and "History" sat off-screen on a 375px viewport with
            nothing to show it was scrollable. These four labels fit four
            columns unaided; the minimum only applies once there is room. */}
        <div className="grid grid-cols-4 gap-1 sm:min-w-[420px]">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              type="button"
              role="tab"
              aria-selected={active === tab.key}
              aria-controls={`champion-panel-${tab.key}`}
              id={`champion-tab-${tab.key}`}
              onClick={() => setActive(tab.key)}
              className={`min-w-0 rounded-lg px-1 py-2.5 text-xs font-semibold transition sm:px-3 sm:text-sm ${active === tab.key ? "bg-accent/15 text-accent ring-1 ring-accent/20" : "text-muted hover:bg-white/[0.05] hover:text-text"}`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>
      {TABS.map((tab) => (
        <section
          key={tab.key}
          role="tabpanel"
          id={`champion-panel-${tab.key}`}
          aria-labelledby={`champion-tab-${tab.key}`}
          hidden={active !== tab.key}
          className="mt-6"
        >
          {panels[tab.key]}
        </section>
      ))}
    </div>
  );
}
