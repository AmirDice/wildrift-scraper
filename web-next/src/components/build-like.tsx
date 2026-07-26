"use client";

import { useCallback, useEffect, useState } from "react";

const storageKey = (buildId: string) => `wtm_like_${buildId}`;

function ThumbUp({ filled = false }: { filled?: boolean }) {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill={filled ? "currentColor" : "none"}
      stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M7 22V11" />
      <path d="M11 5.5 10.2 9a1 1 0 0 0 1 1.2h5.4a2 2 0 0 1 1.95 2.44l-1.1 5A2 2 0 0 1 15.5 19H7V11l2.6-6.2A1.6 1.6 0 0 1 11 4a1.4 1.4 0 0 1 1 1.5Z" />
    </svg>
  );
}

/**
 * Like button for a curated recommended build.
 *
 * The count stays hidden until at least one person has liked the build: a
 * visible "0" reads as a verdict on the build, which is not what an empty
 * counter means. Whether *you* liked it is remembered in localStorage, so the
 * button has no account requirement.
 */
export function BuildLikeButton({ buildId, className = "" }: { buildId: string; className?: string }) {
  const [count, setCount] = useState<number | null>(null);
  const [liked, setLiked] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(() => {
      try {
        setLiked(localStorage.getItem(storageKey(buildId)) === "1");
      } catch {
        /* storage can be unavailable */
      }
    }, 0);
    void (async () => {
      try {
        const res = await fetch(`/api/likes?id=${encodeURIComponent(buildId)}`, { cache: "no-store" });
        if (!res.ok || cancelled) return;
        const data = (await res.json()) as { count: number };
        setCount(data.count);
      } catch {
        /* leave the count hidden */
      }
    })();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [buildId]);

  const toggle = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    const next = !liked;
    setLiked(next);
    setCount((current) => Math.max(0, (current ?? 0) + (next ? 1 : -1)));
    try {
      localStorage.setItem(storageKey(buildId), next ? "1" : "0");
    } catch {
      /* ignore */
    }
    try {
      const res = await fetch("/api/likes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: buildId, liked: next }),
      });
      if (res.ok) {
        const data = (await res.json()) as { count: number };
        setCount(data.count);
      }
    } catch {
      /* the optimistic count stands */
    } finally {
      setBusy(false);
    }
  }, [buildId, busy, liked]);

  const showCount = (count ?? 0) > 0;

  return (
    <button
      onClick={toggle}
      aria-pressed={liked}
      title={liked ? "Remove your like" : "Like this build"}
      className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold transition ${
        liked
          ? "border-emerald-400/50 bg-emerald-400/15 text-emerald-300"
          : "border-line bg-white/[0.03] text-muted hover:border-emerald-400/40 hover:text-emerald-300"
      } ${className}`}
    >
      <ThumbUp filled={liked} />
      {liked ? "Liked" : "Like"}
      {showCount && <span className="font-bold tabular-nums">{count}</span>}
    </button>
  );
}
