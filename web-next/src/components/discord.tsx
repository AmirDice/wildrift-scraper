import Link from "next/link";

export const DISCORD_URL = "https://discord.gg/hqgEtR58wj";

export function DiscordIcon({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden className={className}>
      <path d="M20.317 4.369A19.79 19.79 0 0016.558 3c-.2.36-.43.85-.593 1.234a18.27 18.27 0 00-5.487 0A12.64 12.64 0 009.885 3 19.74 19.74 0 006.12 4.369C2.746 9.398 1.83 14.3 2.286 19.135a19.9 19.9 0 006.073 3.07c.492-.67.93-1.382 1.304-2.13a12.9 12.9 0 01-2.032-.978c.17-.125.337-.255.498-.39a14.2 14.2 0 0012.14 0c.163.135.33.265.498.39-.65.383-1.33.71-2.033.978.375.748.812 1.46 1.304 2.13a19.87 19.87 0 006.075-3.07c.533-5.6-.911-10.46-3.812-14.766zM8.02 16.33c-1.183 0-2.157-1.085-2.157-2.42 0-1.334.955-2.42 2.157-2.42 1.21 0 2.176 1.095 2.157 2.42 0 1.335-.955 2.42-2.157 2.42zm7.975 0c-1.183 0-2.157-1.085-2.157-2.42 0-1.334.955-2.42 2.157-2.42 1.21 0 2.176 1.095 2.157 2.42 0 1.335-.946 2.42-2.157 2.42z" />
    </svg>
  );
}

// Icon-only link, for the nav bar (persistent, hard to miss).
export function DiscordNavLink({ className = "" }: { className?: string }) {
  return (
    <Link
      href={DISCORD_URL}
      target="_blank"
      rel="noopener noreferrer"
      aria-label="Join the WrTrueMeta Discord"
      title="Join our Discord"
      className={`inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-muted transition hover:bg-[#5865F2]/15 hover:text-[#98a0ff] ${className}`}
    >
      <DiscordIcon className="h-5 w-5" />
      <span className="md:hidden">Discord</span>
    </Link>
  );
}

// Filled button in Discord blurple, for prominent CTAs.
export function DiscordButton({ children = "Join our Discord", className = "" }: { children?: React.ReactNode; className?: string }) {
  return (
    <Link
      href={DISCORD_URL}
      target="_blank"
      rel="noopener noreferrer"
      className={`inline-flex items-center gap-2 rounded-xl bg-[#5865F2] px-5 py-2.5 font-semibold text-white transition hover:brightness-110 ${className}`}
    >
      <DiscordIcon className="h-5 w-5" />
      {children}
    </Link>
  );
}
