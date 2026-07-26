import Link from "next/link";

export const BUYMEACOFFEE_URL = "https://buymeacoffee.com/wrtruemeta";

export function CoffeeIcon({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden className={className}>
      <path d="M4 9h13v6a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5V9Z" />
      <path d="M17 10h1.8a2.7 2.7 0 0 1 0 5.4H17" />
      <path d="M7 3v2.5M11 3v2.5M15 3v2.5" />
    </svg>
  );
}

/** Text + icon link, sized for the nav bar. */
export function SupportNavLink({ className = "" }: { className?: string }) {
  return (
    <Link
      href={BUYMEACOFFEE_URL}
      target="_blank"
      rel="noopener noreferrer"
      title="Support WrTrueMeta"
      aria-label="Support WrTrueMeta on Buy Me a Coffee"
      className={`inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-muted transition hover:bg-gold/15 hover:text-gold ${className}`}
    >
      <CoffeeIcon className="h-5 w-5" />
      <span className="md:hidden">Buy me a coffee</span>
    </Link>
  );
}

/** Filled button for prominent placements (footer, support callouts). */
export function SupportButton({
  children = "Buy me a coffee",
  className = "",
}: {
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <Link
      href={BUYMEACOFFEE_URL}
      target="_blank"
      rel="noopener noreferrer"
      className={`inline-flex items-center gap-2 rounded-xl bg-[#FFDD00] px-5 py-2.5 font-semibold text-[#0b0f18] transition hover:brightness-105 ${className}`}
    >
      <CoffeeIcon className="h-5 w-5" />
      {children}
    </Link>
  );
}
