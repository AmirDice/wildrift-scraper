/**
 * Interface translation for the shared page tree (app/[lang]), 2026-11-28.
 *
 * Strings are written in English in the components and looked up by that
 * English text: t("Best {name} player"), with {placeholders} filled from
 * `vars`. A missing translation falls back to English, so a new string never
 * breaks a page; scripts/extract_ui_strings.py lists every t() key and
 * scripts/translate_ui_strings.py fills the per-language tables in
 * src/i18n/ui/<lang>.json.
 *
 * Server components: getT(lang). Client components: useT() from
 * components/i18n-provider.tsx, which the [lang] layout feeds with the one
 * table that page needs, so no client bundle carries every language.
 */
import zh from "@/i18n/ui/zh.json";
import vi from "@/i18n/ui/vi.json";
import tr from "@/i18n/ui/tr.json";
import fr from "@/i18n/ui/fr.json";
import pl from "@/i18n/ui/pl.json";
import ko from "@/i18n/ui/ko.json";
import es from "@/i18n/ui/es.json";

export type UiTable = Record<string, string>;
const TABLES: Record<string, UiTable> = { zh, vi, tr, fr, pl, ko, es };

export function uiTable(lang: string): UiTable {
  return TABLES[lang] ?? {};
}

export type TFunction = (english: string, vars?: Record<string, string | number>) => string;

export function makeT(table: UiTable): TFunction {
  return (english, vars) => {
    let out = table[english] ?? english;
    if (vars) for (const [k, v] of Object.entries(vars)) out = out.split(`{${k}}`).join(String(v));
    return out;
  };
}

export const getT = (lang: string): TFunction => makeT(uiTable(lang));
