"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useAccount } from "@/components/account-provider";
import { GoogleSignInButton } from "@/components/google-sign-in";

/* eslint-disable @next/next/no-img-element */

/**
 * Nav-bar account control. Signed out it offers Google sign-in (and says what
 * signing in buys you: another 10 build generations a day). Signed in it shows
 * the avatar, today's remaining generations, and sign-out.
 */
export function AccountMenu({ compact = false }: { compact?: boolean }) {
  const { user, quota, authConfigured, loading, signOut } = useAccount();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  // Nothing to offer when the deployment has no Google credentials configured.
  if (loading || !authConfigured) return null;

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className={
          user
            ? "flex items-center gap-2 rounded-full border border-line p-0.5 pr-2.5 text-sm font-medium text-muted transition hover:border-accent/50 hover:text-text"
            : `rounded-lg bg-accent/15 px-3 py-2 text-sm font-semibold text-accent transition hover:bg-accent/25 ${compact ? "w-full" : ""}`
        }
      >
        {user ? (
          <>
            {user.picture ? (
              <img src={user.picture} alt="" width={26} height={26} className="h-[26px] w-[26px] rounded-full" referrerPolicy="no-referrer" />
            ) : (
              <span className="grid h-[26px] w-[26px] place-items-center rounded-full bg-accent/20 text-[0.7rem] font-bold text-accent">
                {user.name.slice(0, 1).toUpperCase()}
              </span>
            )}
            <span className="hidden max-w-[9rem] truncate sm:inline">{user.name}</span>
          </>
        ) : (
          "Sign in"
        )}
      </button>

      {open && (
        <div className={`glass-menu absolute z-50 mt-2 w-72 rounded-xl p-4 ${compact ? "left-0" : "right-0"}`}>
          {user ? (
            <>
              <p className="truncate text-sm font-semibold text-text">{user.name}</p>
              <p className="truncate text-xs text-faint">{user.email}</p>
              {quota && (
                <p className="mt-3 rounded-lg bg-white/[0.05] px-3 py-2 text-xs text-muted">
                  {quota.unlimited ? (
                    <span className="font-semibold text-accent">Unlimited build generations.</span>
                  ) : (
                    <>
                      <span className="font-semibold text-accent">{quota.remaining}</span> of {quota.limit} build
                      generations left today.
                    </>
                  )}
                </p>
              )}
              <Link
                href="/albums"
                onClick={() => setOpen(false)}
                className="mt-3 block rounded-lg bg-accent/15 px-3 py-2 text-sm font-semibold text-accent transition hover:bg-accent/25"
              >
                Your build albums
              </Link>
              <button
                onClick={async () => {
                  await signOut();
                  setOpen(false);
                }}
                className="mt-3 w-full rounded-lg border border-line px-3 py-2 text-sm font-medium text-muted transition hover:text-text"
              >
                Sign out
              </button>
            </>
          ) : (
            <>
              <p className="text-sm font-semibold text-text">Sign in with Google</p>
              <p className="mt-1 text-xs leading-relaxed text-muted">
                Unlocks 10 more build generations each day, on top of the free 10.
              </p>
              <div className="mt-3">
                <GoogleSignInButton onDone={() => setOpen(false)} />
              </div>
              <p className="mt-3 text-[0.65rem] leading-relaxed text-faint">
                We only store your Google name, email and avatar to count your daily generations.
              </p>
            </>
          )}
        </div>
      )}
    </div>
  );
}
