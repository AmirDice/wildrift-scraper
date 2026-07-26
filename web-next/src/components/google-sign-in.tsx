"use client";

import { useEffect, useRef, useState } from "react";
import { useAccount } from "@/components/account-provider";

/* Google Identity Services, loaded on demand. Typed narrowly: we only ever use
   initialize() and renderButton(). */
declare global {
  interface Window {
    google?: {
      accounts?: {
        id?: {
          initialize: (config: {
            client_id: string;
            callback: (response: { credential?: string }) => void;
            ux_mode?: "popup" | "redirect";
            auto_select?: boolean;
          }) => void;
          renderButton: (parent: HTMLElement, options: Record<string, unknown>) => void;
          disableAutoSelect?: () => void;
        };
      };
    };
  }
}

const CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID ?? "";
const GSI_SRC = "https://accounts.google.com/gsi/client";

let gsiPromise: Promise<void> | null = null;

function loadGsi(): Promise<void> {
  if (typeof window === "undefined") return Promise.resolve();
  if (window.google?.accounts?.id) return Promise.resolve();
  if (gsiPromise) return gsiPromise;
  gsiPromise = new Promise<void>((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(`script[src="${GSI_SRC}"]`);
    if (existing) {
      existing.addEventListener("load", () => resolve());
      existing.addEventListener("error", () => reject(new Error("gsi failed")));
      return;
    }
    const script = document.createElement("script");
    script.src = GSI_SRC;
    script.async = true;
    script.defer = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("gsi failed"));
    document.head.appendChild(script);
  });
  return gsiPromise;
}

/**
 * Renders Google's own "Sign in with Google" button. The ID token it returns is
 * posted to /api/auth/google, which verifies it and sets our session cookie.
 *
 * The GIS button is initialised exactly once per mount. Callers pass `onDone`
 * as an inline arrow, so it changes identity on every render; if the effect
 * depended on it, GIS would be torn down and re-rendered on every parent
 * render, stacking buttons and flickering. It is held in a ref instead, and
 * the effect runs only when the CLIENT_ID does -- i.e. once.
 */
export function GoogleSignInButton({ onDone }: { onDone?: () => void }) {
  const holder = useRef<HTMLDivElement>(null);
  const { refresh } = useAccount();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  // Latest onDone and refresh, without making them effect dependencies. Synced
  // in their own effect rather than during render (a ref write during render is
  // both a React rule violation and unreliable under concurrent rendering).
  const onDoneRef = useRef(onDone);
  const refreshRef = useRef(refresh);
  useEffect(() => {
    onDoneRef.current = onDone;
    refreshRef.current = refresh;
  });

  useEffect(() => {
    if (!CLIENT_ID) return;
    let cancelled = false;

    loadGsi()
      .then(() => {
        if (cancelled || !holder.current) return;
        const id = window.google?.accounts?.id;
        if (!id) return;
        // Re-rendering into a non-empty holder stacks a second button, so make
        // the render idempotent for the (rare) case the effect runs twice.
        holder.current.replaceChildren();
        id.initialize({
          client_id: CLIENT_ID,
          ux_mode: "popup",
          callback: async (response) => {
            if (!response.credential) return;
            setPending(true);
            setError(null);
            try {
              const res = await fetch("/api/auth/google", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ credential: response.credential }),
              });
              if (!res.ok) {
                const data = (await res.json().catch(() => null)) as { error?: string } | null;
                setError(data?.error ?? "Sign-in failed. Please try again.");
                return;
              }
              await refreshRef.current();
              onDoneRef.current?.();
            } catch {
              setError("Sign-in failed. Please try again.");
            } finally {
              if (!cancelled) setPending(false);
            }
          },
        });
        id.renderButton(holder.current, {
          theme: "filled_black",
          size: "large",
          shape: "pill",
          text: "signin_with",
          logo_alignment: "left",
          width: 240,
        });
      })
      .catch(() => setError("Could not reach Google sign-in. Check your connection and retry."));

    return () => {
      cancelled = true;
    };
  }, []);

  if (!CLIENT_ID) {
    return (
      <p className="text-xs text-faint">
        Google sign-in is not configured for this deployment.
      </p>
    );
  }

  return (
    <div>
      <div ref={holder} className="min-h-[40px]" aria-busy={pending} />
      {pending && <p className="mt-2 text-xs text-muted">Signing you in…</p>}
      {error && <p className="mt-2 text-xs text-bad">{error}</p>}
    </div>
  );
}
