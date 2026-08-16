"use client";

import Link from "next/link";
import { CURRENT_PATCH } from "@/lib/patch";
import { useCallback, useEffect, useState } from "react";
import { Card } from "@/components/ui";
import { ShareBuildButton } from "@/components/share-build";

/* eslint-disable @next/next/no-img-element */

interface SavedBuild {
  id: string;
  champion: string;
  championSlug: string;
  source: "recommended" | "generated" | "custom";
  role?: string;
  variant?: string;
  bias?: string;
  patch?: string;
  items: string[];
  runes: string[];
  note?: string;
  addedAt: string;
}

interface Album {
  id: string;
  title: string;
  description?: string;
  ownerName: string;
  builds: SavedBuild[];
  updatedAt: string;
}

const SOURCE_LABEL: Record<SavedBuild["source"], string> = {
  recommended: "Recommended",
  generated: "Generated",
  custom: "Custom",
};

/** One album: its builds, and owner-only controls to prune it. */
export function AlbumDetail({ id }: { id: string }) {
  const [album, setAlbum] = useState<Album | null>(null);
  const [isOwner, setIsOwner] = useState(false);
  const [missing, setMissing] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`/api/albums/${id}`, { cache: "no-store" });
      if (res.status === 404) {
        setMissing(true);
        return;
      }
      if (!res.ok) return;
      const data = (await res.json()) as { album: Album; isOwner: boolean };
      setAlbum(data.album);
      setIsOwner(data.isOwner);
    } catch {
      /* leave it loading */
    }
  }, [id]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const remove = async (buildId: string) => {
    try {
      const res = await fetch(`/api/albums/${id}/builds?buildId=${encodeURIComponent(buildId)}`, {
        method: "DELETE",
      });
      if (res.ok) await load();
    } catch {
      /* ignore */
    }
  };

  if (missing) {
    return (
      <Card className="p-6 text-center">
        <p className="text-sm text-muted">That album does not exist, or it was deleted.</p>
        <Link href="/albums" className="mt-3 inline-block text-sm font-semibold text-accent">
          Back to albums →
        </Link>
      </Card>
    );
  }
  if (!album) return <p className="text-sm text-faint">Loading album…</p>;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-accent">
            Album by {album.ownerName}
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight">{album.title}</h1>
          {album.description && <p className="mt-1 text-muted">{album.description}</p>}
          <p className="mt-1 text-sm text-faint">
            {album.builds.length} {album.builds.length === 1 ? "build" : "builds"}
          </p>
        </div>
        <ShareBuildButton
          path={`/albums/${album.id}`}
          title={`${album.title} on WrTrueMeta`}
          text={`${album.ownerName}'s Wild Rift build album: ${album.title}.`}
          label="Share album"
        />
      </div>

      {album.builds.length === 0 ? (
        <Card className="p-6 text-center">
          <p className="text-sm text-muted">
            Nothing saved here yet. Open any build and use <span className="text-text">Save to album</span>.
          </p>
        </Card>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {album.builds.map((build) => (
            <Card key={build.id} className="p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link href={`/champions/${build.championSlug}`} className="font-semibold transition hover:text-accent">
                      {build.champion}
                    </Link>
                    <span className="rounded bg-white/[0.07] px-1.5 py-0.5 text-[0.6rem] font-bold uppercase tracking-wide text-muted">
                      {SOURCE_LABEL[build.source]}
                    </span>
                    {build.bias && build.bias !== "balanced" && (
                      <span className="rounded-md bg-gold/15 px-1.5 py-0.5 text-[0.65rem] font-semibold text-gold">
                        {build.bias.replace("max_", "max ").replace("_", " ")}
                      </span>
                    )}
                    {build.variant && (
                      <span className="rounded bg-accent/15 px-1.5 py-0.5 text-[0.6rem] font-bold uppercase tracking-wide text-accent">
                        {build.variant}
                      </span>
                    )}
                  </div>
                  {build.role && <p className="mt-0.5 text-xs text-muted">{build.role}</p>}
                </div>
                {isOwner && (
                  <button
                    onClick={() => remove(build.id)}
                    aria-label={`Remove ${build.champion}`}
                    className="shrink-0 rounded-md px-2 py-1 text-xs text-faint transition hover:bg-bad/15 hover:text-bad"
                  >
                    Remove
                  </button>
                )}
              </div>

              {build.items.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {build.items.map((slug) => (
                    <img
                      key={slug}
                      src={`/items/${slug}.webp`}
                      alt={slug}
                      title={slug}
                      width={30}
                      height={30}
                      className="rounded ring-1 ring-white/10"
                    />
                  ))}
                </div>
              )}
              {build.note && <p className="mt-2 text-xs text-muted">{build.note}</p>}
              {/* The retention loop: a patch lands, saved builds say so, and
                  one click regenerates with the same champion, playstyle and
                  bias. Only shown when we KNOW the build predates the current
                  patch; builds saved before patch stamping say that instead of
                  guessing. */}
              {CURRENT_PATCH && build.patch && build.patch !== CURRENT_PATCH && (
                <div className="mt-2 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-500/30 bg-amber-500/[0.08] px-2.5 py-1.5">
                  <p className="text-xs text-amber-300">
                    Saved on patch {build.patch}; the game is on {CURRENT_PATCH} now.
                  </p>
                  <Link
                    href={`/build?champion=${build.championSlug}&tab=generate${build.variant && build.variant !== "counter" ? `&variant=${encodeURIComponent(build.variant)}` : ""}${build.bias && build.bias !== "balanced" ? `&bias=${build.bias}` : ""}`}
                    className="text-xs font-bold text-amber-200 underline-offset-2 transition hover:underline"
                  >
                    Re-optimize for {CURRENT_PATCH} →
                  </Link>
                </div>
              )}
              <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1">
                <Link
                  href={`/build?champion=${build.championSlug}${build.variant ? `&variant=${build.variant}` : ""}`}
                  className="text-xs font-semibold text-accent transition hover:opacity-80"
                >
                  Open in Build Studio →
                </Link>
                {build.items.length > 0 && (
                  <Link
                    href={`/build?champion=${build.championSlug}&tab=lab&items=${build.items.join(",")}&runes=${encodeURIComponent(build.runes.join(","))}`}
                    className="text-xs font-semibold text-accent transition hover:opacity-80"
                    title="Load this exact loadout into the Custom Build Lab"
                  >
                    Open in Custom Lab →
                  </Link>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
