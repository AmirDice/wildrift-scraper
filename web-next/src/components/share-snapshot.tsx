"use client";

import { useEffect, useRef, useState } from "react";
import { track } from "@/components/share-build";

/**
 * "Permanent link" and "Share as image": the two ways a build leaves the site.
 *
 * The permanent link snapshots the build server-side and copies /b/{id}; the
 * image builds a 1200x630 card whose data rides in the URL itself, so it
 * needs no snapshot and works even when the KV store is down.
 *
 * Both open a small popover first with one optional field: a display name,
 * stamped on the card and the permalink as "Built by X". Remembered in
 * localStorage so it is typed once, and sanitised server-side regardless of
 * what the client sends.
 */
export function ShareSnapshotButton({ build }: {
  build: {
    champion: string;
    championSlug: string;
    role?: string;
    playstyle?: string;
    bias?: string;
    patch?: string;
    items: string[];
    boots?: string;
    bootsUpgrade?: string;
    runes: string[];
    summoners?: string[];
  };
}) {
  const [open, setOpen] = useState(false);
  const [player, setPlayer] = useState("");
  const [state, setState] = useState<"idle" | "busy" | "copied" | "error">("idle");
  const [id, setId] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try {
      const saved = localStorage.getItem("wtm_player_name");
      if (saved) setPlayer(saved.slice(0, 24));
    } catch { /* private mode */ }
  }, []);

  useEffect(() => {
    if (!open) return;
    const onDoc = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const rememberName = () => {
    try {
      const trimmed = player.trim().slice(0, 24);
      if (trimmed) localStorage.setItem("wtm_player_name", trimmed);
      else localStorage.removeItem("wtm_player_name");
    } catch { /* ignore */ }
  };

  const payload = () => ({ ...build, player: player.trim().slice(0, 24) || undefined });

  const copyLink = async () => {
    if (state === "busy") return;
    setState("busy");
    rememberName();
    try {
      let shareId = id;
      if (!shareId) {
        const res = await fetch("/api/share-build", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload()),
        });
        const data = (await res.json()) as { id?: string; error?: string };
        if (!res.ok || !data.id) throw new Error(data.error ?? "share failed");
        shareId = data.id;
        setId(shareId);
        track("build_shared");
      }
      await navigator.clipboard.writeText(`${window.location.origin}/b/${shareId}`);
      setState("copied");
      window.setTimeout(() => setState("idle"), 2000);
    } catch {
      setState("error");
      window.setTimeout(() => setState("idle"), 2500);
    }
  };

  // The card's data rides in the URL (base64url JSON), validated server-side.
  const downloadImage = () => {
    rememberName();
    const encoded = btoa(JSON.stringify(payload()))
      .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
    const a = document.createElement("a");
    a.href = `/api/build-card?d=${encoded}`;
    a.download = `${build.championSlug}-build.png`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    track("build_shared");
  };

  return (
    <div ref={ref} className="relative inline-flex">
      <button
        onClick={() => setOpen((v) => !v)}
        title="Share this exact build: a permanent page or a card image"
        className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-white/[0.03] px-3 py-1.5 text-xs font-semibold text-muted transition hover:border-accent/50 hover:text-text"
      >
        <ImageIcon />
        Share build
      </button>

      {open && (
        <div className="glass-menu absolute right-0 top-full z-50 mt-2 w-72 rounded-xl p-3">
          <p className="text-xs font-bold uppercase tracking-wide text-faint">Share this build</p>
          <label className="mt-2 block text-xs text-muted" htmlFor="share-player-name">
            Your name on the card <span className="text-faint">(optional)</span>
          </label>
          <input
            id="share-player-name"
            value={player}
            onChange={(e) => setPlayer(e.target.value.slice(0, 24))}
            placeholder="Summoner name…"
            maxLength={24}
            className="mt-1 w-full rounded-lg border border-line bg-white/[0.04] px-2.5 py-1.5 text-xs text-text outline-none focus:border-accent/50"
          />
          <div className="mt-3 flex gap-2">
            <button
              onClick={downloadImage}
              title="Download a 1200x630 card, made for Discord and Reddit"
              className="flex-1 rounded-lg bg-accent px-3 py-1.5 text-xs font-bold text-black transition hover:opacity-90"
            >
              Download image
            </button>
            <button
              onClick={copyLink}
              title="Create a permanent page for this build and copy its link"
              className="flex-1 rounded-lg border border-line px-3 py-1.5 text-xs font-semibold text-muted transition hover:border-accent/50 hover:text-text"
            >
              {state === "busy" ? "Creating…"
                : state === "copied" ? "Link copied"
                : state === "error" ? "Try again"
                : "Copy link"}
            </button>
          </div>
          <p className="mt-2 text-[0.65rem] leading-relaxed text-faint">
            The image carries the build itself; the link opens a permanent page that unfurls
            as this card in Discord and Reddit.
          </p>
        </div>
      )}
    </div>
  );
}

function ImageIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="2" strokeLinecap="round" aria-hidden>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <circle cx="8.5" cy="8.5" r="1.5" />
      <path d="M21 15l-5-5L5 21" />
    </svg>
  );
}
