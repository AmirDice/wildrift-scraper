"use client";

import { useEffect, useState, type ReactNode } from "react";

/**
 * The meta page in five views instead of one twenty-section scroll.
 *
 * Every panel is rendered and only hidden, so the whole page stays in the
 * HTML for crawlers and the page keeps its content. Links into the old single
 * page still land: an anchor such as /meta#one-trick opens the panel that
 * holds it and scrolls there.
 */
export type MetaPanel = { key: string; label: string; /** Phone label, if the full one does not fit. */ short?: string; blurb: string; anchors?: string[]; content: ReactNode };

export function MetaTabs({ panels }: { panels: MetaPanel[] }) {
  const [active, setActive] = useState(panels[0].key);

  useEffect(() => {
    const open = () => {
      const hash = window.location.hash.slice(1);
      if (!hash) return;
      const panel = panels.find((p) => p.key === hash || p.anchors?.includes(hash));
      if (!panel) return;
      setActive(panel.key);
      // After the panel is visible, so the browser can find the anchor.
      setTimeout(() => document.getElementById(hash)?.scrollIntoView({ block: "start" }), 50);
    };
    const timer = setTimeout(open, 0);
    window.addEventListener("hashchange", open);
    return () => { clearTimeout(timer); window.removeEventListener("hashchange", open); };
  }, [panels]);

  const current = panels.find((p) => p.key === active) ?? panels[0];
  return (
    <div className="mt-8">
      <div className="glass sticky top-2 z-20 -mx-1 rounded-xl border border-line/70 p-1 shadow-xl shadow-black/10" role="tablist" aria-label="Meta sections">
        {/* A grid at every width: as a scrolling row the fifth tab sat half
            off-screen on a 375px phone with nothing to show it was there. */}
        <div className="grid gap-1" style={{ gridTemplateColumns: `repeat(${panels.length}, minmax(0, 1fr))` }}>
          {panels.map((panel) => (
            <button key={panel.key} type="button" role="tab" id={`meta-tab-${panel.key}`} aria-controls={`meta-panel-${panel.key}`}
              aria-selected={active === panel.key}
              onClick={() => {
                setActive(panel.key);
                window.history.replaceState(null, "", `#${panel.key}`);
              }}
              className={`min-w-0 truncate rounded-lg px-1 py-2.5 text-[0.7rem] font-semibold transition sm:px-4 sm:text-sm ${active === panel.key ? "bg-accent/15 text-accent ring-1 ring-accent/20" : "text-muted hover:bg-white/[0.05] hover:text-text"}`}>
              {panel.short ? <><span className="sm:hidden">{panel.short}</span><span className="hidden sm:inline">{panel.label}</span></> : panel.label}
            </button>
          ))}
        </div>
      </div>
      <p className="mt-4 max-w-2xl text-sm text-muted">{current.blurb}</p>
      {panels.map((panel) => (
        <section key={panel.key} role="tabpanel" id={`meta-panel-${panel.key}`} aria-labelledby={`meta-tab-${panel.key}`}
          hidden={active !== panel.key}>
          {panel.content}
        </section>
      ))}
    </div>
  );
}
