"use client";

import { useMemo, useState } from "react";
import { customizerItems, customizerRunes } from "@/lib/customizer-data";

/* eslint-disable @next/next/no-img-element */

/**
 * Pin items and runes a build must include, before generating.
 *
 * The generator is otherwise free to build whatever it judges best; this is the
 * one place the player overrides that. Kept deliberately small -- up to three
 * items and two runes -- so a "locked" build is still mostly the model's work
 * and still has room to be good around the pins.
 *
 * Items are stored as slugs, runes as display names, matching what the advisor
 * and its lock validation expect.
 */
export function LockPicker({
  lockedItems,
  lockedRunes,
  onItemsChange,
  onRunesChange,
}: {
  lockedItems: string[];
  lockedRunes: string[];
  onItemsChange: (next: string[]) => void;
  onRunesChange: (next: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const items = useMemo(() => customizerItems(), []);
  const runes = useMemo(() => customizerRunes(), []);
  const itemBySlug = useMemo(() => new Map(items.map((i) => [i.slug, i])), [items]);
  const runeByName = useMemo(() => new Map(runes.map((r) => [r.name, r])), [runes]);

  const total = lockedItems.length + lockedRunes.length;

  return (
    <div className="rounded-xl border border-line/60 bg-white/[0.02]">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left"
      >
        <span className="flex items-center gap-2">
          <LockIcon />
          <span className="text-sm font-semibold text-text">Lock items &amp; runes</span>
          <span className="rounded-full border border-line bg-white/[0.06] px-1.5 py-px text-[0.55rem] font-bold uppercase tracking-wide text-faint">
            Optional
          </span>
          <span className="hidden text-xs text-faint sm:inline">· the build must include these</span>
        </span>
        <span className="flex items-center gap-2">
          {total > 0 && (
            <span className="rounded-full bg-accent/20 px-2 py-0.5 text-[0.65rem] font-bold text-accent">{total}</span>
          )}
          <span aria-hidden className={`text-accent transition ${open ? "rotate-180" : ""}`}>⌄</span>
        </span>
      </button>

      {/* Locked chips are always visible so the player sees their pins even
          while the picker is collapsed. */}
      {total > 0 && (
        <div className="flex flex-wrap gap-1.5 px-3 pb-2.5">
          {lockedItems.map((slug) => {
            const item = itemBySlug.get(slug);
            return (
              <Chip
                key={slug}
                icon={item?.icon}
                label={item?.name ?? slug}
                onRemove={() => onItemsChange(lockedItems.filter((s) => s !== slug))}
              />
            );
          })}
          {lockedRunes.map((name) => {
            const rune = runeByName.get(name);
            return (
              <Chip
                key={name}
                icon={rune?.icon}
                label={name}
                round
                onRemove={() => onRunesChange(lockedRunes.filter((n) => n !== name))}
              />
            );
          })}
        </div>
      )}

      {open && (
        <div className="grid gap-3 border-t border-line/60 p-3 sm:grid-cols-2">
          <SearchAdd
            label="Lock an item"
            placeholder="Search items…"
            disabled={lockedItems.length >= 3}
            disabledHint="Up to 3 items"
            options={items
              .filter((i) => !lockedItems.includes(i.slug))
              .map((i) => ({ id: i.slug, name: i.name, icon: i.icon }))}
            onAdd={(id) => onItemsChange([...lockedItems, id])}
          />
          <SearchAdd
            label="Lock a rune"
            placeholder="Search runes…"
            round
            disabled={lockedRunes.length >= 2}
            disabledHint="Up to 2 runes"
            options={runes
              .filter((r) => !lockedRunes.includes(r.name))
              .map((r) => ({ id: r.name, name: r.name, icon: r.icon }))}
            onAdd={(id) => onRunesChange([...lockedRunes, id])}
          />
        </div>
      )}
    </div>
  );
}

function SearchAdd({
  label, placeholder, options, onAdd, disabled, disabledHint, round,
}: {
  label: string;
  placeholder: string;
  options: { id: string; name: string; icon?: string }[];
  onAdd: (id: string) => void;
  disabled?: boolean;
  disabledHint?: string;
  round?: boolean;
}) {
  const [query, setQuery] = useState("");
  const results = query
    ? options.filter((o) => o.name.toLowerCase().includes(query.toLowerCase())).slice(0, 6)
    : [];

  return (
    <div>
      <p className="mb-1 text-[0.6rem] font-bold uppercase tracking-wide text-faint">
        {label}
        {disabled && <span className="ml-1.5 font-normal normal-case text-faint/70">· {disabledHint}</span>}
      </p>
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        className="w-full rounded-lg border border-line bg-white/[0.04] px-2.5 py-1.5 text-sm text-text outline-none focus:border-accent/50 disabled:opacity-40"
      />
      {results.length > 0 && (
        <div className="mt-1 max-h-44 overflow-y-auto rounded-lg border border-line bg-[#0e1322] p-1">
          {results.map((o) => (
            <button
              key={o.id}
              type="button"
              onClick={() => { onAdd(o.id); setQuery(""); }}
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm text-muted transition hover:bg-white/[0.06] hover:text-text"
            >
              {o.icon ? (
                <img src={o.icon} alt="" width={22} height={22} className={`shrink-0 ring-1 ring-white/10 ${round ? "rounded-full" : "rounded"}`} />
              ) : (
                <span className="h-[22px] w-[22px] shrink-0 rounded bg-white/[0.06]" />
              )}
              <span className="truncate">{o.name}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Chip({
  icon, label, onRemove, round,
}: {
  icon?: string; label: string; onRemove: () => void; round?: boolean;
}) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-lg border border-accent/30 bg-accent/10 py-0.5 pl-1 pr-1.5 text-xs">
      {icon ? (
        <img src={icon} alt="" width={20} height={20} className={round ? "rounded-full" : "rounded"} />
      ) : null}
      <span className="max-w-[9rem] truncate font-medium text-text">{label}</span>
      <button type="button" onClick={onRemove} aria-label={`Unlock ${label}`} className="text-faint transition hover:text-bad">
        ×
      </button>
    </span>
  );
}

function LockIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden className="text-accent">
      <rect x="4.5" y="10.5" width="15" height="10" rx="2" />
      <path d="M8 10.5V7a4 4 0 0 1 8 0v3.5" />
    </svg>
  );
}
