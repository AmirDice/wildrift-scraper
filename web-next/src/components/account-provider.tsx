"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

export interface AccountUser {
  name: string;
  email: string;
  picture: string;
}

export interface QuotaState {
  used: number;
  limit: number;
  remaining: number;
  signedIn: boolean;
  canUnlockBySigningIn: boolean;
  resetAt: number;
  unlimited?: boolean;
}

/** An access code the visitor is carrying (beta invite or referral link). */
export interface AccessState {
  code: string;
  label: string;
  /** Early access to the build tools while they are still gated. */
  beta: boolean;
  /** Exempt from the daily generation cap. */
  unlimited: boolean;
}

interface AccountValue {
  user: AccountUser | null;
  quota: QuotaState | null;
  access: AccessState | null;
  /** False when the deployment has no Google client id / auth secret set. */
  authConfigured: boolean;
  loading: boolean;
  refresh: () => Promise<void>;
  signOut: () => Promise<void>;
}

const AccountContext = createContext<AccountValue>({
  user: null,
  quota: null,
  access: null,
  authConfigured: false,
  loading: true,
  refresh: async () => {},
  signOut: async () => {},
});

/** Session + daily build quota, fetched once and shared by the nav and the
 *  build tools so they never disagree about how many generations are left. */
export function AccountProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AccountUser | null>(null);
  const [quota, setQuota] = useState<QuotaState | null>(null);
  const [access, setAccess] = useState<AccessState | null>(null);
  const [authConfigured, setAuthConfigured] = useState(false);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch("/api/auth/me", { cache: "no-store" });
      if (!res.ok) return;
      const data = (await res.json()) as {
        user: AccountUser | null;
        quota: QuotaState;
        access: AccessState | null;
        authConfigured: boolean;
      };
      setUser(data.user);
      setQuota(data.quota);
      setAccess(data.access ?? null);
      setAuthConfigured(data.authConfigured);
    } catch {
      /* offline or the route is unavailable: leave the last known state */
    } finally {
      setLoading(false);
    }
  }, []);

  const signOut = useCallback(async () => {
    try {
      await fetch("/api/auth/signout", { method: "POST" });
    } catch {
      /* ignore */
    }
    setUser(null);
    await refresh();
  }, [refresh]);

  // Deferred by a tick so the first paint is never blocked on the session
  // round-trip (and so the state update is not synchronous inside the effect).
  useEffect(() => {
    const timer = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);

  const value = useMemo(
    () => ({ user, quota, access, authConfigured, loading, refresh, signOut }),
    [user, quota, access, authConfigured, loading, refresh, signOut],
  );

  return <AccountContext.Provider value={value}>{children}</AccountContext.Provider>;
}

export function useAccount(): AccountValue {
  return useContext(AccountContext);
}
