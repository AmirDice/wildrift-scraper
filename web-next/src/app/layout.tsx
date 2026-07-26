import type { Metadata } from "next";
import "./globals.css";
import { SiteNav } from "@/components/site-nav";
import { SiteFooter } from "@/components/site-footer";
import { ToolsCta } from "@/components/tools-cta";
import { FeatureBanner } from "@/components/feature-banner";
import { AccountProvider } from "@/components/account-provider";
import { JsonLd, organizationJsonLd, websiteJsonLd } from "@/lib/structured-data";
import { Analytics } from "@vercel/analytics/next";
import { getChampions } from "@/lib/data";

export const metadata: Metadata = {
  metadataBase: new URL("https://wrtruemeta.com"),
  title: {
    default: "WrTrueMeta | Wild Rift Tier List, Win Rates & Meta Tracker",
    template: "%s | WrTrueMeta",
  },
  description:
    "Real League of Legends Wild Rift win rates from the top 50 players on every champion. Tier list, leaderboards, best players, role & class meta, updated twice a month.",
  keywords: [
    "Wild Rift tier list",
    "Wild Rift tier list",
    "League of Legends Wild Rift",
    "Wild Rift meta",
    "Wild Rift win rates",
    "Wild Rift champions",
  ],
  openGraph: {
    type: "website",
    siteName: "WrTrueMeta",
    url: "https://wrtruemeta.com",
    title: "WrTrueMeta | Wild Rift Tier List, Win Rates & Meta Tracker",
    description:
      "Real League of Legends Wild Rift win rates from the top 50 players on every champion.",
  },
  twitter: {
    card: "summary_large_image",
    title: "WrTrueMeta | Wild Rift Tier List & Meta Tracker",
    description:
      "Real Wild Rift win rates from the top 50 players of every champion.",
  },
  robots: { index: true, follow: true },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const navChampions = getChampions().map(({ name, slug, icon }) => ({ name, slug, icon }));
  return (
    <html lang="en" className="h-full">
      <body className="flex min-h-full flex-col">
        {/* Ambient fixed background, in four layers.
            The glass material is only as convincing as what sits behind it:
            blur() averages the backdrop, so a backdrop crushed to near-black
            blurs to near-black and the panels read as flat plastic. Blurring the
            ART instead of hiding it under a heavy scrim gives the glass real
            colour to refract while keeping the page calm enough to read on.

            1. the art, unblurred. inset-0 rather than the -inset-8 the blurred
               version needed: with no blur() there are no feathered edges to
               hide, so the photo is framed exactly as bg-cover intends. */}
        <div
          aria-hidden
          className="fixed inset-0 -z-30 bg-cover bg-center"
          style={{ backgroundImage: "url(/ionia2.jpg)" }}
        />
        {/* 2. the dark overlay: enough to hold text contrast, light enough that
               the art still reads as art. Slightly heavier at the bottom, where
               long content sits. */}
        <div
          aria-hidden
          className="fixed inset-0 -z-20"
          style={{
            background:
              "linear-gradient(180deg, rgba(7,10,18,0.46) 0%, rgba(7,10,18,0.52) 45%, rgba(7,10,18,0.56) 100%)",
          }}
        />
        {/* 3. vignette: darkens only the far corners so the eye settles in the
               middle. Transparent across the whole centre, so it costs nothing
               in contrast where the content actually is. */}
        <div
          aria-hidden
          className="fixed inset-0 -z-20"
          style={{
            background:
              "radial-gradient(125% 105% at 50% 45%, transparent 55%, rgba(3,5,11,0.42) 88%, rgba(3,5,11,0.62) 100%)",
          }}
        />
        {/* Who publishes this site, stated once for every page. */}
        <JsonLd data={[organizationJsonLd, websiteJsonLd]} />
        <AccountProvider>
          <FeatureBanner />
          <SiteNav champions={navChampions} />
          {/* Above the page, not above the footer: these are the two things we
              most want a visitor to try, and below the fold they were never
              seen. Kept small enough to sit in one row on a phone. */}
          <ToolsCta />
          <main className="flex-1">{children}</main>
          <SiteFooter />
        </AccountProvider>
        <Analytics />
      </body>
    </html>
  );
}
