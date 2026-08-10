/**
 * The daily generation allowances, in a module with NO server-only imports.
 *
 * They live apart from lib/quota.ts because that file pulls in node:crypto to
 * hash IPs, which a client component cannot import. So the UI used to restate
 * the numbers by hand, and they drifted: the account menu promised "10 more on
 * top of the free 10" and the cap notice offered "10 more" while the real
 * allowance was five and five. Anything user-facing should read these instead
 * of writing a number down.
 */

/** Anonymous allowance, per IP per UTC day. */
export const ANON_DAILY_BUILDS = 5;

/** Extra allowance unlocked by signing in, per Google account per UTC day. */
export const SIGNED_IN_DAILY_BUILDS = 5;

/** What a signed-in player gets in a day, in total. */
export const TOTAL_DAILY_BUILDS = ANON_DAILY_BUILDS + SIGNED_IN_DAILY_BUILDS;
