"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useAccount } from "@/components/account-provider";
import { Card } from "@/components/ui";

interface BlendRecord {
  code: string;
  a: { name: string };
  b?: { name: string };
  createdAt: string;
}

/** Starts a duo blend and lists the ones you are already part of. */
export function StartBlend() {
  const { user } = useAccount();
  const router = useRouter();
  const [blends, setBlends] = useState<BlendRecord[]>([]);
  const [busy, setBusy] = useState(false);
  const [code, setCode] = useState("");

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/blend", { cache: "no-store" });
      if (!res.ok) return;
      const data = (await res.json()) as { blends: BlendRecord[] };
      setBlends(data.blends);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (!user) return;
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [user, load]);

  if (!user) return null;

  const start = async () => {
    setBusy(true);
    try {
      const res = await fetch("/api/blend", { method: "POST" });
      if (!res.ok) return;
      const data = (await res.json()) as { blend: BlendRecord };
      router.push(`/blend/${data.blend.code}`);
    } catch {
      /* ignore */
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-lg">
          <h2 className="font-semibold">Duo Blend</h2>
          <p className="mt-0.5 text-sm leading-relaxed text-muted">
            Mix your album with a friend&rsquo;s. You get a taste match, the champions you both saved, and a
            pick list for when you queue together. Start one, send them the link.
          </p>
        </div>
        <button
          onClick={start}
          disabled={busy}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-bold text-black transition hover:opacity-90 disabled:opacity-40"
        >
          {busy ? "Starting…" : "Start a blend"}
        </button>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-line/60 pt-4">
        <span className="text-xs font-bold uppercase tracking-wide text-faint">Have a code?</span>
        <input
          value={code}
          onChange={(event) => setCode(event.target.value.toUpperCase())}
          onKeyDown={(event) => event.key === "Enter" && code.trim() && router.push(`/blend/${code.trim()}`)}
          maxLength={12}
          placeholder="ABC123"
          className="w-32 rounded-lg border border-line bg-white/[0.04] px-3 py-1.5 text-sm tracking-[0.2em] text-text outline-none focus:border-accent/50"
        />
        <button
          onClick={() => code.trim() && router.push(`/blend/${code.trim()}`)}
          disabled={!code.trim()}
          className="rounded-lg border border-line px-3 py-1.5 text-sm font-medium text-muted transition hover:text-text disabled:opacity-40"
        >
          Open
        </button>
      </div>

      {blends.length > 0 && (
        <div className="mt-4 border-t border-line/60 pt-3">
          <p className="text-xs font-bold uppercase tracking-wide text-faint">Your blends</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {blends.map((blend) => (
              <Link
                key={blend.code}
                href={`/blend/${blend.code}`}
                className="rounded-lg bg-white/[0.05] px-3 py-1.5 text-xs font-medium text-muted transition hover:text-text"
              >
                <span className="font-bold tracking-[0.15em] text-text">{blend.code}</span>
                <span className="ml-2">
                  {blend.b ? `${blend.a.name} + ${blend.b.name}` : "waiting for a partner"}
                </span>
              </Link>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}
