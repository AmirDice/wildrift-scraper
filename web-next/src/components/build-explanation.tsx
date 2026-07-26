"use client";

import type { Build } from "@/lib/builds";

/* eslint-disable @next/next/no-img-element */

/**
 * Why each item and rune is in a recommended build.
 *
 * The curated generator already writes a one-line reason onto every item, boot,
 * rune and summoner (see scripts/build_champions_llm.py). Those reasons were
 * only reachable as hover tooltips, which no one finds on a phone, so this
 * collapses them into one expandable "why this build" list -- the same
 * information, discoverable.
 *
 * Collapsed by default: the build itself is the answer, and the reasoning is
 * there for anyone who wants to learn rather than copy.
 */
export function BuildExplanation({ build }: { build: Build }) {
  const items: { icon?: string; name: string; reason?: string; kind: string }[] = [
    ...build.coreBuild.map((item) => ({ icon: item.icon, name: item.name, reason: item.reason, kind: "item" })),
    ...(build.bootsEarly ? [{ icon: build.bootsEarly.icon, name: build.bootsEarly.name, reason: build.bootsEarly.reason, kind: "boots" }] : []),
    ...(build.boots && build.boots.slug !== build.bootsEarly?.slug
      ? [{ icon: build.boots.icon, name: build.boots.name, reason: build.boots.reason, kind: "boots" }]
      : []),
  ];

  const runes = [
    build.runes.keystone ? { icon: build.runes.keystone.icon, name: build.runes.keystone.name, reason: build.runes.keystone.reason, kind: "keystone" } : null,
    ...build.runes.treeMinors.map((rune) => ({ icon: rune.icon, name: rune.name, reason: rune.reason, kind: "rune" })),
    build.runes.flexMinor ? { icon: build.runes.flexMinor.icon, name: build.runes.flexMinor.name, reason: build.runes.flexMinor.reason, kind: "flex" } : null,
  ].filter((rune): rune is NonNullable<typeof rune> => Boolean(rune));

  const summoners = (build.summoners ?? []).map((spell) => ({
    icon: spell.icon, name: spell.name, reason: spell.reason, kind: "spell",
  }));

  // Nothing to explain (older builds without reasons): render nothing rather
  // than an empty accordion.
  const hasAny = [...items, ...runes, ...summoners].some((entry) => entry.reason);
  if (!hasAny) return null;

  return (
    <details className="glass group rounded-2xl">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 p-4">
        <span>
          <span className="block text-sm font-bold text-text">Why this build</span>
          <span className="text-xs font-normal text-faint">The reason behind every item and rune</span>
        </span>
        <span aria-hidden className="text-accent transition group-open:rotate-180">⌄</span>
      </summary>
      <div className="space-y-4 border-t border-line/60 p-4">
        <Section title="Items" rows={items} />
        <Section title="Runes" rows={runes} />
        {summoners.length > 0 && <Section title="Summoner spells" rows={summoners} />}
      </div>
    </details>
  );
}

function Section({
  title,
  rows,
}: {
  title: string;
  rows: { icon?: string; name: string; reason?: string }[];
}) {
  const withReason = rows.filter((row) => row.reason);
  if (withReason.length === 0) return null;

  return (
    <div>
      <p className="mb-2 text-[0.6rem] font-bold uppercase tracking-wide text-faint">{title}</p>
      <ul className="space-y-2">
        {withReason.map((row, index) => (
          <li key={`${row.name}-${index}`} className="flex items-start gap-3">
            {row.icon ? (
              <img src={row.icon} alt="" width={28} height={28} className="mt-0.5 shrink-0 rounded-md ring-1 ring-white/10" loading="lazy" />
            ) : (
              <span className="mt-0.5 h-7 w-7 shrink-0 rounded-md bg-white/[0.06]" />
            )}
            <div className="min-w-0">
              <p className="text-sm font-medium leading-tight">{row.name}</p>
              <p className="mt-0.5 text-xs leading-relaxed text-muted">{row.reason}</p>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
