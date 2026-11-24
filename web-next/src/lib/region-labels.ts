/** The champion page's server choices and their names. Kept out of the
 *  "use client" region-scope module so server components can read them:
 *  a value exported from a client module is only a reference on the server,
 *  and rendered as "undefined". */
export const REGIONS = ["global", "eu", "na"] as const;   // China retired 2026-11-24
export type Region = (typeof REGIONS)[number];
export const REGION_LABEL: Record<Region, string> = { global: "Global", eu: "EU", na: "NA" };
export const REGION_LONG: Record<Region, string> = {
  global: "EU + NA",
  eu: "Europe",
  na: "North America",
};
