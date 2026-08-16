"use client";

import { useMemo, useState } from "react";
import engineData from "@/data/engine.json";

/* eslint-disable @next/next/no-img-element */

const DATA = engineData as {
  items?: Record<string, { name?: string; icon?: string; category?: string }>;
};

const VERDICT_LABEL: Record<string, { text: string; cls: string }> = {
  viable_alternative: { text: "Viable alternative", cls: "bg-emerald-400/15 text-emerald-300" },
  situational: { text: "Situational", cls: "bg-gold/15 text-gold" },
  worse_here: { text: "Worse here", cls: "bg-accent/15 text-accent" },
  not_viable: { text: "Not viable", cls: "bg-bad/15 text-bad" },
};

/**
 * "Why not this item?" -- let the player challenge the build.
 *
 * People disagree with generated builds constantly. Without this, the
 * disagreement ends as "the generator is stupid"; with it, the generator
 * defends the call or concedes the alternative, either of which builds more
 * trust than silence. A question spends one generation from the same daily
 * allowance as a build, and the button says so before anyone clicks.
 */
export function WhyNotPanel({ champion, items, boots, runeNames, playstyle, buildBias, bare = false }: {
  champion: string;
  items: string[];
  boots?: string;
  runeNames: string[];
  playstyle: string;
  buildBias: string;
  /** Renders without its own card chrome, for embedding in "Adapt this build". */
  bare?: boolean;
}) {
  const [candidate, setCandidate] = useState("");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [asked, setAsked] = useState<{
    candidate: string; candidateName?: string; verdict?: string;
    answer?: string; competesWith?: string | null; error?: string;
  } | null>(null);

  const options = useMemo(() => {
    const inBuild = new Set([...items, boots ?? ""]);
    return Object.entries(DATA.items ?? {})
      .filter(([slug, meta]) => !inBuild.has(slug) && meta.category !== "Boots")
      .map(([slug, meta]) => ({ slug, name: meta.name ?? slug }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [items, boots]);

  const ask = async () => {
    if (!candidate || busy) return;
    setBusy(true);
    setAsked(null);
    try {
      const res = await fetch("/api/build/why-not", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ champion, items, boots, runes: runeNames, candidate, playstyle, buildBias }),
      });
      const data = await res.json();
      setAsked({ candidate, ...data });
    } catch {
      setAsked({ candidate, error: "Could not reach the engine; ask again." });
    } finally {
      setBusy(false);
    }
  };

  const verdict = asked?.verdict ? VERDICT_LABEL[asked.verdict] : null;

  return (
    <div className={bare ? "" : "glass rounded-2xl p-4"}>
      <p className="text-sm font-bold text-text">Wondering about another item?</p>
      <p className="mt-0.5 text-xs text-muted">
        Pick one and the engine explains why it is not in this build, or concedes that it
        could be. Costs one generation, same as a build.
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <div className="relative min-w-0 flex-1 sm:max-w-xs">
          <input
            value={candidate ? (DATA.items?.[candidate]?.name ?? candidate) : query}
            onChange={(e) => { setCandidate(""); setQuery(e.target.value); }}
            placeholder="Search an item…"
            aria-label="Item to ask about"
            className="w-full rounded-lg border border-line bg-[#0e1322] px-3 py-2 text-sm text-text outline-none focus:border-accent/50"
          />
          {query.trim() && !candidate && (
            <div className="absolute left-0 right-0 top-full z-40 mt-1 max-h-56 overflow-y-auto rounded-xl border border-line bg-[#0e1322] p-1 shadow-2xl">
              {options
                .filter((o) => o.name.toLowerCase().includes(query.trim().toLowerCase()))
                .slice(0, 8)
                .map((o) => (
                  <button
                    key={o.slug}
                    onClick={() => { setCandidate(o.slug); setQuery(""); }}
                    className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-sm text-muted transition hover:bg-white/[0.06] hover:text-text"
                  >
                    <img src={DATA.items?.[o.slug]?.icon ?? `/items/${o.slug}.webp`} alt=""
                         width={22} height={22} className="rounded" />
                    {o.name}
                  </button>
                ))}
              {options.filter((o) => o.name.toLowerCase().includes(query.trim().toLowerCase())).length === 0 && (
                <p className="px-2.5 py-1.5 text-xs text-faint">Nothing matches.</p>
              )}
            </div>
          )}
        </div>
        <button
          onClick={ask}
          disabled={!candidate || busy}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-bold text-black transition hover:opacity-90 disabled:opacity-40"
        >
          {busy ? "Asking…" : "Why not this?"}
        </button>
      </div>

      {asked && (
        <div className="mt-3 rounded-xl border border-line/60 bg-white/[0.025] p-3">
          {asked.error ? (
            <p className="text-sm text-bad">{asked.error}</p>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <img src={DATA.items?.[asked.candidate]?.icon ?? `/items/${asked.candidate}.webp`}
                     alt="" width={28} height={28} className="rounded-md ring-1 ring-white/15" />
                <span className="text-sm font-bold">{asked.candidateName ?? asked.candidate}</span>
                {verdict && (
                  <span className={`rounded-md px-2 py-0.5 text-[0.65rem] font-bold uppercase tracking-wide ${verdict.cls}`}>
                    {verdict.text}
                  </span>
                )}
                {asked.competesWith && (
                  <span className="text-xs text-faint">competes with {asked.competesWith}</span>
                )}
              </div>
              <p className="mt-2 text-sm leading-relaxed text-muted">{asked.answer}</p>
            </>
          )}
        </div>
      )}
    </div>
  );
}
