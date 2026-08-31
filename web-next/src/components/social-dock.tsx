import Link from "next/link";
import { DISCORD_URL, DiscordIcon } from "@/components/discord";
import { TIKTOK_URL, TikTokIcon, YOUTUBE_URL, YouTubeIcon } from "@/components/socials";

/* The persistent social dock: bottom-right, every page.
 *
 * The channels were reachable only from the footer and one nav link, which
 * means a visitor who reads half a champion page and leaves never sees them.
 * This sits in the corner of every route instead, so the ask is always one
 * click away rather than one scroll-to-the-bottom away.
 *
 * Deliberately small and quiet. It is a dock, not a popup: no animation on
 * arrival, no overlay, no dismissal to remember -- three icons that never move
 * and never interrupt. Anything louder would be a worse trade on a site whose
 * whole pitch is data rather than engagement bait.
 *
 * It shares the corner with FlagshipNudge, which is why that card now sits
 * above it rather than under it.
 */

const CHANNELS = [
  {
    key: "youtube",
    href: YOUTUBE_URL,
    label: "WrTrueMeta on YouTube",
    Icon: YouTubeIcon,
    // Brand colours on hover only. All three tinted at rest would put a
    // traffic light in the corner of every page.
    hover: "hover:bg-[#FF0000] hover:text-white",
  },
  {
    key: "tiktok",
    href: TIKTOK_URL,
    label: "WrTrueMeta on TikTok",
    Icon: TikTokIcon,
    hover: "hover:bg-[#111111] hover:text-white",
  },
  {
    key: "discord",
    href: DISCORD_URL,
    label: "Join the WrTrueMeta Discord",
    Icon: DiscordIcon,
    hover: "hover:bg-[#5865F2] hover:text-white",
  },
] as const;

export function SocialDock() {
  // Rendered on the server too. There is nothing here that differs between
  // server and client -- three static links -- so gating it behind a mount
  // effect bought no hydration safety and cost the dock its place in the
  // delivered HTML, along with a visible pop-in on every navigation.
  return (
    <div
      aria-label="WrTrueMeta social channels"
      role="complementary"
      className="fixed bottom-4 right-4 z-50 print:hidden"
    >
      <div className="liquid-glass flex items-center gap-1 rounded-2xl p-1.5">
        {CHANNELS.map(({ key, href, label, Icon, hover }) => (
          <Link
            key={key}
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={label}
            title={label}
            data-social={key}
            className={`inline-flex h-10 w-10 items-center justify-center rounded-xl text-muted transition ${hover}`}
          >
            <Icon className="h-5 w-5" />
          </Link>
        ))}
      </div>
    </div>
  );
}
