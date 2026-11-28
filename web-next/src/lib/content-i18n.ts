import "server-only";
import { createHash } from "node:crypto";
import zh from "@/i18n/content/zh.json";
import vi from "@/i18n/content/vi.json";
import tr from "@/i18n/content/tr.json";
import fr from "@/i18n/content/fr.json";
import pl from "@/i18n/content/pl.json";
import ko from "@/i18n/content/ko.json";
import es from "@/i18n/content/es.json";

/**
 * Translated DATA text (2026-11-28): ability names and descriptions, and
 * patch-change history. Unlike interface strings (lib/ui-i18n.ts) these are
 * long, fixed texts machine-translated once by scripts/translate_content.py
 * and stored in src/i18n/content/<lang>.json, keyed by the first 12 hex of
 * the SHA-1 of the English text. A changed or new English text has a new key,
 * so a re-run after a patch translates only what changed; anything missing
 * falls back to English.
 *
 * Imported statically, not read from disk: Vercel ships only files it can
 * trace from imports, so an fs read of src/ would find nothing in production
 * and silently serve English. "server-only" keeps the tables out of client
 * bundles.
 */
const TABLES: Record<string, Record<string, string>> = { zh, vi, tr, fr, pl, ko, es };

export const contentKey = (text: string): string =>
  createHash("sha1").update(text, "utf8").digest("hex").slice(0, 12);

/** The text in `lang`, or the English text when there is no translation. */
export function tc(lang: string, text: string | null | undefined): string {
  if (!text) return text ?? "";
  if (lang === "en") return text;
  return TABLES[lang]?.[contentKey(text)] ?? text;
}
