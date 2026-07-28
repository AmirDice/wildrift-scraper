import comboData from "@/data/champion_combos.json";
import { getChampionDetails } from "@/lib/champion-details";

/* eslint-disable @next/next/no-img-element */

const COMBOS = comboData as {
  champions?: Record<string, { combo?: string[]; why?: string; confidence?: string }>;
};

/** Slot letters as players say them. */
const SLOT_LABEL: Record<string, string> = { P: "Passive", "1": "Q", "2": "W", "3": "E", "4": "R" };

/**
 * The champion's highest-damage combo, shown with the real ability icons.
 *
 * Icons rather than bare letters because "3 -> 1 -> auto" is the storage format,
 * not something a player reads: they recognise the art long before they decode
 * which slot is which.
 *
 * Suggested, and labelled as such. These come from a model asked for the
 * highest-damage sequence with the tooltips in front of it, not from a guide, so
 * the page should not present them as authoritative.
 */
export function ChampionCombo({ name, slug }: { name: string; slug: string }) {
  const entry = COMBOS.champions?.[name];
  if (!entry?.combo?.length) return null;

  const details = getChampionDetails(slug);
  const abilities = details?.abilities ?? [];
  const iconOf = new Map(abilities.map((a) => [String(a.slot), a.icon] as const));
  const nameOf = new Map(abilities.map((a) => [String(a.slot), a.name] as const));

  return (
    <div className="glass rounded-2xl p-5 sm:p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold">Highest-damage combo</h2>
        <span className="text-xs text-faint">suggested opener</span>
      </div>

      <ol className="mt-4 flex flex-wrap items-center gap-x-1 gap-y-3">
        {entry.combo.map((step, i) => (
          <li key={i} className="flex items-center gap-1">
            {i > 0 && <span aria-hidden className="px-0.5 text-lg text-faint">›</span>}
            <div className="flex w-16 flex-col items-center gap-1">
              {step === "auto" ? (
                <span className="grid h-11 w-11 place-items-center rounded-lg border border-line bg-white/[0.05]">
                  <AttackGlyph />
                </span>
              ) : iconOf.get(step) ? (
                <img src={iconOf.get(step)!} alt="" width={44} height={44}
                     className="h-11 w-11 rounded-lg ring-1 ring-white/10" loading="lazy" />
              ) : (
                <span className="grid h-11 w-11 place-items-center rounded-lg border border-line bg-accent/15 text-sm font-bold text-accent">
                  {SLOT_LABEL[step] ?? step}
                </span>
              )}
              <span className="text-center text-[0.65rem] font-bold uppercase tracking-wide text-accent">
                {step === "auto" ? "Attack" : SLOT_LABEL[step] ?? step}
              </span>
              <span className="line-clamp-2 text-center text-[0.6rem] leading-tight text-faint">
                {step === "auto" ? "basic" : nameOf.get(step) ?? ""}
              </span>
            </div>
          </li>
        ))}
      </ol>

      {entry.why && (
        <p className="mt-4 border-t border-line/60 pt-3 text-sm leading-relaxed text-muted">
          {entry.why}
        </p>
      )}
      <p className="mt-2 text-xs text-faint">
        Ordered for damage against a single target, so it ignores safety and
        positioning. Cooldowns and the situation decide the rest.
      </p>
    </div>
  );
}

function AttackGlyph() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"
         className="text-muted" aria-hidden>
      <path d="M14.5 3.5 21 3l-.5 6.5" />
      <path d="M21 3 10 14" />
      <path d="M6.5 12.5 3 16l5 5 3.5-3.5" />
    </svg>
  );
}
