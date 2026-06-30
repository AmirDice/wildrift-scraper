import Link from "next/link";
import type { Champion } from "@/lib/data";
import { tierClass } from "@/lib/data";

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
      {tier}
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
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={champion.icon}
        alt={`${champion.name} Wild Rift icon`}
        width={size}
        height={size}
        loading="lazy"
        className={`h-full w-full rounded-full object-cover ${ring}`}
      />
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
