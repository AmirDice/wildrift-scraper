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
export function WhyNotPanel({ champion, items, boots, runeNames, playstyle, buildBias }: {
  champion: string;
  items: string[];
  boots?: string;
  runeNames: string[];
  playstyle: string;
  buildBias: string;
}) {
  const [candidate, setCandidate] = useState("");
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
    <div className="glass rounded-2xl p-4">
      <p className="text-sm font-bold text-text">Wondering about another item?</p>
      <p className="mt-0.5 text-xs text-muted">
        Pick one and the engine explains why it is not in this build, or concedes that it
        could be. Costs one generation, same as a build.
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <select
          value={candidate}
          onChange={(e) => setCandidate(e.target.value)}
          aria-label="Item to ask about"
          className="min-w-0 flex-1 rounded-lg border border-line bg-[#0e1322] px-3 py-2 text-sm text-text sm:max-w-xs"
        >
          <option value="">Choose an item…</option>
          {options.map((o) => <option key={o.slug} value={o.slug}>{o.name}</option>)}
        </select>
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
