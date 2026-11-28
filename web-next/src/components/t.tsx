"use client";

import { useT } from "@/components/i18n-provider";

/**
 * Translated text node: <T>Most played</T>. Works inside server and client
 * components alike (it is a client component reading the [lang] layout's
 * table), so wrapping visible text needs no hooks or props in the parent.
 * English, or any string without a translation, renders unchanged.
 */
export function T({ children, vars }: { children: string; vars?: Record<string, string | number> }) {
  const t = useT();
  return <>{t(children, vars)}</>;
}
