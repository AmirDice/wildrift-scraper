/**
 * Google Analytics 4. The measurement id is public (it ships in every page),
 * so it lives here with an env override rather than as a secret. Only the
 * production deployment loads it: localhost and preview deploys would count
 * our own testing as visitors.
 */
export const GA_ID = process.env.VERCEL_ENV === "production"
  ? process.env.NEXT_PUBLIC_GA_ID ?? "G-3G5FWLHT80"
  : "";

/**
 * Grow by Mediavine: the save/bookmark widget and its audience analytics,
 * and the script Mediavine's Journey ads would later run through. Public in
 * every page like the GA id, and production only for the same reason.
 */
export const GROW_SITE_ID = process.env.VERCEL_ENV === "production"
  ? process.env.NEXT_PUBLIC_GROW_SITE_ID ?? "U2l0ZToxM2VhZmZkYy1lODBjLTQ1YWEtODMzZC04Y2M2ZWM4ZWEwZWY="
  : "";

/**
 * Where consent is required before analytics or ad cookies: the EU, the rest
 * of the EEA, the UK and Switzerland. Consent Mode v2 defaults these regions
 * to "denied"; Google's certified consent message (enabled in the AdSense
 * console under Privacy & messaging) updates it when a visitor chooses, for
 * GA4 and AdSense alike. Elsewhere tags run with consent granted.
 */
export const CONSENT_REGIONS = [
  "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT",
  "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE",
  "IS", "LI", "NO", "GB", "CH",
];
