import Link from "next/link";
import { LOCALES, NATIVE_NAME, entityName, fmtPct, localizedPath, type Locale } from "@/lib/i18n";
import type { Dict } from "@/lib/i18n-dict";
import type { LoadoutRow } from "@/lib/cn-loadouts";

/** Loadout rows with names and numbers in the page's language. */
export function LocalizedRows({ rows, lang, t }: { rows: LoadoutRow[]; lang: Locale; t: Dict }) {
  if (!rows.length) return null;
  return (
    <ul className="mt-3 divide-y divide-white/[0.06]">
      {rows.map((row) => (
        <li key={row.entities.map((e) => e.name).join("+")} className="flex flex-wrap items-center gap-3 py-2.5">
          <span className="flex items-center gap-1.5">
            {row.entities.map((e) => (
              // eslint-disable-next-line @next/next/no-img-element
              <img key={e.name} src={e.icon} alt="" width={30} height={30} className="rounded-md ring-1 ring-white/10" />
            ))}
          </span>
          <span className="min-w-0 flex-1 text-sm text-text">
            {row.entities.map((e) => entityName(e.name, lang)).join(" + ")}
          </span>
          <span className="flex shrink-0 gap-3 text-xs tabular-nums">
            <span className={row.winRate >= 50 ? "text-emerald-300" : "text-rose-300"}>{fmtPct(lang, row.winRate)} {t.win}</span>
            <span className="text-muted">{fmtPct(lang, row.pickRate)} {t.pick}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

/**
 * Links to this page in every language. `path` is the English path; a
 * language without the page (`available` false) is left out.
 */
export function LanguageSwitcher({ path, current, label }: { path: string; current: Locale | "en"; label: string }) {
  const all: (Locale | "en")[] = ["en", ...LOCALES];
  return (
    <nav aria-label={label} className="flex flex-wrap items-center gap-1.5 text-xs">
      <span className="text-faint">{label}:</span>
      {all.map((l) => (
        <Link
          key={l}
          href={localizedPath(l, path)}
          hrefLang={l === "zh" ? "zh-Hans" : l}
          className={`rounded-full px-2 py-0.5 transition ${l === current ? "bg-white/10 font-semibold text-text" : "text-muted hover:text-text"}`}
        >
          {NATIVE_NAME[l]}
        </Link>
      ))}
    </nav>
  );
}
