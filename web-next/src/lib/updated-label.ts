import cn from "@/data/cn.json";
import { regionBoard } from "@/lib/data";

/**
 * "Updated 26 Oct" for page titles, from the data's own dates.
 *
 * A freshness claim in a title earns clicks only while it is true, so it is
 * computed, never written: "Updated Today" on a page refreshed weekly would
 * be read once and distrusted after. Pages are rebuilt on every data commit
 * (China's daily one included), so the date in a title is the date of the
 * newest data the build saw.
 */

const fmt = (d: Date) => d.toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });

function parse(value: string | null | undefined): Date | null {
  if (!value) return null;
  // "20261024" (Tencent) or "October 23, 2026" (our boards).
  const compact = /^(\d{4})(\d{2})(\d{2})$/.exec(value);
  const d = compact ? new Date(Date.UTC(+compact[1], +compact[2] - 1, +compact[3])) : new Date(`${value} UTC`);
  return Number.isNaN(d.getTime()) ? null : d;
}

function newest(values: (string | null | undefined)[]): string | null {
  const dates = values.map(parse).filter((d): d is Date => d != null);
  if (!dates.length) return null;
  return fmt(new Date(Math.max(...dates.map((d) => d.getTime()))));
}

/** The leaderboards: EU and NA boards, China's ladder board. */
export function leaderboardUpdated(): string | null {
  return newest([regionBoard("EU").collectedOn, regionBoard("NA").collectedOn, regionBoard("CN").collectedOn]);
}

/** The tier list and home page: the boards plus China's daily official rates. */
export function tierListUpdated(): string | null {
  return newest([regionBoard("EU").collectedOn, regionBoard("NA").collectedOn, (cn as { date?: string }).date]);
}
