"use client";

import { useState } from "react";
import { track } from "@/components/share-build";

/**
 * "Permanent link": snapshots the build server-side and copies /b/{id}.
 *
 * Different job from ShareBuildButton, which shares the GENERATOR page: that
 * link regenerates and can drift with the patch, while this one is the exact
 * build the player is looking at, frozen. Created lazily on first click and
 * remembered, so mashing the button never mints duplicate records.
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
  };
}) {
  const [state, setState] = useState<"idle" | "busy" | "copied" | "error">("idle");
  const [id, setId] = useState<string | null>(null);

  const share = async () => {
    if (state === "busy") return;
    setState("busy");
    try {
      let shareId = id;
      if (!shareId) {
        const res = await fetch("/api/share-build", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(build),
        });
        const data = (await res.json()) as { id?: string; error?: string };
        if (!res.ok || !data.id) throw new Error(data.error ?? "share failed");
        shareId = data.id;
        setId(shareId);
        track("build_shared");
      }
      const url = `${window.location.origin}/b/${shareId}`;
      await navigator.clipboard.writeText(url);
      setState("copied");
      window.setTimeout(() => setState("idle"), 2000);
    } catch {
      setState("error");
      window.setTimeout(() => setState("idle"), 2500);
    }
  };

  return (
    <button
      onClick={share}
      title="Create a permanent page for this exact build and copy its link"
      className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-white/[0.03] px-3 py-1.5 text-xs font-semibold text-muted transition hover:border-accent/50 hover:text-text"
    >
      <LinkIcon />
      {state === "busy" ? "Creating…"
        : state === "copied" ? "Link copied"
        : state === "error" ? "Try again"
        : "Permanent link"}
    </button>
  );
}

function LinkIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="2" strokeLinecap="round" aria-hidden>
      <path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7" />
      <path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7" />
    </svg>
  );
}
