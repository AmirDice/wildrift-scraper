"use client";

import { useState, type ReactNode } from "react";

const TABS = [
  { key: "overview", label: "Overview" },
  { key: "playstyle", label: "Playstyle" },
  { key: "abilities", label: "Abilities" },
  { key: "history", label: "History" },
  { key: "skins", label: "Skins" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

export function ChampionTabs({ panels, toolbar }: {
  panels: Record<TabKey, ReactNode>;
  /** Shown beside the tabs in the sticky bar (the page's region toggle). */
  toolbar?: ReactNode;
}) {
  const [active, setActive] = useState<TabKey>("overview");
  return (
    <div className="mt-6">
      <div className="glass sticky top-2 z-20 -mx-1 overflow-x-auto rounded-xl border border-line/70 p-1 shadow-xl shadow-black/10" role="tablist" aria-label="Champion information">
        {/* The 420px minimum was wider than any phone, so the strip always
            overflowed and "History" sat off-screen on a 375px viewport with
            nothing to show it was scrollable. These four labels fit four
            columns unaided; the minimum only applies once there is room. */}
        <div className="flex flex-wrap items-center gap-1">
        <div className="grid min-w-0 flex-1 grid-cols-5 gap-1 sm:min-w-[480px]">
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
        {toolbar && <div className="ml-auto pl-1">{toolbar}</div>}
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
