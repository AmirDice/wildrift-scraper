"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { CollectionState, RegionProgress } from "@/lib/collection";

const REGION_COLOR: Record<string, string> = {
  EU: "#72a7ff",
  NA: "#5ad6a8",
  CN: "#ff7f91",
};

const POLL_MS = 15_000;

function formatDate(iso: string | null): string {
  if (!iso) return "";
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) return "";
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function label(region: RegionProgress): string {
  if (region.status === "running") return `${region.percent}% · ${region.done}/${region.total}`;
  if (region.status === "complete") return formatDate(region.collectedOn) || "Complete";
  return "Waiting";
}

function StatusIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
      <ellipse cx="12" cy="5" rx="7" ry="3" />
      <path d="M5 5v6c0 1.7 3.1 3 7 3s7-1.3 7-3V5" />
      <path d="M5 11v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6" />
    </svg>
  );
}

function RegionStatus({ region }: { region: RegionProgress }) {
  const color = REGION_COLOR[region.region] ?? "var(--color-muted)";
  const running = region.status === "running";
  const complete = region.status === "complete";
  const tint = running || complete ? color : "var(--color-muted)";

  return (
    <div className="rounded-xl border border-white/[0.07] bg-white/[0.035] px-3 py-2.5">
      <div className="flex items-center gap-2">
        <span
          className={`h-2 w-2 shrink-0 rounded-full ${running ? "animate-pulse" : ""}`}
          style={{ background: tint, boxShadow: running ? `0 0 10px ${color}` : undefined }}
        />
        <span className="text-[0.68rem] font-bold uppercase tracking-[0.15em]" style={{ color: tint }}>
          {region.region}
        </span>
        <span className={`ml-auto text-xs tabular-nums ${running ? "font-semibold text-text" : "text-muted"}`}>
          {label(region)}
        </span>
      </div>
      <div
        className="mt-2 h-1 overflow-hidden rounded-full bg-white/[0.07]"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={region.percent}
        aria-label={`${region.region} data collection: ${label(region)}`}
      >
        <div
          className="h-full rounded-full transition-[width] duration-700"
          style={{
            width: `${region.percent}%`,
            background: tint,
            opacity: complete ? 0.62 : 1,
            boxShadow: running ? `0 0 8px ${color}88` : undefined,
          }}
        />
      </div>
    </div>
  );
}

function StatusPanel({ state, drawer = false }: { state: CollectionState; drawer?: boolean }) {
  return (
    <div className={drawer ? "rounded-2xl border border-line bg-white/[0.035] p-3" : "glass-menu w-[19rem] rounded-2xl p-3 shadow-2xl"}>
      <div className="mb-3 flex items-center gap-2 px-1">
        <span className="text-accent"><StatusIcon /></span>
        <div>
          <p className="text-[0.67rem] font-bold uppercase tracking-[0.16em] text-text">Data collection</p>
          <p className="text-[0.62rem] text-faint">Top-player boards by region</p>
        </div>
        <Link href="/updates" className="ml-auto text-[0.65rem] font-semibold text-accent transition hover:text-text">
          Details →
        </Link>
      </div>
      <div className="space-y-2">
        {state.regions.map((region) => <RegionStatus key={region.region} region={region} />)}
      </div>
    </div>
  );
}

export function CompactCollectionStatus({ variant = "nav" }: { variant?: "nav" | "drawer" }) {
  const [state, setState] = useState<CollectionState | null>(null);
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const load = async () => {
      try {
        const response = await fetch("/api/collection", { cache: "no-store" });
        if (!response.ok) return;
        const next = (await response.json()) as CollectionState;
        if (cancelled) return;
        setState(next);
        if (next.active) timer = setTimeout(load, POLL_MS);
      } catch {
        // Keep the last good state visible if the visitor briefly goes offline.
      }
    };
    void load();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (root.current && !root.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  if (!state || state.regions.length === 0) return null;
  if (variant === "drawer") return <StatusPanel state={state} drawer />;

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-label="Data collection status"
        aria-expanded={open}
        className={`flex h-10 items-center gap-2 rounded-lg px-2.5 text-muted transition hover:bg-white/[0.06] hover:text-text ${open ? "bg-white/[0.06] text-text" : ""}`}
      >
        <StatusIcon />
        <span className="hidden text-xs font-semibold xl:inline">Data</span>
        <span className="flex items-center gap-1" aria-hidden>
          {state.regions.map((region) => {
            const color = REGION_COLOR[region.region] ?? "var(--color-muted)";
            return (
              <span
                key={region.region}
                className={`h-1.5 w-1.5 rounded-full ${region.status === "running" ? "animate-pulse" : ""}`}
                style={{ background: region.status === "idle" ? "var(--color-muted)" : color }}
              />
            );
          })}
        </span>
      </button>
      {open && (
        <div className="absolute right-0 top-full z-[70] pt-2">
          <StatusPanel state={state} />
        </div>
      )}
    </div>
  );
}
