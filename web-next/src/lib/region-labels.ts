/** The champion page's server choices and their names. Kept out of the
 *  "use client" region-scope module so server components can read them:
 *  a value exported from a client module is only a reference on the server,
 *  and rendered as "undefined". */
export const REGIONS = ["global", "eu", "na", "cn"] as const;
export type Region = (typeof REGIONS)[number];
export const REGION_LABEL: Record<Region, string> = { global: "Global", eu: "EU", na: "NA", cn: "CN" };
export const REGION_LONG: Record<Region, string> = {
  global: "EU + NA + China",
  eu: "Europe",
  na: "North America",
  cn: "China",
};
