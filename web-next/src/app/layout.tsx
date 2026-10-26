import type { Metadata } from "next";
import Script from "next/script";
import "./globals.css";
import { SiteNav } from "@/components/site-nav";
import { FeatureBanner } from "@/components/feature-banner";
import { SiteFooter } from "@/components/site-footer";
import { FlagshipNudge } from "@/components/flagship-nudge";
import { SocialDock } from "@/components/social-dock";
import { AccountProvider } from "@/components/account-provider";
import { SiteAgentProvider } from "@/components/site-agent";
import { AdSlot } from "@/components/ad-slot";
import { AnchorAd } from "@/components/anchor-ad";
import { ADSENSE_CLIENT, ADS_LIVE } from "@/lib/ads";
import { JsonLd, organizationJsonLd, websiteJsonLd } from "@/lib/structured-data";
import { Analytics } from "@vercel/analytics/next";
import { CONSENT_REGIONS, CONSENT_RESTORE_SNIPPET, GA_ID, GROW_SITE_ID } from "@/lib/analytics";
import { AnalyticsConsent } from "@/components/analytics-consent";
import { getChampions, pendingChampions } from "@/lib/data";

export const metadata: Metadata = {
  metadataBase: new URL("https://wrtruemeta.com"),
  title: {
    default: "WrTrueMeta | Wild Rift Tier List, Win Rates & Meta Tracker",
    template: "%s | WrTrueMeta",
  },
  description:
    "Real League of Legends Wild Rift win rates from the top players on every champion. Tier list, leaderboards and meta tracking, plus a Build Studio that generates optimal items, runes and summoners for your exact game, blind or against the enemy team.",
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
      "Real Wild Rift win rates from the top players on every champion, plus a Build Studio that generates optimal items, runes and summoners for your exact game.",
    locale: "en_US",
  },
  twitter: {
    card: "summary_large_image",
    title: "WrTrueMeta | Wild Rift Tier List & Build Tools",
    description:
      "Real Wild Rift win rates from the top players of every champion, plus build and counter tools.",
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
    <html lang="en" className="h-full" suppressHydrationWarning>
      <head>
        {/* Grow by Mediavine, verbatim in the server-rendered <head>. It was
            a next/script afterInteractive tag first, which ran fine but is
            injected at the end of <body> after hydration, and Grow's
            dashboard checker only looks for the initializer in the page
            source's <head>. */}
        {/* A ternary, not `&&`: off production GROW_SITE_ID is "", and
            `"" && <script/>` renders that empty string as a text node in
            <head>, which React refuses to hydrate (the whole tree is then
            rebuilt on the client and the page flashes unstyled). */}
        {GROW_SITE_ID ? (
          <script
            data-grow-initializer=""
            dangerouslySetInnerHTML={{
              __html: `!(function(){window.growMe||((window.growMe=function(e){window.growMe._.push(e);}),(window.growMe._=[]));var e=document.createElement("script");(e.type="text/javascript"),(e.src="https://faves.grow.me/main.js"),(e.defer=!0),e.setAttribute("data-grow-faves-site-id",${JSON.stringify(GROW_SITE_ID)});var t=document.getElementsByTagName("script")[0];t.parentNode.insertBefore(e,t);})();`,
            }}
          />
        ) : null}
      </head>
      <body className="flex min-h-full flex-col" suppressHydrationWarning>
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
            filter: "saturate(0.82) brightness(0.84) hue-rotate(3deg)",
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
              "linear-gradient(180deg, rgba(5,13,26,0.22) 0%, rgba(5,13,26,0.3) 52%, rgba(4,11,23,0.42) 100%), radial-gradient(72% 62% at 78% 0%, rgba(82,151,255,0.2), transparent 72%)",
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
              "radial-gradient(125% 105% at 50% 40%, transparent 52%, rgba(3,10,22,0.3) 86%, rgba(3,9,20,0.52) 100%)",
          }}
        />
        {/* Who publishes this site, stated once for every page. */}
        <JsonLd data={[organizationJsonLd, websiteJsonLd]} />
        <AccountProvider>
          <SiteAgentProvider champions={navChampions}>
          {/* Restored after the liquid-glass revamp (f7c8a3c) dropped it: the
              site-wide announcement had no reader at all for a day, so the
              copy went on being maintained while nothing displayed it. Above
              the nav, which is where it has always sat. */}
          <FeatureBanner />
          <SiteNav champions={navChampions} />
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
          </SiteAgentProvider>
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
        {/* Google Analytics 4 under Consent Mode v2. The consent defaults
            are set before the config call: denied in the EU/EEA, UK and
            Switzerland until Google's consent message (the same one AdSense
            uses) records a choice, granted elsewhere. Denied still sends
            cookieless pings, so EU traffic is counted without storing
            anything on the device. */}
        {GA_ID && (
          <>
            <Script id="ga-init" strategy="afterInteractive">
              {`window.dataLayer = window.dataLayer || [];
function gtag(){dataLayer.push(arguments);}
gtag('consent', 'default', {
  ad_storage: 'denied', ad_user_data: 'denied', ad_personalization: 'denied', analytics_storage: 'denied',
  region: ${JSON.stringify(CONSENT_REGIONS)}, wait_for_update: 500
});
gtag('consent', 'default', {
  ad_storage: 'granted', ad_user_data: 'granted', ad_personalization: 'granted', analytics_storage: 'granted'
});
${CONSENT_RESTORE_SNIPPET}
gtag('js', new Date());
gtag('config', '${GA_ID}');`}
            </Script>
            <Script id="ga-tag" strategy="afterInteractive" src={`https://www.googletagmanager.com/gtag/js?id=${GA_ID}`} />
          </>
        )}
        {/* Analytics-only consent for Europe until AdSense's own message can
            serve (it needs an approved site); it stands down by itself once
            Google's banner appears. Production only, like GA. */}
        {GA_ID ? <AnalyticsConsent /> : null}
        <Analytics />
      </body>
    </html>
  );
}
