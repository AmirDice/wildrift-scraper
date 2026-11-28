/**
 * "Hot" marker, on three pages only (2026-11-28): Tier List and Leaderboards,
 * the most visited after the home page, and Build Studio (v5). The same pages
 * carry a "hot" badge in the nav. Seven was tried first and diluted it.
 * The fire emoji is the owner's explicit choice, the one exception to the
 * site's no-emoji copy rule.
 *
 * Kept OUT of the <h1>: the heading text is what search engines index, and
 * "Wild Rift Tier List Hot" is not a title anyone searches for.
 */
export function HotTag({ className = "" }: { className?: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border border-red-400/35 bg-red-500/15 px-2.5 py-1 text-[0.6rem] font-bold uppercase leading-none tracking-[0.12em] text-red-300 ${className}`}
    >
      <span aria-hidden className="mr-1">🔥</span>Hot
    </span>
  );
}
