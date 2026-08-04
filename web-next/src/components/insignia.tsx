/* Engraved insignia: the site's shared vocabulary for crowning something.
 *
 * These began on the Hall of Fame, where every record gets a glyph and a gold
 * accent. The leaderboard's best-player spotlight needs the same language --
 * the point of a house style is that a crown means the same thing wherever it
 * appears -- so the paths live here rather than being redrawn per page.
 *
 * Stroked, not filled, and sized in em-ish steps: they sit beside text as
 * punctuation, not as illustration.
 */

export function Glyph({
  d,
  className = "",
  size = 22,
}: {
  d: string;
  className?: string;
  size?: number;
}) {
  return (
    <svg
      width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
      className={className} aria-hidden
    >
      <path d={d} />
    </svg>
  );
}

export const GLYPHS: Record<string, string> = {
  crown: "M3 18h18M4 16l-1-8 5.5 4L12 5l3.5 7L21 8l-1 8H4z",
  star: "M12 2.5l2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 17.4l-5.9 3.1 1.2-6.5L2.5 9.4l6.6-.9 2.9-6z",
  swords: "M4 4l7 7M4 4v4M4 4h4M20 4l-7 7M20 4v4M20 4h-4M7 17l-3 3M17 17l3 3M6 14l4 4M18 14l-4 4",
  shield: "M12 3l8 3v6c0 4.5-3.5 7.7-8 9-4.5-1.3-8-4.5-8-9V6l8-3z",
  tower: "M8 21V9M16 21V9M6 9h12M8 9V5l2 1.5L12 5l2 1.5L16 5v4M5 21h14",
  coin: "M12 3a9 9 0 100 18 9 9 0 000-18zM12 7v10M9.5 9.5c0-1 1-1.7 2.5-1.7s2.5.7 2.5 1.7-1 1.5-2.5 2-2.5 1-2.5 2 1 1.7 2.5 1.7 2.5-.7 2.5-1.7",
  users: "M9 11a4 4 0 100-8 4 4 0 000 8zM2 21v-1a6 6 0 016-6h2a6 6 0 016 6v1M17 8a3 3 0 100-4M19 14a5 5 0 013 5v2",
  bolt: "M13 2L4 14h6l-1 8 9-12h-6l1-8z",
  medal: "M12 15a5 5 0 100-10 5 5 0 000 10zM12 15v6M9 20l3-2 3 2M8 6L5 2M16 6l3-4",
  gem: "M6 3h12l4 6-10 12L2 9l4-6zM2 9h20M9 3l3 6 3-6M12 9v12",
  award: "M12 13a5 5 0 100-10 5 5 0 000 10zM8.5 12L7 22l5-3 5 3-1.5-10",
  flame: "M12 22c4.4 0 7-2.8 7-6.5 0-3-2-5-3.5-6.5C14 7.5 13 5.5 13 3c-3 2-4.5 4.5-4.5 7C7 9 6.5 8 6.5 6.5 5 8.5 5 11 5 12.5 5 19.2 7.6 22 12 22z",
  scroll: "M6 3h12a2 2 0 012 2v14a2 2 0 01-2 2H6a2 2 0 01-2-2V5a2 2 0 012-2zM8 8h8M8 12h8M8 16h5",
  hourglass: "M6 2h12M6 22h12M7 2c0 5 4 6 4 8s-4 3-4 8M17 2c0 5-4 6-4 8s4 3 4 8",
  sprout: "M12 22V10M12 10C12 6 9 4 4 4c0 5 3 7 8 6zM12 12c0-4 3-6 8-6 0 5-3 7-8 6z",
  cross: "M12 3v18M3 12h18M6.5 6.5l11 11M17.5 6.5l-11 11",
};

/** Two laurel branches. Reads as "this one won something" at a glance. */
export function Laurel({ size = 30, className = "text-gold/80" }: { size?: number; className?: string }) {
  return (
    <svg
      width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.5" strokeLinecap="round" aria-hidden className={className}
    >
      <path d="M7 21c-3-2-5-6-4-11 3 1 5 3 5 6M5.5 13c-2-2-3-5-2-8 2.5 1 4 3 4.2 5.5M17 21c3-2 5-6 4-11-3 1-5 3-5 6M18.5 13c2-2 3-5 2-8-2.5 1-4 3-4.2 5.5M8 21h8" />
    </svg>
  );
}
