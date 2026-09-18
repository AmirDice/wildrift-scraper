"use client";

import { useEffect, useState } from "react";
import runeIconsData from "@/data/rune_icons.json";
import { BUILD_SERVERS, SERVER_GAP, SERVER_LABEL, type BuildServer, type ServerBuild } from "@/lib/server-build";

/** Rune name to picture. 2.4KB for 53 runes, and it covers every rune name the
 *  ladder records contain (checked across all 141), so the items in this card
 *  are no longer the only things in it with a face. */
const RUNE_ICONS = runeIconsData as Record<string, string>;

/* eslint-disable @next/next/no-img-element */

/**
 * What the top 50 build, per server.
 *
 * The site already splits win rates by board -- EU, NA and China disagree
 * about who is strong -- and they disagree about what to buy for the same
 * reason. One merged "most common build" hides exactly the thing worth
 * knowing, so each server answers for itself here.
 *
 * A server with nothing to show says WHY, in its own words. That matters most
 * for China: Tencent publishes win, pick and ban rates and no item data at
 * all, so that tab is not "loading" or "coming soon", it is a wall. Saying so
 * costs one line and stops it reading as a bug.
 *
 * The data is per-champion and passed in from the server component: the full
 * per-server records are ~100KB each, and no champion page needs 141 of them
 * in the browser.
 */

export function ServerBuilds({
  champion,
  builds,
  gaps,
  collected,
}: {
  champion: string;
  builds: Partial<Record<BuildServer, ServerBuild | null>>;
  /** Why a server is empty, when it is. */
  gaps: Record<BuildServer, string>;
  /** When each server's boards were collected, for the honesty line. */
  collected?: Partial<Record<BuildServer, string>>;
}) {
  // Open on a server that actually has something, so the card never greets
  // anyone with an empty tab when a filled one exists.
  const first = BUILD_SERVERS.find((s) => builds[s]) ?? "eu";
  const [server, setServer] = useState<BuildServer>(first);
  const build = builds[server] ?? null;

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        {BUILD_SERVERS.map((s) => (
          <button
            key={s}
            onClick={() => setServer(s)}
            className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
              server === s ? "bg-accent text-white"
                : builds[s] ? "glass text-muted hover:text-text"
                : "glass text-faint hover:text-muted"
            }`}
          >
            {SERVER_LABEL[s]}
            {!builds[s] && <span className="ml-1 opacity-60">·</span>}
          </button>
        ))}
      </div>

      {build ? (
        <>
          <div className="mt-4 flex flex-wrap items-start gap-2.5">
            {build.items.map((it, i) => (
              <span key={it.slug} className="w-16 text-center">
                <img src={it.icon} alt={it.name} loading="lazy"
                  className="mx-auto h-11 w-11 rounded-lg border border-line" />
                <span className="mt-1 block text-[10px] leading-tight text-muted">
                  {i + 1}. {it.name}
                </span>
              </span>
            ))}
            {build.boots && (
              <span className="w-16 text-center">
                <img src={build.boots.icon} alt={build.boots.name} loading="lazy"
                  className="mx-auto h-11 w-11 rounded-lg border border-line" />
                <span className="mt-1 block text-[10px] leading-tight text-muted">
                  {build.boots.name}
                </span>
              </span>
            )}
          </div>
          {build.runes.keystone && (
            <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 text-xs text-muted">
              {[
                { name: build.runes.keystone, keystone: true, flex: false },
                ...build.runes.minors.map((name) => ({ name, keystone: false, flex: false })),
                ...(build.runes.flex
                  ? [{ name: build.runes.flex, keystone: false, flex: true }]
                  : []),
              ].map((rune, i) => (
                <span key={`${rune.name}-${i}`} className="flex items-center gap-1.5">
                  {RUNE_ICONS[rune.name] && (
                    <img
                      src={RUNE_ICONS[rune.name]}
                      alt=""
                      loading="lazy"
                      className={`rounded-full ${rune.keystone ? "h-7 w-7" : "h-6 w-6"}`}
                    />
                  )}
                  <span className={rune.keystone ? "font-semibold text-text" : ""}>
                    {rune.name}
                    {rune.flex && <span className="ml-1 text-faint">(flex)</span>}
                  </span>
                </span>
              ))}
            </div>
          )}
          <p className="mt-2 text-[11px] text-faint">
            {build.sample
              ? `${champion}'s most-built item on ${SERVER_LABEL[server]}: ${build.sample.count} of ${build.sample.of} top-50 players`
              : `From the ${SERVER_LABEL[server]} top-50 boards`}
            {collected?.[server] ? ` · collected ${collected[server]}` : ""}
          </p>
        </>
      ) : (
        <p className="mt-4 text-sm text-muted">{gaps[server]}</p>
      )}
    </div>
  );
}

/**
 * The same card, fetching its own champion.
 *
 * The Build Studio changes champion without navigating, so it cannot be
 * handed this from the server the way a champion page is; it asks
 * /api/ladder-build instead, which keeps the per-server records off the
 * browser bundle.
 */
export function ServerBuildsPanel({ champion }: { champion: string }) {
  const [data, setData] = useState<{
    builds: Partial<Record<BuildServer, ServerBuild | null>>;
    collected?: Partial<Record<BuildServer, string>>;
  } | null>(null);

  useEffect(() => {
    let live = true;
    setData(null);
    fetch(`/api/ladder-build?champion=${encodeURIComponent(champion)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (live && d) setData(d); })
      .catch(() => {});
    return () => { live = false; };
  }, [champion]);

  return (
    <div className="glass rounded-2xl p-4 sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-bold uppercase tracking-wide text-muted">
          Most-built by server
        </h3>
        <span className="text-[11px] text-faint">what the top 50 hold, not what we recommend</span>
      </div>
      <div className="mt-3">
        {data ? (
          <ServerBuilds
            champion={champion}
            builds={data.builds}
            gaps={SERVER_GAP}
            collected={data.collected}
          />
        ) : (
          <p className="text-sm text-faint">Reading the boards…</p>
        )}
      </div>
    </div>
  );
}
