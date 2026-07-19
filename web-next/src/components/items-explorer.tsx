"use client";

import { useMemo, useState } from "react";
import { ITEMS, ITEM_CATEGORIES, statLines, type Item } from "@/lib/items";

/* eslint-disable @next/next/no-img-element */

function ItemCard({ it }: { it: Item }) {
  const lines = statLines(it.stats);
  return (
    <div className="glass flex flex-col rounded-2xl p-4">
      <div className="flex items-start gap-3">
        {it.icon ? (
          <img src={it.icon} alt={it.name} width={52} height={52} className="rounded-lg ring-1 ring-white/10" />
        ) : (
          <span className="grid h-[52px] w-[52px] place-items-center rounded-lg bg-white/[0.06] text-xs text-faint">?</span>
        )}
        <div className="min-w-0 flex-1">
          <p className="font-semibold leading-tight">{it.name}</p>
          <div className="mt-1 flex items-center gap-2">
            <span className="text-sm font-semibold text-gold">{it.cost.toLocaleString()}g</span>
            <span className="rounded bg-white/[0.06] px-1.5 py-0.5 text-[0.6rem] uppercase tracking-wide text-muted">{it.category}</span>
          </div>
        </div>
      </div>

      {lines.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {lines.map((l) => (
            <span key={l.key} className="rounded-md bg-accent/10 px-2 py-0.5 text-xs font-medium text-accent">{l.text}</span>
          ))}
        </div>
      )}

      {it.passives.length > 0 && (
        <ul className="mt-3 space-y-1.5 border-t border-line/60 pt-3 text-sm text-muted">
          {it.passives.map((p, i) => {
            const [head, ...rest] = p.split(":");
            const hasLabel = rest.length > 0 && head.length < 24;
            return (
              <li key={i} className="leading-relaxed">
                {hasLabel ? (
                  <>
                    <span className="font-semibold text-text">{head.trim()}:</span> {rest.join(":").trim()}
                  </>
                ) : (
                  p
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export function ItemsExplorer() {
  const [q, setQ] = useState("");
  const [cat, setCat] = useState<string>("All");

  const filtered = useMemo(() => {
    const query = q.trim().toLowerCase();
    return ITEMS.filter((it) => {
      if (cat !== "All" && it.category !== cat) return false;
      if (!query) return true;
      return (
        it.name.toLowerCase().includes(query) ||
        it.passives.some((p) => p.toLowerCase().includes(query)) ||
        Object.keys(it.stats).some((k) => k.toLowerCase().includes(query))
      );
    });
  }, [q, cat]);

  const cats = ["All", ...ITEM_CATEGORIES];

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search items, stats or passives…"
          className="w-full max-w-xs rounded-lg border border-line bg-white/[0.04] px-3 py-2 text-sm text-text outline-none focus:border-accent/50"
        />
        <div className="flex flex-wrap gap-1.5">
          {cats.map((c) => (
            <button
              key={c}
              onClick={() => setCat(c)}
              className={`rounded-lg px-3 py-1.5 text-sm font-semibold transition ${
                c === cat ? "bg-accent/20 text-accent" : "bg-white/[0.04] text-muted hover:text-text"
              }`}
            >
              {c}
            </button>
          ))}
        </div>
        <span className="ml-auto text-xs text-faint">{filtered.length} items</span>
      </div>

      <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {filtered.map((it) => <ItemCard key={it.slug} it={it} />)}
        {filtered.length === 0 && <p className="py-8 text-sm text-faint">No items match.</p>}
      </div>
    </div>
  );
}
