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
        Generate one around how <span className="text-text">you</span> actually play
        {champion ? ` ${champion}` : ""}: your role, playstyle, power spike and win condition.
      </span>
      <span className="mt-2 inline-flex items-center gap-1 text-sm font-semibold text-accent">
        Build it with the assistant <span aria-hidden>→</span>
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

/** Anywhere in the studio -> the Counter Builder. */
export function CounterBuilderCta({ champion }: { champion?: string }) {
  return (
    <Link
      href={champion ? `/counter?champion=${encodeURIComponent(champion)}` : "/counter"}
      className="glass glass-hover block rounded-2xl border border-emerald-400/25 p-4 transition"
    >
      <span className="flex items-center gap-2 font-semibold text-emerald-300">
        <ShieldGlyph />
        Facing a lane bully, or a comp that shreds you?
      </span>
      <span className="mt-1 block text-sm text-muted">
        The Counter Builder takes the enemy team and rebuilds your items, boots and runes
        around beating exactly those five picks.
      </span>
      <span className="mt-2 inline-flex items-center gap-1 text-sm font-semibold text-emerald-300">
        Counter your opponent <span aria-hidden>→</span>
      </span>
    </Link>
  );
}

/** Counter Builder -> the studio's personal generator. */
export function StudioCta({ champion }: { champion?: string }) {
  return (
    <Link
      href={champion ? `/build?champion=${encodeURIComponent(champion)}` : "/build"}
      className="glass glass-hover block rounded-2xl border border-accent/25 p-4 transition"
    >
      <span className="flex items-center gap-2 font-semibold text-accent">
        <Sparkles size={15} />
        Just want a solid build for the champion?
      </span>
      <span className="mt-1 block text-sm text-muted">
        The Build Optimizer has curated builds per playstyle, a custom lab, and a generator
        that reads your playstyle instead of the enemy team.
      </span>
      <span className="mt-2 inline-flex items-center gap-1 text-sm font-semibold text-accent">
        Open the Build Optimizer <span aria-hidden>→</span>
      </span>
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
