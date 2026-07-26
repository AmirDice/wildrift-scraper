"use client";

import { useMemo, useRef, useState } from "react";
import { Card } from "@/components/ui";

/* eslint-disable @next/next/no-img-element */

/**
 * The shared-album memory wall: screenshots and keepsakes a duo keeps together.
 *
 * It hangs off a BLEND -- the pairing of two players -- because the album is
 * theirs jointly, not one person's. Either member may add a memory and either
 * may set the duo-profile banner; the endpoints enforce membership.
 *
 * A memory is a picture with a category and a caption. Filtering is by the four
 * fixed categories -- open tags would fragment into near-duplicates the filter
 * could not use.
 */

const CATEGORY_LABELS: Record<string, string> = {
  victory: "Victory screenshots",
  "rank-up": "Rank-up moments",
  "funny-chat": "Funny chats",
  favorite: "Favorite memories",
};
const CATEGORIES = ["victory", "rank-up", "funny-chat", "favorite"] as const;
type Category = (typeof CATEGORIES)[number];

export interface Memory {
  id: string;
  imageUrl: string;
  category: Category;
  caption?: string;
  addedByName: string;
  addedAt: string;
}

export function MemoryWall({
  blendCode,
  memories,
  bannerMemoryId,
  canContribute,
  uploadsEnabled,
  onChanged,
}: {
  blendCode: string;
  memories: Memory[];
  bannerMemoryId?: string;
  /** True for the two players in the blend: they add memories and set the
   *  banner. A visitor who is not a member sees the wall read-only. */
  canContribute: boolean;
  /** False until a blob store is configured; hides the uploader honestly. */
  uploadsEnabled: boolean;
  onChanged: (memories: Memory[], bannerMemoryId?: string) => void;
}) {
  const [filter, setFilter] = useState<Category | "all">("all");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const base = `/api/blend/${blendCode}/memories`;

  // Only offer category chips that actually have memories behind them.
  const present = useMemo(() => {
    const counts = new Map<Category, number>();
    for (const m of memories) counts.set(m.category, (counts.get(m.category) ?? 0) + 1);
    return counts;
  }, [memories]);

  const shown = filter === "all" ? memories : memories.filter((m) => m.category === filter);
  const banner = memories.find((m) => m.id === bannerMemoryId);

  // Every write returns the recomputed blend; hand its memory fields back up.
  const applied = (data: unknown) => {
    const blend = (data as { blend?: { memories?: Memory[]; bannerMemoryId?: string } })?.blend;
    onChanged(blend?.memories ?? [], blend?.bannerMemoryId);
  };

  const removeMemory = async (memoryId: string) => {
    setError("");
    try {
      const res = await fetch(`${base}?memoryId=${encodeURIComponent(memoryId)}`, { method: "DELETE" });
      if (res.ok) applied(await res.json());
      else setError("Could not remove that memory.");
    } catch {
      setError("Could not remove that memory.");
    }
  };

  const setBanner = async (memoryId: string | null) => {
    setError("");
    try {
      const res = await fetch(base, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bannerMemoryId: memoryId }),
      });
      if (res.ok) applied(await res.json());
    } catch {
      /* ignore */
    }
  };

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Shared album</h2>
          <p className="mt-0.5 text-sm text-muted">
            Victories, rank-ups, the funny chats. Pick one as your duo banner.
          </p>
        </div>
      </div>

      {/* The chosen banner, shown large: this is the album's shared face. */}
      {banner && (
        <div className="relative overflow-hidden rounded-2xl border border-accent/40">
          <img src={banner.imageUrl} alt={banner.caption ?? "Duo banner"} className="h-40 w-full object-cover sm:h-56" />
          <div className="absolute inset-x-0 bottom-0 flex items-end justify-between gap-2 bg-gradient-to-t from-black/70 to-transparent p-3">
            <span className="rounded-md bg-accent/20 px-2 py-0.5 text-[0.6rem] font-bold uppercase tracking-wide text-accent">
              Duo banner
            </span>
            {canContribute && (
              <button
                onClick={() => setBanner(null)}
                className="rounded-md bg-black/40 px-2 py-1 text-xs font-medium text-white/90 transition hover:bg-black/60"
              >
                Clear banner
              </button>
            )}
          </div>
        </div>
      )}

      {canContribute && (
        <MemoryUploader
          endpoint={base}
          uploadsEnabled={uploadsEnabled}
          busy={busy}
          setBusy={setBusy}
          onError={setError}
          onDone={applied}
        />
      )}
      {error && <p className="text-sm text-bad">{error}</p>}

      {memories.length === 0 ? (
        <Card className="p-6 text-center">
          <p className="text-sm text-muted">No memories yet. Add a victory screenshot to start the wall.</p>
        </Card>
      ) : (
        <>
          {/* Category filter: "All", then only the categories in use. */}
          <div className="flex flex-wrap gap-2">
            <FilterChip active={filter === "all"} onClick={() => setFilter("all")} label={`All · ${memories.length}`} />
            {CATEGORIES.filter((c) => present.has(c)).map((c) => (
              <FilterChip
                key={c}
                active={filter === c}
                onClick={() => setFilter(c)}
                label={`${CATEGORY_LABELS[c]} · ${present.get(c)}`}
              />
            ))}
          </div>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {shown.map((memory) => (
              <figure key={memory.id} className="group relative overflow-hidden rounded-xl border border-line">
                <img src={memory.imageUrl} alt={memory.caption ?? CATEGORY_LABELS[memory.category]} className="aspect-video w-full object-cover" />
                <figcaption className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/75 to-transparent p-2">
                  <span className="rounded bg-white/15 px-1.5 py-0.5 text-[0.55rem] font-bold uppercase tracking-wide text-white/90">
                    {CATEGORY_LABELS[memory.category]}
                  </span>
                  {memory.caption && <p className="mt-1 line-clamp-2 text-xs text-white">{memory.caption}</p>}
                  <p className="mt-0.5 text-[0.6rem] text-white/70">by {memory.addedByName}</p>
                </figcaption>

                {/* Controls appear on hover so the image stays the subject. */}
                <div className="absolute right-1.5 top-1.5 flex gap-1 opacity-0 transition group-hover:opacity-100">
                  {canContribute && memory.id !== bannerMemoryId && (
                    <button
                      onClick={() => setBanner(memory.id)}
                      title="Set as duo banner"
                      className="rounded-md bg-black/60 px-1.5 py-1 text-[0.6rem] font-semibold text-white transition hover:bg-accent hover:text-black"
                    >
                      Banner
                    </button>
                  )}
                  {canContribute && (
                    <button
                      onClick={() => removeMemory(memory.id)}
                      title="Remove"
                      aria-label="Remove memory"
                      className="rounded-md bg-black/60 px-1.5 py-1 text-[0.6rem] font-semibold text-white transition hover:bg-bad"
                    >
                      ✕
                    </button>
                  )}
                </div>
              </figure>
            ))}
          </div>
        </>
      )}
    </section>
  );
}

