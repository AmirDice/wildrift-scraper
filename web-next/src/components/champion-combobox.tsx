"use client";

import { useMemo, useState } from "react";

export type ComboItem = { name: string; slug: string; icon: string };

export function ChampionCombobox({
  champions,
  onSelect,
  placeholder = "Search a champion…",
  limit = 8,
}: {
  champions: ComboItem[];
  onSelect: (slug: string) => void;
  placeholder?: string;
  limit?: number;
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = q
      ? champions.filter((c) => c.name.toLowerCase().includes(q))
      : champions;
    return list.slice(0, limit);
  }, [query, champions, limit]);

  const choose = (slug: string) => {
    onSelect(slug);
    setQuery("");
    setOpen(false);
  };

  return (
    <div className="relative">
      <div className="relative">
        <svg
          className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-faint"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        >
          <circle cx="11" cy="11" r="7" />
          <line x1="21" y1="21" x2="16.65" y2="16.65" />
        </svg>
        <input
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
            setActive(0);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setActive((a) => Math.min(a + 1, matches.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((a) => Math.max(a - 1, 0));
            } else if (e.key === "Enter" && matches[active]) {
              e.preventDefault();
              choose(matches[active].slug);
            } else if (e.key === "Escape") {
              setOpen(false);
            }
          }}
          placeholder={placeholder}
          className="glass w-full rounded-xl py-2.5 pl-10 pr-4 text-sm outline-none transition placeholder:text-faint focus:border-accent/50"
        />
      </div>

      {open && matches.length > 0 && (
        <ul className="absolute z-50 mt-2 w-full overflow-hidden rounded-xl border border-line bg-surface-2 shadow-2xl">
          {matches.map((c, i) => (
            <li key={c.slug}>
              <button
                onMouseDown={(e) => {
                  e.preventDefault();
                  choose(c.slug);
                }}
                onMouseEnter={() => setActive(i)}
                className={`flex w-full items-center gap-3 px-3 py-2 text-left transition ${
                  active === i ? "bg-white/[0.06]" : ""
                }`}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={c.icon}
                  alt=""
                  width={28}
                  height={28}
                  loading="lazy"
                  className="h-7 w-7 rounded-full ring-1 ring-white/10"
                />
                <span className="text-sm font-medium">{c.name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
