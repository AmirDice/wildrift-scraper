"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { visibleBuildVariants, type Build, type ChampionBuilds } from "@/lib/builds";
import {
  customBuildIssues,
  customizerItems,
  customizerRunes,
} from "@/lib/customizer-data";
import { Tip } from "@/components/build-view";
import {
  BuildStatsPanel,
  ChampionAbilitiesPanel,
  ItemDetail,
  RuneDetail,
} from "@/components/build-details";
import { BuildComparison, type ComparableBuild } from "@/components/build-comparison";
import { ShareBuildButton, track } from "@/components/share-build";
import { getChampions } from "@/lib/data";

/* eslint-disable @next/next/no-img-element */

type RunePick = { keystone: string; tree: string; minors: [string, string, string]; flex: string };
type CustomBuildState = { items: string[]; boots: string; runes: RunePick };
type SavedCustomBuild = {
  id: string;
  name: string;
  state: CustomBuildState;
  level: number;
  savedAt: number;
};

function fromBuild(b: Build): { items: string[]; boots: string; runes: RunePick } {
  return {
    items: b.coreBuild.map((i) => i.slug),
    boots: b.boots?.slug ?? "",
    runes: {
      keystone: b.runes.keystone?.name ?? "",
      tree: b.runes.primaryTree,
      minors: [
        b.runes.treeMinors[0]?.name ?? "",
        b.runes.treeMinors[1]?.name ?? "",
        b.runes.treeMinors[2]?.name ?? "",
      ],
      flex: b.runes.flexMinor?.name ?? "",
    },
  };
}

const EMPTY_STATE: CustomBuildState = { items: [], boots: "", runes: { keystone: "", tree: "Precision", minors: ["", "", ""], flex: "" } };
// Wild Rift minor-rune paths. Keystone is chosen independently of these.
const TREES = ["Domination", "Precision", "Resolve", "Sorcery"] as const;

