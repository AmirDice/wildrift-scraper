import Link from "next/link";
import type { Champion } from "@/lib/data";
import { tierClass, tierLabel } from "@/lib/data";

export function Container({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={`mx-auto max-w-6xl px-5 ${className}`}>{children}</div>;
}

export function TierChip({ tier, className = "" }: { tier: string; className?: string }) {
  return (
    <span
      className={`inline-grid place-items-center rounded-md px-2 py-0.5 text-xs font-bold tracking-wide ${tierClass[tier] ?? "tier-c"} ${className}`}
    >
      {tierLabel(tier)}
    </span>
  );
}

export function ChampionAvatar({
  champion,
  size = 56,
  href,
  showBadges = true,
}: {
  champion: Champion;
  size?: number;
  href?: string;
  showBadges?: boolean;
}) {
  const ring = champion.isHard
    ? "ring-2 ring-bad/70"
    : "ring-1 ring-white/10";
  const img = (
    <span className="relative inline-block" style={{ width: size, height: size }}>
      <span className={`block h-full w-full overflow-hidden rounded-full ${ring}`}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={champion.icon}
          alt={`${champion.name} Wild Rift icon`}
          width={size}
          height={size}
          loading="lazy"
          className="h-full w-full scale-[1.12] object-cover"
        />
      </span>
      {showBadges && champion.isOtp && (
        <span className="absolute -right-1 -top-1 rounded bg-gradient-to-br from-orange-400 to-orange-600 px-1 text-[9px] font-bold leading-tight text-white shadow">
          OTP
        </span>
      )}
    </span>
  );
  if (href) {
    return (
      <Link href={href} className="transition hover:opacity-90">
        {img}
      </Link>
    );
  }
  return img;
}

export function SectionHeading({
  title,
  href,
  linkLabel,
  subtitle,
}: {
  title: string;
  href?: string;
  linkLabel?: string;
  subtitle?: string;
}) {
  return (
    <div className="mb-4 flex items-end justify-between gap-4">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">{title}</h2>
        {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
      </div>
      {href && linkLabel && (
        <Link
          href={href}
          className="shrink-0 text-sm font-medium text-accent transition hover:opacity-80"
        >
          {linkLabel} →
        </Link>
      )}
    </div>
  );
}

export function Card({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={`glass rounded-2xl ${className}`}>{children}</div>;
}

/**
 * The show/hide control on a collapsible result panel.
 *
 * A lone chevron is easy to read as decoration, especially on a phone where
 * there is no hover to reveal it is interactive. Pairing it with a word inside
 * a bordered pill makes it look like the button it is, and the word flips with
 * the panel so the control always says what the next tap does.
 */
export function Disclosure() {
  return (
    <span
      aria-hidden
      className="inline-flex shrink-0 items-center gap-1 rounded-full border border-line bg-white/[0.04] px-2.5 py-1 text-[0.65rem] font-bold uppercase tracking-wide text-accent transition group-hover:border-accent/40 group-hover:bg-accent/10"
    >
      <span className="group-open:hidden">Show</span>
      <span className="hidden group-open:inline">Hide</span>
      <span className="transition group-open:rotate-180">⌄</span>
    </span>
  );
}
