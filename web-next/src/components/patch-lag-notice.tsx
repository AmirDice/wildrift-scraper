import type { Freshness } from "@/lib/patch-freshness";

/**
 * "These win rates predate the current patch."
 *
 * Rendered only when that is actually true, so it is a fact on the page rather
 * than boilerplate a reader learns to skip. It removes itself once the boards
 * are re-collected, which is why nothing about it is hand-written.
 */
export function PatchLagNotice({
  freshness,
  className = "",
}: {
  freshness: Freshness | null;
  className?: string;
}) {
  if (!freshness?.stale) return null;
  const { patch, collectedOn, daysBefore } = freshness;
  const days = daysBefore === 1 ? "a day" : `${daysBefore} days`;

  return (
    <div
      className={`rounded-xl border border-gold/30 bg-gold/[0.07] px-4 py-3 ${className}`}
      role="note"
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-gold">
        Collected before patch {patch}
      </p>
      <p className="mt-1.5 text-xs leading-relaxed text-muted">
        These win rates come from games played on the previous patch. The board was collected
        on <span className="text-text">{collectedOn}</span>, {days} before {patch} went live, so
        any champion changed by it is still showing its pre-patch performance. Item and ability
        numbers elsewhere on the site are already on {patch}; only the win rates lag, and they
        update on the next collection.
      </p>
    </div>
  );
}
