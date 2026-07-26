"use client";

import { useMemo, useState } from "react";

/* eslint-disable @next/next/no-img-element */

export type RuneEntry = {
  name: string;
  slug: string;
  icon: string;
  tree: string;
  type: string;
  slot: number;
  description: string;
};

export type SpellEntry = {
  name: string;
  slug: string;
  icon: string;
  cooldown: string;
  description: string;
  use: string;
};

export function RuneSpellExplorer({ runes, spells }: { runes: RuneEntry[]; spells: SpellEntry[] }) {
  const [tab, setTab] = useState<"runes" | "spells">("runes");
  const [query, setQuery] = useState("");
  const [tree, setTree] = useState("All");
  const trees = ["All", "Keystones", ...Array.from(new Set(runes.map((rune) => rune.tree).filter(Boolean))).sort()];
  const visibleRunes = useMemo(() => runes.filter((rune) => {
    const matchesTree = tree === "All" || (tree === "Keystones" ? rune.type === "Keystone" : rune.tree === tree);
    const q = query.toLowerCase();
    return matchesTree && (!q || `${rune.name} ${rune.description}`.toLowerCase().includes(q));
  }), [query, runes, tree]);
  const visibleSpells = useMemo(() => {
    const q = query.toLowerCase();
    return spells.filter((spell) => !q || `${spell.name} ${spell.description} ${spell.use}`.toLowerCase().includes(q));
  }, [query, spells]);

  return (
    <div>
      <div className="glass rounded-2xl p-4">
        <div className="grid grid-cols-2 gap-1 rounded-xl border border-line bg-white/[0.025] p-1 sm:max-w-sm">
          <button onClick={() => { setTab("runes"); setQuery(""); }} className={`rounded-lg px-4 py-2 text-sm font-semibold transition ${tab === "runes" ? "bg-accent/20 text-accent" : "text-muted hover:text-text"}`}>Runes · {runes.length}</button>
          <button onClick={() => { setTab("spells"); setQuery(""); }} className={`rounded-lg px-4 py-2 text-sm font-semibold transition ${tab === "spells" ? "bg-accent/20 text-accent" : "text-muted hover:text-text"}`}>Spells · {spells.length}</button>
        </div>
        <div className="mt-4 flex flex-col gap-3 sm:flex-row">
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={`Search ${tab}…`} className="min-w-0 flex-1 rounded-lg border border-line bg-white/[0.04] px-3 py-2 text-sm text-text outline-none focus:border-accent/50" />
          {tab === "runes" && <select value={tree} onChange={(event) => setTree(event.target.value)} className="rounded-lg border border-line bg-[#0e1322] px-3 py-2 text-sm text-text outline-none" title="Filter runes by their primary tree"><option disabled>Rune tree</option>{trees.map((name) => <option key={name} value={name}>{name}</option>)}</select>}
        </div>
        <p className="mt-3 text-xs text-muted">Tap or click any card to expand the full effect. Rune descriptions reflect the current stored patch data; spell availability can depend on mode.</p>
      </div>

      {tab === "runes" ? (
        <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {visibleRunes.map((rune) => <details key={rune.name} className="group glass rounded-xl p-4 open:border-accent/30"><summary className="flex cursor-pointer list-none items-center gap-3"><img src={rune.icon} alt="" width={44} height={44} className="h-11 w-11 rounded-full object-cover ring-1 ring-white/10" /><div className="min-w-0 flex-1"><p className="truncate font-semibold">{rune.name}</p><p className="text-xs text-muted">{rune.type === "Keystone" ? "Keystone" : `${rune.tree} · slot ${rune.slot}`}</p></div><span className="text-lg text-faint transition group-open:rotate-45">+</span></summary><p className="mt-3 border-t border-line/60 pt-3 text-sm leading-relaxed text-muted">{rune.description}</p></details>)}
        </div>
      ) : (
        <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {visibleSpells.map((spell) => <details key={spell.slug} className="group glass rounded-xl p-4 open:border-accent/30"><summary className="flex cursor-pointer list-none items-center gap-3"><img src={spell.icon} alt="" width={46} height={46} className="h-[46px] w-[46px] rounded-lg object-cover ring-1 ring-white/10" /><div className="min-w-0 flex-1"><p className="truncate font-semibold">{spell.name}</p><p className="text-xs text-accent">{spell.cooldown}</p></div><span className="text-lg text-faint transition group-open:rotate-45">+</span></summary><div className="mt-3 border-t border-line/60 pt-3"><p className="text-sm leading-relaxed text-muted">{spell.description}</p><p className="mt-2 text-xs text-faint"><b className="text-text">Best for:</b> {spell.use}</p></div></details>)}
        </div>
      )}
      {((tab === "runes" && visibleRunes.length === 0) || (tab === "spells" && visibleSpells.length === 0)) && <p className="mt-8 text-center text-sm text-faint">No matching {tab}.</p>}
    </div>
  );
}
