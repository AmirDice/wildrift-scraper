"use client";

import { useAccount } from "@/components/account-provider";
import { BUILD_TOOLS_LIVE } from "@/lib/flags";

/**
 * Client-side twin of access.buildToolsVisible().
 *
 * BUILD_TOOLS_LIVE is inlined at build time, so a client component cannot know
 * that *this particular visitor* is holding a beta invite. The grant arrives
 * with the session payload instead, and every client surface that hides the
 * build tools asks this rather than the flag directly -- otherwise a beta
 * tester would reach /build by URL but find no link to it anywhere.
 *
 * Returns false while the session is still loading, so the links do not flash
 * in and out for visitors who have no invite.
 */
export function useBuildToolsVisible(): boolean {
  const { access, loading } = useAccount();
  if (BUILD_TOOLS_LIVE) return true;
  return !loading && Boolean(access?.beta);
}
