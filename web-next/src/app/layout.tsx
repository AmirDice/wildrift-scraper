import type { Metadata } from "next";
import Script from "next/script";
import "./globals.css";
import { SiteNav } from "@/components/site-nav";
import { SiteFooter } from "@/components/site-footer";
import { ToolsCta } from "@/components/tools-cta";
import { FeatureBanner } from "@/components/feature-banner";
import { FlagshipNudge } from "@/components/flagship-nudge";
import { SocialDock } from "@/components/social-dock";
import { AccountProvider } from "@/components/account-provider";
import { AdSlot } from "@/components/ad-slot";
import { AnchorAd } from "@/components/anchor-ad";
import { ADSENSE_CLIENT, ADS_LIVE } from "@/lib/ads";
import { JsonLd, organizationJsonLd, websiteJsonLd } from "@/lib/structured-data";
import { Analytics } from "@vercel/analytics/next";
import { getChampions, pendingChampions } from "@/lib/data";

export const metadata: Metadata = {
  metadataBase: new URL("https://wrtruemeta.com"),
  title: {
    default: "WrTrueMeta | Wild Rift Tier List, Win Rates & Meta Tracker",
    template: "%s | WrTrueMeta",
  },
  description:
    "Real League of Legends Wild Rift win rates from the top 50 players on every champion. Tier list, leaderboards and meta tracking, plus a Build Studio that generates optimal items, runes and summoners for your exact game, blind or against the enemy team.",
  keywords: [
    "Wild Rift tier list",
    "League of Legends Wild Rift",
    "Wild Rift meta",
    "Wild Rift win rates",
    "Wild Rift champions",
    "Wild Rift builds",
    "Wild Rift build generator",
    "Wild Rift counter builds",
    "Wild Rift runes",
  ],
  openGraph: {
    type: "website",
    siteName: "WrTrueMeta",
    url: "https://wrtruemeta.com",
    title: "WrTrueMeta | Wild Rift Tier List, Win Rates & Build Tools",
    description:
      "Real Wild Rift win rates from the top 50 players on every champion, plus a Build Studio that generates optimal items, runes and summoners for your exact game.",
    locale: "en_US",
  },
  twitter: {
    card: "summary_large_image",
    title: "WrTrueMeta | Wild Rift Tier List & Build Tools",
    description:
      "Real Wild Rift win rates from the top 50 players of every champion, plus build and counter tools.",
  },
  robots: { index: true, follow: true },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const navChampions = [...getChampions(), ...pendingChampions()]
    .map(({ name, slug, icon }) => ({ name, slug, icon }));
  return (
    <html lang="en" className="h-full">
      <body className="flex min-h-full flex-col">
        {/* Ambient fixed background, in three layers.
            The glass material is only as convincing as what sits behind it:
            blur() averages the backdrop, so a backdrop crushed to near-black
            blurs to near-black and the panels read as flat plastic. The
            painting is therefore shown as painted -- sharp, undimmed -- and
            contrast is handled where the text is instead.

            1. the art, unblurred and unscrimmed. inset-0 rather than the
               -inset-8 the blurred version needed: with no blur() there are no
               feathered edges to hide, so the photo is framed exactly as
               bg-cover intends. */}
        <div
          aria-hidden
          className="fixed inset-0 -z-30 bg-cover bg-center"
          style={{
            backgroundImage: "url(/hwei2.jpg)",
            // Calmed, not dimmed. Taking the saturation and brightness down a
            // little settles the art behind the content instead of competing
            // with it, without reaching for a heavy scrim, and it costs nothing
            // at runtime: this layer is composited once and never repaints.
            //
            // Tuned against the neon-on-black Hwei piece; hwei2 is a calmer
            // painting and brighter on average (mean luminance 55 against 40),
            // so it was taken down a further step on 2026-09-18 at the
            // owner's request. Darkened, not blurred: blur was offered twice
            // and turned down both times as boring.
            filter: "saturate(0.86) brightness(0.86)",
          }}
        />
        {/* 2. a light scrim. It was 0.54-0.64 when it had to carry text
               contrast on its own; every block of text now has its own backing
               (a glass panel, or a reading halo from globals.css), so this is
               down to a third of the way dark -- just enough to settle the
               neon and keep the painting from shouting over the content. */}
        <div
          aria-hidden
          className="fixed inset-0 -z-20"
          style={{
            background:
              "linear-gradient(180deg, rgba(7,10,18,0.36) 0%, rgba(7,10,18,0.40) 45%, rgba(7,10,18,0.44) 100%)",
          }}
        />
        {/* 3. vignette: darkens only the far corners so the eye settles in
               the middle. Transparent across the whole centre, so it costs
               nothing in contrast where the content actually is. */}
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
          {/* Two units on every page that takes them, top and bottom, which is
              the whole site-wide inventory. A third goes in-content on the
              pages that are long enough to earn it (<AdSlot placement="inline">),
              and ad-free routes are listed in lib/ads.ts. Each slot reserves
              its height, so a page is the same shape whether or not anything
              fills it. */}
          <AdSlot placement="top" className="mt-4" />
          <main className="flex-1">{children}</main>
          <AdSlot placement="bottom" className="mt-10" />
          {/* Bottom-right suggestion card; engagement-triggered, capped, and
              measured. See components/flagship-nudge.tsx for the rules. */}
          <FlagshipNudge />
          <SocialDock />
          <SiteFooter />
          {/* Last, and fixed to the bottom of the viewport: the highest-earning
              unit on the site, and the only one that pays for its space by
              reserving it. Renders nothing until an anchor unit is configured. */}
          <AnchorAd />
        </AccountProvider>
        {/* AdSense, once, for the whole site. It carries Google's own consent
            message for EEA visitors, which is why there is no CMP of ours: a
            home-made banner is not TCF-certified, and without a certified one
            Google serves nothing to EU traffic at all. Enable the GDPR message
            in the AdSense console, not here.

            afterInteractive, not beforeInteractive: nothing on the page waits
            for it, and an ad script that blocks first paint is how a site
            trades its Core Web Vitals for pennies. */}
        {ADS_LIVE && ADSENSE_CLIENT && (
          <Script
            id="adsense"
            async
            strategy="afterInteractive"
            crossOrigin="anonymous"
            src={`https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${ADSENSE_CLIENT}`}
          />
        )}
        <Analytics />
      </body>
    </html>
  );
}
