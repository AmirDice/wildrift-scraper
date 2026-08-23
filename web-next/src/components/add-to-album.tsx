"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useAccount } from "@/components/account-provider";
import { GoogleSignInButton } from "@/components/google-sign-in";

interface AlbumSummary { id: string; title: string; buildCount: number }

export interface AlbumBuildPayload {
  champion: string;
  championSlug: string;
  source: "recommended" | "generated" | "custom";
  role?: string;
  variant?: string;
  /** Build Bias the build was generated with; absent means balanced. */
  bias?: string;
  /** Patch the build was generated on, so a saved build can say when it went stale. */
  patch?: string;
  items: string[];
  runes: string[];
}

function BookmarkIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M6 4h12v16l-6-4-6 4V4Z" />
    </svg>
  );
}

/**
 * "Save to album" for any build on the site.
 *
 * Signed out it explains what an album is and offers sign-in rather than
 * silently doing nothing; signed in it lists the player's albums and can create
 * one inline, so saving the first build never needs a detour to another page.
 */
export function AddToAlbumButton({ build, className = "" }: { build: AlbumBuildPayload; className?: string }) {
  const { user, authConfigured, loading } = useAccount();
  const [open, setOpen] = useState(false);
  const [albums, setAlbums] = useState<AlbumSummary[] | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/albums", { cache: "no-store" });
      if (!res.ok) return;
      const data = (await res.json()) as { albums: AlbumSummary[] };
      setAlbums(data.albums);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (!open || !user) return;
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [open, user, load]);

  // The menu renders in a portal at <body>, positioned from the button's
  // rect. Inside the card it was an `absolute z-50` child of a .glass panel,
  // and backdrop-filter makes every glass panel its own stacking context:
  // z-index inside one cannot climb over a sibling panel painted later, so
  // the menu slid under the next glass block (and under the glass nav bar).
  // Raising the card's own z-index papered over one case and not the others.
  const menuRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  useEffect(() => {
    if (!open) { setPos(null); return; }
    const place = () => {
      const r = ref.current?.getBoundingClientRect();
      if (!r) return;
      const width = 288;                                   // w-72
      const left = Math.max(8, Math.min(r.right - width, window.innerWidth - width - 8));
      setPos({ top: r.bottom + 8, left });
    };
    place();
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    const onDoc = (event: MouseEvent) => {
      const t = event.target as Node;
      if (ref.current?.contains(t) || menuRef.current?.contains(t)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => {
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("resize", place);
      document.removeEventListener("mousedown", onDoc);
    };
  }, [open]);

  const [savedTo, setSavedTo] = useState<string | null>(null);

  const save = async (albumId: string) => {
    if (busy) return;
    setBusy(true);
    setStatus(null);
    try {
      const res = await fetch(`/api/albums/${albumId}/builds`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(build),
      });
      const data = (await res.json()) as { error?: string };
      setStatus(res.ok ? "Saved" : data.error ?? "Could not save that.");
      if (res.ok) {
        setSavedTo(albumId);
        await load();
        // The popover closing used to take the only link to the album with it,
        // which read as the save vanishing. The confirmation link below the
        // button stays put instead.
        window.setTimeout(() => setOpen(false), 900);
      }
    } catch {
      setStatus("Could not save that.");
    } finally {
      setBusy(false);
    }
  };

  const createAndSave = async () => {
    if (!newTitle.trim() || busy) return;
    setBusy(true);
    setStatus(null);
    try {
      const res = await fetch("/api/albums", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: newTitle }),
      });
      const data = (await res.json()) as { album?: { id: string }; error?: string };
      if (!res.ok || !data.album) {
        setStatus(data.error ?? "Could not create that album.");
        return;
      }
      setNewTitle("");
      await save(data.album.id);
    } catch {
      setStatus("Could not create that album.");
    } finally {
      setBusy(false);
    }
  };

  if (loading || !authConfigured) return null;

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((value) => !value)}
        title="Save this build to one of your albums"
        className={`inline-flex items-center gap-1.5 rounded-lg border border-line bg-white/[0.03] px-3 py-1.5 text-xs font-semibold text-muted transition hover:border-accent/50 hover:text-text ${className}`}
      >
        <BookmarkIcon />
        {savedTo ? "Saved" : "Save to album"}
      </button>
      {savedTo && (
        <Link href={`/albums/${savedTo}`}
              className="ml-2 inline-flex items-center gap-1 text-xs font-semibold text-accent transition hover:opacity-80">
          View album →
        </Link>
      )}

      {open && pos && typeof document !== "undefined" && createPortal(
        <div ref={menuRef} style={{ position: "fixed", top: pos.top, left: pos.left }}
             className="glass-menu z-[90] w-72 rounded-xl p-3">
          {!user ? (
            <>
              <p className="text-sm font-semibold text-text">Keep this build</p>
              <p className="mt-1 text-xs leading-relaxed text-muted">
                Albums are collections of builds tied to your account. Sign in and this one goes straight
                into yours.
              </p>
              <div className="mt-3">
                <GoogleSignInButton />
              </div>
            </>
          ) : (
            <>
              <p className="text-xs font-bold uppercase tracking-wide text-faint">Save to</p>
              <div className="mt-2 max-h-48 space-y-1 overflow-y-auto">
                {albums == null && <p className="text-xs text-faint">Loading…</p>}
                {albums?.length === 0 && (
                  <p className="text-xs text-faint">No albums yet. Name one below.</p>
                )}
                {albums?.map((album) => (
                  <button
                    key={album.id}
                    onClick={() => save(album.id)}
                    disabled={busy}
                    className="flex w-full items-center justify-between gap-2 rounded-lg px-2.5 py-1.5 text-left text-sm text-muted transition hover:bg-white/[0.06] hover:text-text disabled:opacity-40"
                  >
                    <span className="min-w-0 truncate">{album.title}</span>
                    <span className="shrink-0 text-[0.65rem] text-faint">{album.buildCount}</span>
                  </button>
                ))}
              </div>
              <div className="mt-2 flex gap-1.5 border-t border-line/60 pt-2">
                <input
                  value={newTitle}
                  onChange={(event) => setNewTitle(event.target.value)}
                  onKeyDown={(event) => event.key === "Enter" && void createAndSave()}
                  maxLength={60}
                  placeholder="New album…"
                  className="min-w-0 flex-1 rounded-lg border border-line bg-white/[0.04] px-2.5 py-1.5 text-xs text-text outline-none focus:border-accent/50"
                />
                <button
                  onClick={createAndSave}
                  disabled={!newTitle.trim() || busy}
                  className="rounded-lg bg-accent/20 px-2.5 py-1.5 text-xs font-bold text-accent transition hover:bg-accent/30 disabled:opacity-40"
                >
                  Add
                </button>
              </div>
              {status && (
                <p className={`mt-2 text-xs ${status === "Saved" ? "text-emerald-300" : "text-bad"}`}>{status}</p>
              )}
              <Link
                href="/albums"
                className="mt-2 block border-t border-line/60 pt-2 text-xs font-semibold text-accent transition hover:opacity-80"
              >
                Manage albums →
              </Link>
            </>
          )}
        </div>,
        document.body,
      )}
    </div>
  );
}
