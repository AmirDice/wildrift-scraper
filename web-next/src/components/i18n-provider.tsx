"use client";

import { createContext, useContext, useMemo } from "react";
import { makeT, type TFunction, type UiTable } from "@/lib/ui-i18n";

/**
 * Client side of lib/ui-i18n.ts: the [lang] layout passes the current
 * language and its one table; client components call useT() and useLp().
 * Outside the shared tree (no provider) everything is English.
 */
const Ctx = createContext<{ lang: string; table: UiTable }>({ lang: "en", table: {} });

export function I18nProvider({ lang, table, children }: { lang: string; table: UiTable; children: React.ReactNode }) {
  const value = useMemo(() => ({ lang, table }), [lang, table]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useT(): TFunction {
  const { table } = useContext(Ctx);
  return useMemo(() => makeT(table), [table]);
}

export function useLang(): string {
  return useContext(Ctx).lang;
}

/** Site path in the current language (English stays unprefixed). */
export function useLp(): (path: string) => string {
  const { lang } = useContext(Ctx);
  return (path: string) => (lang === "en" ? path : `/${lang}${path === "/" ? "" : path}`);
}
