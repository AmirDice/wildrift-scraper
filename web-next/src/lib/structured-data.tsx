/**
 * Structured data (JSON-LD).
 *
 * Only claims we can actually back up: no SearchAction, because the site has no
 * `?q=` search endpoint for Google to send a query to, and no aggregateRating,
 * because nothing here is rated by users. Declaring either would be inventing a
 * capability, and Google penalises structured data that does not match the page.
 */

export const SITE_URL = "https://wrtruemeta.com";

export const organizationJsonLd = {
  "@context": "https://schema.org",
  "@type": "Organization",
  "@id": `${SITE_URL}/#organization`,
  name: "WrTrueMeta",
  url: SITE_URL,
  logo: `${SITE_URL}/logo.png`,
  description:
    "Wild Rift build platform and meta tracker built on the real win rates of the top 50 players on every champion.",
};

export const websiteJsonLd = {
  "@context": "https://schema.org",
  "@type": "WebSite",
  "@id": `${SITE_URL}/#website`,
  name: "WrTrueMeta",
  url: SITE_URL,
  publisher: { "@id": `${SITE_URL}/#organization` },
  inLanguage: "en",
};

/** Breadcrumbs let Google show the path instead of a bare URL in results. */
export function breadcrumbJsonLd(trail: { name: string; path: string }[]) {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: trail.map((entry, index) => ({
      "@type": "ListItem",
      position: index + 1,
      name: entry.name,
      item: `${SITE_URL}${entry.path}`,
    })),
  };
}

/** Renders one JSON-LD block. Next keeps this out of the React tree's text. */
export function JsonLd({ data }: { data: object | object[] }) {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(data) }}
    />
  );
}