function Tile({ icon, label, onClick, size = 40, round = false }: {
  icon?: string; label: string; onClick: () => void; size?: number; round?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      title={label}
      className="flex flex-col items-center gap-1 rounded-lg p-1 transition hover:bg-white/[0.06]"
    >
      {icon ? (
        <img src={icon} alt={label} width={size} height={size}
             className={`${round ? "rounded-full" : "rounded-lg"} ring-1 ring-white/15`}
             style={{ width: size, height: size }} />
      ) : (
        <span className={`grid place-items-center ${round ? "rounded-full" : "rounded-lg"} bg-white/[0.06] text-faint`}
              style={{ width: size, height: size }}>+</span>
      )}
    </button>
  );
}
function EquippedTile({ icon, label, detail, onRemove, size = 40, round = false }: {
  icon: string;
  label: string;
  detail: ReactNode;
  onRemove: () => void;
  size?: number;
  round?: boolean;
}) {
  return (
    <span className="relative inline-flex">
      <Tip tip={detail} wide>
        <button type="button" title={`Inspect ${label}`} className="rounded-lg p-1 transition hover:bg-white/[0.06]">
          <img
            src={icon}
            alt={label}
            width={size}
            height={size}
            className={`${round ? "rounded-full" : "rounded-lg"} ring-1 ring-white/15`}
            style={{ width: size, height: size }}
          />
        </button>
      </Tip>
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Remove ${label}`}
        title={`Remove ${label}`}
        className="absolute -right-1 -top-1 z-20 grid h-4 w-4 place-items-center rounded-full bg-[#0e1322] text-[0.65rem] font-bold leading-none text-bad ring-1 ring-bad/50 transition hover:bg-bad hover:text-white"
      >
        ×
      </button>
    </span>
  );
}

export function BuildCustomizer({ name, data, comparisonChoices }: {
  name: string;
  data: ChampionBuilds;
  comparisonChoices: ComparableBuild[];
}) {
  const variants = visibleBuildVariants(data);
  const [variant, setVariant] = useState(variants[0]);
  const base = data.builds[variant];
  // start EMPTY: the sandbox shows the champion's bare base stats, and every
  // item/rune the user adds shows its delta. "Start from" loads a variant.
  // The minor TREE is seeded from the current build, else the tree-minor slots
  // filter on tree === "" and show nothing (the reported bug). In Wild Rift the
  // keystone is independent of the minor path, so the tree is its own control.
  const [state, setState] = useState(() => ({
    ...EMPTY_STATE,
    runes: { ...EMPTY_STATE.runes, tree: base?.runes.primaryTree || "Precision" },
  }));
  const [level, setLevel] = useState(15);
  const [picker, setPicker] = useState<{ kind: "item" | "boots" | "keystone" | "minor" | "flex"; idx?: number } | null>(null);
  const [query, setQuery] = useState("");
  const [savedBuilds, setSavedBuilds] = useState<SavedCustomBuild[]>([]);
  const [saveName, setSaveName] = useState("");
  const [loadedSavedId, setLoadedSavedId] = useState<string | null>(null);

  const championSlug = useMemo(
    () => getChampions().find((entry) => entry.name === name)?.slug ?? "",
    [name],
  );
  const allItems = useMemo(() => customizerItems(), []);
  const allRunes = useMemo(() => customizerRunes(), []);
  const itemMeta = useMemo(() => new Map(allItems.map((i) => [i.slug, i])), [allItems]);
  const runeMeta = useMemo(() => new Map(allRunes.map((r) => [r.name, r])), [allRunes]);

  const allSlugs = [...state.items.filter(Boolean), ...(state.boots ? [state.boots] : [])];
  const runeNames = [state.runes.keystone, ...state.runes.minors, state.runes.flex].filter(Boolean);
  const edited = allSlugs.length > 0 || runeNames.length > 0;
  const totalGold = allSlugs.reduce((sum, slug) => sum + (itemMeta.get(slug)?.cost ?? 0), 0);
  const issues = [
    ...customBuildIssues(allSlugs),
    ...(new Set(runeNames).size !== runeNames.length ? ["duplicate rune"] : []),
  ];

  const storageKey = `wr_custom_builds_v1:${name}`;
  useEffect(() => {
    const timer = window.setTimeout(() => {
      try {
        const parsed = JSON.parse(localStorage.getItem(storageKey) || "[]") as SavedCustomBuild[];
        setSavedBuilds(Array.isArray(parsed) ? parsed.slice(0, 20) : []);
      } catch {
        setSavedBuilds([]);
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, [storageKey]);

  const persistSavedBuilds = (next: SavedCustomBuild[]) => {
    setSavedBuilds(next);
    try { localStorage.setItem(storageKey, JSON.stringify(next)); } catch { /* storage can be unavailable */ }
  };

  const saveCurrentBuild = () => {
    if (!allSlugs.length) return;
    const saved: SavedCustomBuild = {
      id: `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
      name: saveName.trim() || `${name} custom ${savedBuilds.length + 1}`,
      state: {
        items: [...state.items],
        boots: state.boots,
        runes: { ...state.runes, minors: [...state.runes.minors] as RunePick["minors"] },
      },
      level,
      savedAt: Date.now(),
    };
    persistSavedBuilds([saved, ...savedBuilds].slice(0, 20));
    setLoadedSavedId(saved.id);
    setSaveName("");
    // Saving is the strongest signal that someone actually used the lab, as
    // opposed to browsing the tier list. Counted server-side, no payload.
    track("build_saved");
  };

  const loadSavedBuild = (saved: SavedCustomBuild) => {
    setState({
      items: [...saved.state.items],
      boots: saved.state.boots,
      runes: { ...saved.state.runes, minors: [...saved.state.runes.minors] as RunePick["minors"] },
    });
    setLevel(saved.level);
    setLoadedSavedId(saved.id);
    setPicker(null);
  };

  const deleteSavedBuild = (id: string) => {
    persistSavedBuilds(savedBuilds.filter((saved) => saved.id !== id));
    if (loadedSavedId === id) setLoadedSavedId(null);
  };

  const savedChoices: ComparableBuild[] = savedBuilds.map((saved) => ({
    id: `saved:${saved.id}`,
    label: saved.name,
    itemSlugs: [...saved.state.items, ...(saved.state.boots ? [saved.state.boots] : [])],
    runeNames: [saved.state.runes.keystone, ...saved.state.runes.minors, saved.state.runes.flex].filter(Boolean),
  }));

  const reset = (v: string) => {
    setVariant(v);
    setState(fromBuild(data.builds[v]));
    setPicker(null);
    setLoadedSavedId(null);
  };

  const pickItem = (slug: string) => {
    setLoadedSavedId(null);
    setState((s) => {
      if (picker?.kind === "boots") return { ...s, boots: slug };
      const items = [...s.items];
      const idx = picker?.idx ?? 0;
      if (slug === "") items.splice(idx, 1);     // unequip: drop the slot
      else if (idx >= items.length) items.push(slug); // add a new item
      else items[idx] = slug;
      return { ...s, items };
    });
    setPicker(null);
    setQuery("");
  };
  const pickRune = (rn: string) => {
    setLoadedSavedId(null);
    setState((s) => {
      const r = { ...s.runes };
      if (picker?.kind === "keystone") {
        // WR keystones are NOT tied to a tree (the scrape tags them all
        // "Keystone"), so picking one must not touch the minor path.
        r.keystone = rn;
      } else if (picker?.kind === "flex") r.flex = rn;
      else if (picker?.kind === "minor") {
        const minors = [...r.minors] as RunePick["minors"];
        minors[picker.idx ?? 0] = rn;
        r.minors = minors;
      }
      return { ...s, runes: r };
    });
    setPicker(null);
    setQuery("");
  };
  const removeItem = (index: number) => {
    setLoadedSavedId(null);
    setState((current) => ({
      ...current,
      items: current.items.filter((_, itemIndex) => itemIndex !== index),
    }));
  };
  const removeBoots = () => {
    setLoadedSavedId(null);
    setState((current) => ({ ...current, boots: "" }));
  };
  const removeRune = (kind: "keystone" | "minor" | "flex", index = 0) => {
    setLoadedSavedId(null);
    setState((current) => {
      const runes = { ...current.runes };
      if (kind === "keystone") runes.keystone = "";
      else if (kind === "flex") runes.flex = "";
      else {
        const minors = [...runes.minors] as RunePick["minors"];
        minors[index] = "";
        runes.minors = minors;
      }
      return { ...current, runes };
    });
  };

  const candidates = useMemo(() => {
    if (!picker) return [];
    const q = query.toLowerCase();
    if (picker.kind === "item" || picker.kind === "boots") {
      return allItems
        .filter((i) => (picker.kind === "boots" ? i.category === "Boots" : i.category !== "Boots"))
        .filter((i) => i.name.toLowerCase().includes(q))
        .sort((a, b) => a.name.localeCompare(b.name));
    }
    if (picker.kind === "keystone")
      return allRunes.filter((r) => r.type === "Keystone" && r.name.toLowerCase().includes(q));
    if (picker.kind === "flex")
      return allRunes.filter((r) => r.type === "Minor" && r.name.toLowerCase().includes(q));
    // tree minor: correct slot, constrained to the chosen tree (all trees if
    // none set, so the picker is never empty).
    const slot = (picker.idx ?? 0) + 1;
    return allRunes.filter(
      (r) => r.type === "Minor" && r.slot === slot
        && (!state.runes.tree || r.tree === state.runes.tree)
        && r.name.toLowerCase().includes(q));
  }, [picker, query, allItems, allRunes, state.runes.tree]);

  return (
    <div className="glass rounded-2xl p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[0.65rem] font-bold uppercase tracking-wide text-faint">
          Customize <span className="normal-case text-faint/70">· build from scratch, watch every stat change</span>
        </p>
        <div className="flex items-center gap-1.5" data-tour="lab-start-from">
          <select
            value=""
            onChange={(e) => e.target.value && reset(e.target.value)}
            title="Load a recommended build as your editable starting point"
            aria-label="Start from a recommended build"
            className="rounded-lg border border-line bg-[#0e1322] px-2 py-1 text-xs text-muted"
          >
            <option value="">start from…</option>
            {variants.map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
          <button onClick={() => { setState(EMPTY_STATE); setPicker(null); setLoadedSavedId(null); }}
                  title="Remove every selected item and rune"
                  className="rounded-lg border border-line px-2 py-1 text-xs text-muted transition hover:text-text">
            clear
          </button>
        </div>
      </div>

      <div className="mt-3 rounded-xl border border-line/60 bg-white/[0.025] p-3" data-tour="lab-saved">
        <div className="flex flex-wrap items-center gap-2">
          <div className="mr-auto">
            <p className="text-xs font-bold text-text">Saved custom builds</p>
            <p className="text-[0.65rem] text-faint">Save up to 20 builds on this device. Load one, then compare it with another saved or recommended build.</p>
          </div>
          <input
            value={saveName}
            onChange={(event) => setSaveName(event.target.value)}
            placeholder={`${name} build name…`}
            aria-label="Custom build name"
            className="min-w-40 rounded-lg border border-line bg-[#0e1322] px-2.5 py-1.5 text-xs text-text outline-none focus:border-accent/60"
          />
          <button
            type="button"
            onClick={saveCurrentBuild}
            disabled={!allSlugs.length}
            title={allSlugs.length ? "Save this exact item, rune, and level setup" : "Add an item before saving"}
            className="rounded-lg bg-accent px-3 py-1.5 text-xs font-bold text-black transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Save build
          </button>
          <ShareBuildButton
            path={`/build?champion=${encodeURIComponent(championSlug)}`}
            title={`${name} custom build`}
            text={`${name} custom build on WrTrueMeta: ${allSlugs
              .map((slug) => itemMeta.get(slug)?.name ?? slug)
              .join(", ") || "work in progress"}.`}
            label="Share"
          />
        </div>
        {savedBuilds.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {savedBuilds.map((saved) => (
              <span key={saved.id} className={`inline-flex items-center overflow-hidden rounded-lg border ${loadedSavedId === saved.id ? "border-accent/60 bg-accent/10" : "border-line bg-white/[0.03]"}`}>
                <button type="button" onClick={() => loadSavedBuild(saved)} title={`Load ${saved.name}`} className="px-2.5 py-1.5 text-xs font-medium text-muted transition hover:text-text">
                  {saved.name}
                </button>
                <button type="button" onClick={() => deleteSavedBuild(saved.id)} aria-label={`Delete ${saved.name}`} title={`Delete ${saved.name}`} className="border-l border-line px-2 py-1.5 text-xs text-faint transition hover:bg-bad/15 hover:text-bad">×</button>
              </span>
            ))}
          </div>
        )}
      </div>

      {/* level slider */}
      <div className="mt-3 flex items-center gap-3 rounded-xl bg-white/[0.03] px-3 py-2">
        <span className="shrink-0 text-[0.65rem] font-bold uppercase tracking-wide text-faint">Level</span>
        <input type="range" min={1} max={15} value={level} onChange={(e) => { setLoadedSavedId(null); setLevel(Number(e.target.value)); }}
               className="h-1.5 flex-1 cursor-pointer accent-[var(--color-accent)]" aria-label="Champion level" />
        <span className="w-6 shrink-0 text-right text-sm font-bold text-accent">{level}</span>
      </div>

      {/* item slots */}
      <div className="mt-3 flex flex-wrap items-center gap-1.5" data-tour="lab-slots">
        {state.items.map((slug, i) => {
          const item = itemMeta.get(slug);
          return item ? (
            <EquippedTile key={`${slug}-${i}`} icon={item.icon} label={item.name}
              detail={<ItemDetail item={item} />} onRemove={() => removeItem(i)} />
          ) : null;
        })}
        {state.items.length < 5 && (
          <Tile label="add item"
                onClick={() => { setPicker({ kind: "item", idx: state.items.length }); setQuery(""); }} />
        )}
        <span className="text-faint">+</span>
        {state.boots && itemMeta.get(state.boots) ? (
          <EquippedTile icon={itemMeta.get(state.boots)!.icon} label={itemMeta.get(state.boots)!.name}
            detail={<ItemDetail item={itemMeta.get(state.boots)!} />} size={36} onRemove={removeBoots} />
        ) : (
          <Tile label="add boots" size={36} onClick={() => { setPicker({ kind: "boots" }); setQuery(""); }} />
        )}
        <span className="mx-1 h-8 w-px bg-line" />
        {state.runes.keystone && runeMeta.get(state.runes.keystone) ? (
          <EquippedTile icon={runeMeta.get(state.runes.keystone)!.icon} label={state.runes.keystone}
            detail={<RuneDetail rune={runeMeta.get(state.runes.keystone)!} />} size={40} round
            onRemove={() => removeRune("keystone")} />
        ) : (
          <Tile label="add keystone" size={40} round onClick={() => { setPicker({ kind: "keystone" }); setQuery(""); }} />
        )}
        {/* minor path selector: switching resets the 3 minors */}
        <select
          value={state.runes.tree}
          onChange={(e) => {
            setLoadedSavedId(null);
            setState((s) => ({ ...s, runes: { ...s.runes, tree: e.target.value, minors: ["", "", ""] } }));
          }}
          className="rounded-lg border border-line bg-white/[0.04] px-1.5 py-1 text-xs outline-none"
          title="Minor rune path"
        >
          {TREES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        {state.runes.minors.map((runeName, i) => {
          const rune = runeMeta.get(runeName);
          return rune ? (
            <EquippedTile key={`${runeName}-${i}`} icon={rune.icon} label={rune.name}
              detail={<RuneDetail rune={rune} />} size={32} round onRemove={() => removeRune("minor", i)} />
          ) : (
            <Tile key={`empty-${i}`} label={`add slot ${i + 1}`} size={32} round
              onClick={() => { setPicker({ kind: "minor", idx: i }); setQuery(""); }} />
          );
        })}
        {state.runes.flex && runeMeta.get(state.runes.flex) ? (
          <EquippedTile icon={runeMeta.get(state.runes.flex)!.icon} label={state.runes.flex}
            detail={<RuneDetail rune={runeMeta.get(state.runes.flex)!} />} size={32} round
            onRemove={() => removeRune("flex")} />
        ) : (
          <Tile label="add flex rune" size={32} round onClick={() => { setPicker({ kind: "flex" }); setQuery(""); }} />
        )}
        <span className="ml-auto rounded-md bg-gold/10 px-2 py-1 text-xs font-semibold text-gold">
          ~{totalGold.toLocaleString()}g
        </span>
      </div>

      {/* picker */}
      {picker && (
        <div className="mt-3 rounded-xl border border-line bg-[#0d1220] p-3">
          <div className="flex items-center gap-2">
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={picker.kind === "minor" ? `${state.runes.tree} slot ${(picker.idx ?? 0) + 1}…` : "search…"}
              className="w-full rounded-lg border border-line bg-transparent px-2.5 py-1.5 text-sm outline-none"
            />
            <button onClick={() => setPicker(null)} className="text-xs text-muted hover:text-text">close</button>
          </div>
          <div className="mt-2 grid max-h-44 grid-cols-6 gap-1 overflow-y-auto sm:grid-cols-10">
            {candidates.map((c) => (
              <button
                key={"slug" in c ? c.slug : c.name}
                onClick={() => ("cost" in c ? pickItem(c.slug) : pickRune(c.name))}
                title={c.name}
                className="rounded-lg p-1 transition hover:bg-white/[0.08]"
              >
                <img src={c.icon} alt={c.name} width={34} height={34}
                     className={`${"cost" in c ? "rounded-lg" : "rounded-full"} ring-1 ring-white/10`}
                     style={{ width: 34, height: 34 }} />
              </button>
            ))}
          </div>
        </div>
      )}

      <BuildStatsPanel name={name} itemSlugs={allSlugs} runeNames={runeNames} level={level} embedded />
      <ChampionAbilitiesPanel
        name={name}
        itemSlugs={allSlugs}
        runeNames={runeNames}
        level={level}
        embedded
      />

      {edited && issues.length > 0 && (
        <p className="mt-3 border-t border-line/60 pt-3 text-center text-xs font-medium text-bad">
          ⚠ {issues.join(" · ")}
        </p>
      )}
      <div className="mt-4">
        <BuildComparison
          champion={name}
          current={{
            id: loadedSavedId ? `saved:${loadedSavedId}` : "custom",
            label: loadedSavedId ? savedBuilds.find((saved) => saved.id === loadedSavedId)?.name ?? "Custom build" : "Custom build",
            itemSlugs: allSlugs,
            runeNames,
          }}
          choices={[...savedChoices, ...comparisonChoices]}
          level={level}
        />
      </div>
    </div>
  );
}