function MemoryUploader({
  endpoint, uploadsEnabled, busy, setBusy, onError, onDone,
}: {
  endpoint: string;
  uploadsEnabled: boolean;
  busy: boolean;
  setBusy: (v: boolean) => void;
  onError: (message: string) => void;
  onDone: (data: unknown) => void;
}) {
  const [category, setCategory] = useState<Category>("victory");
  const [caption, setCaption] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  if (!uploadsEnabled) {
    return (
      <Card className="p-4">
        <p className="text-sm text-muted">
          <span className="font-semibold text-text">Adding memories is almost ready.</span> Image uploads
          switch on once this deployment has its image storage configured.
        </p>
      </Card>
    );
  }

  const submit = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file) {
      onError("Choose an image first.");
      return;
    }
    onError("");
    setBusy(true);
    try {
      const form = new FormData();
      form.append("image", file);
      form.append("category", category);
      if (caption.trim()) form.append("caption", caption.trim().slice(0, 200));
      const res = await fetch(endpoint, { method: "POST", body: form });
      if (res.ok) {
        setCaption("");
        if (fileRef.current) fileRef.current.value = "";
        onDone(await res.json());
      } else {
        const data = (await res.json().catch(() => ({}))) as { error?: string };
        onError(data.error ?? "Upload failed.");
      }
    } catch {
      onError("Upload failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="p-4">
      <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
        <div className="space-y-2">
          <input
            ref={fileRef}
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            className="block w-full text-sm text-muted file:mr-3 file:rounded-lg file:border-0 file:bg-accent/20 file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-accent"
          />
          <div className="flex flex-wrap gap-2">
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value as Category)}
              className="rounded-lg border border-line bg-[#111827] px-2.5 py-1.5 text-sm outline-none focus:border-accent/50"
            >
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>{CATEGORY_LABELS[c]}</option>
              ))}
            </select>
            <input
              value={caption}
              onChange={(e) => setCaption(e.target.value)}
              placeholder="Caption (optional)"
              maxLength={200}
              className="min-w-0 flex-1 rounded-lg border border-line bg-black/20 px-3 py-1.5 text-sm outline-none placeholder:text-faint focus:border-accent/50"
            />
          </div>
        </div>
        <button
          onClick={submit}
          disabled={busy}
          className="self-start rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-black transition hover:brightness-110 disabled:opacity-50"
        >
          {busy ? "Uploading…" : "Add memory"}
        </button>
      </div>
    </Card>
  );
}

function FilterChip({ active, onClick, label }: { active: boolean; onClick: () => void; label: string }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-full px-3 py-1 text-xs font-medium transition ${
        active ? "bg-accent text-black" : "bg-white/[0.05] text-muted hover:text-text"
      }`}
    >
      {label}
    </button>
  );
}
