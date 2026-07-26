"use client";

import { useState } from "react";

/** Fire-and-forget usage counter. Never blocks or fails the interaction. */
export function track(event: string) {
  try {
    void fetch("/api/events", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event }),
      keepalive: true,
    });
  } catch {
    /* ignore */
  }
}

function ShareIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 3v13" />
      <path d="m8 7 4-4 4 4" />
      <path d="M5 13v5a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-5" />
    </svg>
  );
}

/**
 * Share control for any build on the site.
 *
 * `path` is the deep link that reproduces the build (champion + variant, or the
 * generator inputs). Uses the native share sheet on mobile and falls back to
 * copying the link, which is what most desktop users want anyway.
 */
export function ShareBuildButton({
  path,
  title,
  text,
  label = "Share",
  className = "",
}: {
  path: string;
  title: string;
  text?: string;
  label?: string;
  className?: string;
}) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");

  const share = async () => {
    const url = typeof window === "undefined" ? path : new URL(path, window.location.origin).toString();
    track("build_shared");
    const payload = { title, text: text ?? title, url };

    if (typeof navigator !== "undefined" && typeof navigator.share === "function") {
      try {
        await navigator.share(payload);
        return;
      } catch {
        /* user dismissed the sheet, or the browser refused: fall through to copy */
      }
    }
    try {
      await navigator.clipboard.writeText(url);
      setState("copied");
      window.setTimeout(() => setState("idle"), 2000);
    } catch {
      setState("failed");
      window.setTimeout(() => setState("idle"), 2500);
    }
  };

  return (
    <button
      onClick={share}
      title={`Share this build: ${title}`}
      className={`inline-flex items-center gap-1.5 rounded-lg border border-line bg-white/[0.03] px-3 py-1.5 text-xs font-semibold text-muted transition hover:border-accent/50 hover:text-text ${className}`}
    >
      <ShareIcon />
      {state === "copied" ? "Link copied" : state === "failed" ? "Copy failed" : label}
    </button>
  );
}
