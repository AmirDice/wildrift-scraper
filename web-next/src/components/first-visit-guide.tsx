"use client";

import { useEffect, useState } from "react";

const KEY = "wr_studio_guide_v1";

const STEPS: { tab: string; what: string }[] = [
  { tab: "Build", what: "The engine's best build for each playstyle. Standard is the best all-around build for a normal game — it adapts to the champion (glass for assassins, tank for tanks)." },
  { tab: "Analysis", what: "How the build actually performs: damage by type, time to kill each enemy type, gold efficiency, mitigation, and real-fight friction." },
  { tab: "Customize", what: "Build from scratch and watch every stat change live, with a + next to each number. See ability damage at any level with the slider." },
  { tab: "vs Enemy", what: "Pick the enemy team and get the exact item swaps that counter them, scored against their real champions." },
];

/** One-time onboarding overlay (localStorage-gated) plus a floating help button
 *  to reopen it. Explains what each tab does for first-time visitors. */
export function FirstVisitGuide() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    try { if (!localStorage.getItem(KEY)) setOpen(true); } catch { /* ignore */ }
  }, []);

  const dismiss = () => {
    try { localStorage.setItem(KEY, "1"); } catch { /* ignore */ }
    setOpen(false);
  };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        aria-label="How this works"
        className="fixed bottom-4 right-4 z-40 grid h-11 w-11 place-items-center rounded-full border border-line bg-[#0e1322] text-lg font-bold text-accent shadow-2xl transition hover:border-accent/60"
      >
        ?
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={dismiss}>
          <div
            onClick={(e) => e.stopPropagation()}
            className="glass max-h-[85vh] w-full max-w-md overflow-y-auto rounded-2xl border border-line p-5"
          >
            <div className="mb-1 flex items-center justify-between">
              <h3 className="text-lg font-bold">The build optimizer in 20 seconds</h3>
              <button onClick={dismiss} className="text-muted hover:text-text" aria-label="close">✕</button>
            </div>
            <p className="mb-4 text-sm text-muted">Four tabs, each answering a different question:</p>
            <div className="space-y-3">
              {STEPS.map((s) => (
                <div key={s.tab} className="flex gap-3">
                  <span className="mt-0.5 shrink-0 rounded-md bg-accent/20 px-2 py-1 text-xs font-bold text-accent">{s.tab}</span>
                  <p className="text-sm text-muted">{s.what}</p>
                </div>
              ))}
            </div>
            <p className="mt-4 text-xs text-faint">Tip: tap any item, rune or ability icon for details.</p>
            <button
              onClick={dismiss}
              className="mt-4 w-full rounded-lg bg-accent/20 py-2.5 text-sm font-semibold text-accent transition hover:bg-accent/30"
            >
              Got it
            </button>
          </div>
        </div>
      )}
    </>
  );
}
