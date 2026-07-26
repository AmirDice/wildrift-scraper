"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useAccount } from "@/components/account-provider";
import { GoogleSignInButton } from "@/components/google-sign-in";
import { Card } from "@/components/ui";
import { ShareBuildButton } from "@/components/share-build";
import { MemoryWall, type Memory } from "@/components/memory-wall";

/* eslint-disable @next/next/no-img-element */

interface Player { sub: string; name: string; picture?: string }

interface Blend {
  code: string;
  a: Player;
  b?: Player;
  match: number;
  sharedChampions: { champion: string; championSlug: string }[];
  onlyA: string[];
  onlyB: string[];
  sharedItems: string[];
  duoPicks: { champion: string; championSlug: string; from: "both" | "a" | "b"; role?: string }[];
  pending: boolean;
  memories: Memory[];
  bannerMemoryId?: string;
}

function Avatar({ player, size = 44 }: { player?: Player; size?: number }) {
  if (!player) {
    return (
      <span
        className="grid place-items-center rounded-full border border-dashed border-line text-faint"
        style={{ width: size, height: size, fontSize: size * 0.4 }}
      >
        ?
      </span>
    );
  }
  return player.picture ? (
    <img src={player.picture} alt="" width={size} height={size} className="rounded-full" referrerPolicy="no-referrer" />
  ) : (
    <span
      className="grid place-items-center rounded-full bg-accent/20 font-bold text-accent"
      style={{ width: size, height: size, fontSize: size * 0.4 }}
    >
      {player.name.slice(0, 1).toUpperCase()}
    </span>
  );
}

/**
 * One duo blend: two players' albums mixed into a shared picture of what they
 * both play, and a pick list for when they queue together.
 */
