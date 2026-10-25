/**
 * The operator details German law requires on a site that sells to consumers
 * (section 5 DDG): a name, a postal address that can be served, and a way to
 * reach the operator quickly by email.
 *
 * Read from the environment, not written in the repository: the address is
 * the owner's, and the repository is not the place for it. The page itself is
 * public, which is the point of an Impressum.
 *
 *   IMPRESSUM_NAME      full name (or business name)
 *   IMPRESSUM_STREET    street and number
 *   IMPRESSUM_CITY      postcode and city
 *   IMPRESSUM_COUNTRY   defaults to Germany
 *   IMPRESSUM_EMAIL     a monitored address
 *   IMPRESSUM_VAT_ID    optional, only when VAT registered
 *   IMPRESSUM_SMALL_BUSINESS=1   adds the section 19 UStG note (no VAT charged)
 *
 * Selling is gated on it: lib/credits.ts offers no pack while this is
 * incomplete, so a checkout can never open before the seller can be named.
 */
export interface Impressum {
  name: string;
  street: string;
  city: string;
  country: string;
  email: string;
  vatId: string;
  smallBusiness: boolean;
}

export function impressum(): Impressum {
  const env = (k: string) => (process.env[k] ?? "").trim();
  return {
    name: env("IMPRESSUM_NAME"),
    street: env("IMPRESSUM_STREET"),
    city: env("IMPRESSUM_CITY"),
    country: env("IMPRESSUM_COUNTRY") || "Germany",
    email: env("IMPRESSUM_EMAIL"),
    vatId: env("IMPRESSUM_VAT_ID"),
    smallBusiness: env("IMPRESSUM_SMALL_BUSINESS") === "1",
  };
}

export function impressumComplete(): boolean {
  const i = impressum();
  return Boolean(i.name && i.street && i.city && i.email);
}
