"use client";

import Link from "next/link";
import { Sparkles } from "@/components/enemy-build";

/* The two build tools answer different questions, and people who land on one
   rarely discover the other. These are the hand-offs between them. */

/** Recommended builds -> the personal generator. */
export function GenerateBuildCta({
  onGenerate,
  champion,
}: {
  /** Switches the studio to its generator tab. Omit to link to /build instead. */
  onGenerate?: () => void;
  champion?: string;
}) {
  const body = (
    <>
      <span className="flex items-center gap-2 font-semibold text-accent">
        <Sparkles size={15} />
        Not sold on this build?
      </span>
      <span className="mt-1 block text-sm text-muted">
        Generate the optimal one around how <span className="text-text">you</span> actually play
        {champion ? ` ${champion}` : ""}: your role, playstyle, power spike and win condition.
      </span>
      <span className="mt-2 inline-flex items-center gap-1 text-sm font-semibold text-accent">
        Build the optimal loadout <span aria-hidden>→</span>
      </span>
    </>
  );

  const className =
    "glass glass-hover block rounded-2xl border border-accent/25 p-4 text-left transition";

  return onGenerate ? (
    <button onClick={onGenerate} className={`${className} w-full`}>
      {body}
    </button>
  ) : (
    <Link href={champion ? `/build?champion=${encodeURIComponent(champion)}&tab=generate` : "/build?tab=generate"} className={className}>
      {body}
    </Link>
  );
}

/** Anywhere in the studio -> Build vs Enemy Team. */
export function CounterBuilderCta({
  onOpen,
  champion,
}: {
  /** Switches the studio to its enemy-team tab. Omit to link to /build instead. */
  onOpen?: () => void;
  champion?: string;
}) {
  const body = (
    <>
      <span className="flex items-center gap-2 font-semibold text-emerald-300">
        <ShieldGlyph />
        Don&rsquo;t know what to build against an enemy team?
      </span>
      <span className="mt-1 block text-sm text-muted">
        Name the five champions you are up against and get the optimal items, boots and runes
        for beating exactly those picks.
      </span>
      <span className="mt-2 inline-flex items-center gap-1 text-sm font-semibold text-emerald-300">
        Build against their team <span aria-hidden>→</span>
      </span>
    </>
  );

  const className =
    "glass glass-hover block rounded-2xl border border-emerald-400/25 p-4 text-left transition";

  return onOpen ? (
    <button onClick={onOpen} className={`${className} w-full`}>
      {body}
    </button>
  ) : (
    <Link
      href={champion ? `/build?champion=${encodeURIComponent(champion)}&tab=counter` : "/build?tab=counter"}
      className={className}
    >
      {body}
    </Link>
  );
}

function ShieldGlyph() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 3 5 6v6c0 4.2 2.9 7.7 7 9 4.1-1.3 7-4.8 7-9V6l-7-3Z" />
    </svg>
  );
}