export function BlendView({ code }: { code: string }) {
  const { user, authConfigured, loading: sessionLoading } = useAccount();
  const [blend, setBlend] = useState<Blend | null>(null);
  const [isMember, setIsMember] = useState(false);
  const [uploadsEnabled, setUploadsEnabled] = useState(false);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`/api/blend/${code}`, { cache: "no-store" });
      if (res.status === 404) {
        setMissing(true);
        return;
      }
      if (!res.ok) return;
      const data = (await res.json()) as { blend: Blend; isMember: boolean; uploadsEnabled?: boolean };
      setBlend(data.blend);
      setIsMember(data.isMember);
      setUploadsEnabled(Boolean(data.uploadsEnabled));
    } catch {
      /* keep the loading state */
    }
  }, [code]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const join = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/blend/${code}`, { method: "POST" });
      const data = (await res.json()) as { error?: string };
      if (!res.ok) setError(data.error ?? "Could not join that blend.");
      else await load();
    } catch {
      setError("Could not join that blend.");
    } finally {
      setBusy(false);
    }
  };

  if (missing) {
    return (
      <Card className="p-6 text-center">
        <p className="text-sm text-muted">That blend link has expired, or never existed.</p>
        <Link href="/albums" className="mt-3 inline-block text-sm font-semibold text-accent">
          Start a new one →
        </Link>
      </Card>
    );
  }
  if (!blend || sessionLoading) return <p className="text-sm text-faint">Loading blend…</p>;

  return (
    <div className="space-y-6">
      {/* the two players and the match number */}
      <Card className="p-6 text-center">
        <div className="flex items-center justify-center gap-4">
          <div className="flex flex-col items-center gap-1.5">
            <Avatar player={blend.a} size={56} />
            <span className="max-w-[8rem] truncate text-sm font-medium">{blend.a.name}</span>
          </div>
          <div className="px-2">
            <p className="text-4xl font-semibold text-accent">{blend.pending ? "—" : `${blend.match}%`}</p>
            <p className="text-[0.6rem] font-bold uppercase tracking-wide text-faint">taste match</p>
          </div>
          <div className="flex flex-col items-center gap-1.5">
            <Avatar player={blend.b} size={56} />
            <span className="max-w-[8rem] truncate text-sm font-medium">
              {blend.b?.name ?? "Waiting…"}
            </span>
          </div>
        </div>

        {blend.pending && (
          <div className="mt-5">
            {!user ? (
              <>
                <p className="mx-auto max-w-md text-sm text-muted">
                  {blend.a.name} wants to blend build albums with you. Sign in with Google to join.
                </p>
                {authConfigured && (
                  <div className="mt-3 flex justify-center">
                    <GoogleSignInButton onDone={() => void join()} />
                  </div>
                )}
              </>
            ) : isMember ? (
              <>
                <p className="text-sm text-muted">
                  Waiting for the second player. Send them this link and the blend fills in.
                </p>
                <div className="mt-3 flex flex-wrap items-center justify-center gap-2">
                  <code className="rounded-lg bg-white/[0.06] px-3 py-1.5 text-sm font-bold tracking-[0.2em] text-text">
                    {blend.code}
                  </code>
                  <ShareBuildButton
                    path={`/blend/${blend.code}`}
                    title="Blend our Wild Rift builds"
                    text="Blend your Wild Rift build album with mine on WrTrueMeta."
                    label="Copy invite"
                  />
                </div>
              </>
            ) : (
              <>
                <p className="mx-auto max-w-md text-sm text-muted">
                  Join this blend to mix your album with {blend.a.name}&rsquo;s.
                </p>
                <button
                  onClick={join}
                  disabled={busy}
                  className="mt-3 rounded-lg bg-accent px-5 py-2 text-sm font-bold text-black transition hover:opacity-90 disabled:opacity-40"
                >
                  {busy ? "Joining…" : "Join the blend"}
                </button>
              </>
            )}
            {error && <p className="mt-2 text-xs text-bad">{error}</p>}
          </div>
        )}
      </Card>

      {!blend.pending && (
        <>
          <div className="grid gap-4 md:grid-cols-2">
            <Card className="p-5">
              <h2 className="font-semibold">You both saved</h2>
              <p className="mt-0.5 text-sm text-muted">
                {blend.sharedChampions.length > 0
                  ? "Common ground: the champions in both albums."
                  : "No overlap yet. Save a few more builds and check back."}
              </p>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {blend.sharedChampions.map((entry) => (
                  <Link
                    key={entry.championSlug}
                    href={`/champions/${entry.championSlug}`}
                    className="rounded-lg bg-accent/15 px-2.5 py-1 text-xs font-semibold text-accent transition hover:bg-accent/25"
                  >
                    {entry.champion}
                  </Link>
                ))}
              </div>
            </Card>

            <Card className="p-5">
              <h2 className="font-semibold">Queue together</h2>
              <p className="mt-0.5 text-sm text-muted">
                A pick list drawn from both albums: shared picks first, then what each of you brings.
              </p>
              <div className="mt-3 divide-y divide-line/60">
                {blend.duoPicks.map((pick) => (
                  <Link
                    key={pick.championSlug}
                    href={`/champions/${pick.championSlug}`}
                    className="flex items-center gap-3 py-2 transition hover:opacity-80"
                  >
                    <span className={`shrink-0 rounded px-1.5 py-0.5 text-[0.55rem] font-bold uppercase tracking-wide ${
                      pick.from === "both" ? "bg-accent/20 text-accent"
                        : pick.from === "a" ? "bg-emerald-400/20 text-emerald-300"
                        : "bg-violet-400/20 text-violet-300"
                    }`}>
                      {pick.from === "both" ? "both" : pick.from === "a" ? blend.a.name.split(" ")[0] : blend.b?.name.split(" ")[0]}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-sm font-medium">{pick.champion}</span>
                    {pick.role && <span className="shrink-0 text-xs text-faint">{pick.role}</span>}
                  </Link>
                ))}
                {blend.duoPicks.length === 0 && (
                  <p className="py-2 text-sm text-faint">Neither album has builds in it yet.</p>
                )}
              </div>
            </Card>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <Card className="p-5">
              <h3 className="text-sm font-semibold">Only {blend.a.name} plays</h3>
              <p className="mt-2 text-sm text-muted">
                {blend.onlyA.join(" · ") || "Nothing exclusive."}
              </p>
            </Card>
            <Card className="p-5">
              <h3 className="text-sm font-semibold">Only {blend.b?.name} plays</h3>
              <p className="mt-2 text-sm text-muted">
                {blend.onlyB.join(" · ") || "Nothing exclusive."}
              </p>
            </Card>
          </div>

          <div className="flex justify-center">
            <ShareBuildButton
              path={`/blend/${blend.code}`}
              title="Our Wild Rift blend"
              text={`We match ${blend.match}% on Wild Rift builds.`}
              label="Share this blend"
            />
          </div>
        </>
      )}

      {/* The duo's shared album. Shown whether or not the blend is complete --
          a pair can start their wall the moment one of them has the link. Only
          the two members can add or set the banner; a visitor sees it read-only. */}
      {blend && (
        <div className="border-t border-line/60 pt-8">
          <MemoryWall
            blendCode={blend.code}
            memories={blend.memories}
            bannerMemoryId={blend.bannerMemoryId}
            canContribute={isMember}
            uploadsEnabled={uploadsEnabled}
            onChanged={(memories, bannerMemoryId) =>
              setBlend((prev) => (prev ? { ...prev, memories, bannerMemoryId } : prev))
            }
          />
        </div>
      )}
    </div>
  );
}
