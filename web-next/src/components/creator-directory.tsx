"use client";

import { useMemo, useState } from "react";
import { Card } from "@/components/ui";
import { CREATOR_CATEGORIES, PLATFORMS, type Creator } from "@/lib/creators";

/* eslint-disable @next/next/no-img-element */

const PLATFORM_LABEL = Object.fromEntries(PLATFORMS.map((entry) => [entry.key, entry.label]));
const CATEGORY_LABEL = Object.fromEntries(CREATOR_CATEGORIES.map((entry) => [entry.key, entry.label]));

/** Filterable creator list. Filtering is client-side because the directory is
 *  small enough that a round trip per tab would be slower than the filter. */
export function CreatorDirectory({
  creators,
  categories,
}: {
  creators: Creator[];
  categories: { key: string; label: string; blurb: string }[];
}) {
  const [active, setActive] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  const shown = useMemo(() => {
    const search = query.trim().toLowerCase();
    return creators.filter((creator) => {
      if (active && !creator.categories.includes(active as Creator["categories"][number])) return false;
      if (!search) return true;
      return creator.name.toLowerCase().includes(search)
        || creator.tagline.toLowerCase().includes(search);
    });
  }, [creators, active, query]);

  if (creators.length === 0) return null;

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => setActive(null)}
          className={`rounded-lg px-3 py-1.5 text-sm font-semibold transition ${
            active === null ? "bg-accent/20 text-accent" : "bg-white/[0.04] text-muted hover:text-text"
          }`}
        >
          All
          <span className="ml-1.5 text-xs font-normal text-faint">{creators.length}</span>
        </button>
        {categories.map((category) => (
          <button
            key={category.key}
            onClick={() => setActive(category.key === active ? null : category.key)}
            title={category.blurb}
            className={`rounded-lg px-3 py-1.5 text-sm font-semibold transition ${
              active === category.key ? "bg-accent/20 text-accent" : "bg-white/[0.04] text-muted hover:text-text"
            }`}
          >
            {category.label}
          </button>
        ))}
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search creators…"
          className="ml-auto min-w-44 rounded-lg border border-line bg-white/[0.04] px-3 py-1.5 text-sm text-text outline-none focus:border-accent/50"
        />
      </div>

      <div className="mt-5 grid gap-4 md:grid-cols-2">
        {shown.map((creator) => (
          <CreatorCard key={creator.name} creator={creator} />
        ))}
      </div>

      {shown.length === 0 && (
        <p className="mt-6 text-center text-sm text-faint">No creator matches that filter.</p>
      )}
    </div>
  );
}

function CreatorCard({ creator }: { creator: Creator }) {
  const primary = creator.links.youtube ?? Object.values(creator.links)[0];

  return (
    <Card className="glass-hover flex h-full flex-col p-5">
      <div className="flex items-start gap-3">
        {creator.avatar ? (
          <img
            src={creator.avatar}
            alt=""
            width={48}
            height={48}
            className="h-12 w-12 shrink-0 rounded-full ring-1 ring-white/10"
            loading="lazy"
            referrerPolicy="no-referrer"
          />
        ) : (
          <span className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-accent/15 text-lg font-bold text-accent">
            {creator.name.slice(0, 1).toUpperCase()}
          </span>
        )}
        <div className="min-w-0 flex-1">
          <h3 className="truncate font-semibold">
            {primary ? (
              <a href={primary} target="_blank" rel="noopener noreferrer" className="transition hover:text-accent">
                {creator.name}
              </a>
            ) : (
              creator.name
            )}
          </h3>
          <p className="mt-0.5 text-sm leading-relaxed text-muted">{creator.tagline}</p>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {creator.categories.map((category) => (
          <span key={category} className="rounded-md bg-white/[0.06] px-2 py-0.5 text-[0.65rem] font-semibold text-muted">
            {CATEGORY_LABEL[category] ?? category}
          </span>
        ))}
        {creator.languages?.map((language) => (
          <span key={language} className="rounded-md bg-accent/10 px-2 py-0.5 text-[0.65rem] font-semibold text-accent">
            {language}
          </span>
        ))}
      </div>

      <div className="mt-3 flex flex-1 flex-wrap items-end gap-2">
        {PLATFORMS.filter((platform) => creator.links[platform.key]).map((platform) => (
          <a
            key={platform.key}
            href={creator.links[platform.key]}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-lg border border-line bg-white/[0.03] px-2.5 py-1 text-xs font-semibold text-muted transition hover:border-accent/50 hover:text-text"
          >
            {PLATFORM_LABEL[platform.key]}
          </a>
        ))}
      </div>
    </Card>
  );
}
