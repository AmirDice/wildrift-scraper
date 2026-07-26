"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useAccount } from "@/components/account-provider";
import { GoogleSignInButton } from "@/components/google-sign-in";
import { Card } from "@/components/ui";

export interface AlbumSummary {
  id: string;
  title: string;
  description?: string;
  ownerName: string;
  buildCount: number;
  champions: string[];
  updatedAt: string;
}

/** The player's album shelf: create, browse, and jump into a blend. */
export function AlbumsView() {
  const { user, authConfigured, loading } = useAccount();
  const [albums, setAlbums] = useState<AlbumSummary[] | null>(null);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/albums", { cache: "no-store" });
      if (!res.ok) return;
      const data = (await res.json()) as { albums: AlbumSummary[] };
      setAlbums(data.albums);
    } catch {
      /* leave the shelf empty */
    }
  }, []);

  useEffect(() => {
    if (!user) return;
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [user, load]);

  const create = async () => {
    if (!title.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/albums", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title }),
      });
      const data = (await res.json()) as { error?: string };
      if (!res.ok) setError(data.error ?? "Could not create that album.");
      else {
        setTitle("");
        await load();
      }
    } catch {
      setError("Could not create that album.");
    } finally {
      setBusy(false);
    }
  };

  if (loading) return null;

  if (!user) {
    return (
      <Card className="p-6 text-center">
        <h2 className="text-lg font-semibold">Albums live with your account</h2>
        <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-muted">
          Sign in to keep collections of builds: your one-tricks, the picks you are learning, the
          loadouts you want to try next patch. Then blend them with a friend to see what you both play.
        </p>
        {authConfigured ? (
          <div className="mt-4 flex justify-center">
            <GoogleSignInButton />
          </div>
        ) : (
          <p className="mt-4 text-xs text-faint">Sign-in is not configured on this deployment yet.</p>
        )}
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <Card className="p-5">
        <h2 className="font-semibold">New album</h2>
        <p className="mt-0.5 text-sm text-muted">
          Name it after what it is for: &ldquo;Jungle comfort picks&rdquo;, &ldquo;Climbing to Sovereign&rdquo;,
          &ldquo;Builds to test in 7.3&rdquo;.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            onKeyDown={(event) => event.key === "Enter" && void create()}
            maxLength={60}
            placeholder="Album name…"
            className="min-w-56 flex-1 rounded-lg border border-line bg-white/[0.04] px-3 py-2 text-sm text-text outline-none focus:border-accent/50"
          />
          <button
            onClick={create}
            disabled={!title.trim() || busy}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-bold text-black transition hover:opacity-90 disabled:opacity-40"
          >
            Create
          </button>
        </div>
        {error && <p className="mt-2 text-xs text-bad">{error}</p>}
      </Card>

      {albums == null ? (
        <p className="text-sm text-faint">Loading your albums…</p>
      ) : albums.length === 0 ? (
        <Card className="p-6 text-center">
          <p className="text-sm text-muted">
            No albums yet. Create one above, then use <span className="text-text">Save to album</span> on any
            build in the Build Optimizer or Counter Builder.
          </p>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {albums.map((album) => (
            <Link key={album.id} href={`/albums/${album.id}`}>
              <Card className="glass-hover flex h-full flex-col p-5">
                <div className="flex items-baseline justify-between gap-3">
                  <h3 className="font-semibold">{album.title}</h3>
                  <span className="shrink-0 text-xs text-faint">
                    {album.buildCount} {album.buildCount === 1 ? "build" : "builds"}
                  </span>
                </div>
                {album.description && <p className="mt-1 text-sm text-muted">{album.description}</p>}
                <p className="mt-3 flex-1 text-xs text-muted">
                  {album.champions.length > 0 ? album.champions.join(" · ") : "Empty for now"}
                </p>
                <span className="mt-3 text-sm font-semibold text-accent">Open album →</span>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
