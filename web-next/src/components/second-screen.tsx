"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { roster } from "@/lib/threat";
import {
  contentRect, loadReference, scanFrame, READER,
  type Reference, type ScanResult,
} from "@/lib/screen-read";

/**
 * Reads champion select off a picture of the phone screen.
 *
 * TWO WAYS IN, AND THE FAST ONE IS FIRST. A SCREENSHOT needs no mirroring
 * software, no cable and no install, works on iPhone and Android alike, and
 * works on the phone itself: open this page there, screenshot the draft, pick
 * it. That is three taps from a game that is already running, and it is the
 * only route that asks the player to set up nothing at all.
 *
 * A LIVE MIRROR (AirPlay, Phone Link, scrcpy) still reads continuously for
 * anyone already mirroring, and the browser's own share picker is the
 * permission prompt -- the one people know from video calls rather than a Play
 * Protect warning.
 *
 * The icons load themselves. Making that a numbered button meant every visitor
 * had to be told that a reader cannot read before it knows what champions look
 * like, which is our problem, not theirs.
 */
export function SecondScreen({ onScan }: {
  /** Called with every successful read. The second-screen page passes the
   *  draft board's filler, so a screenshot lands in the seats instead of in a
   *  list beside them. */
  onScan?: (scan: ScanResult) => void;
} = {}) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const frameRef = useRef<HTMLCanvasElement | null>(null);
  const patchRef = useRef<HTMLCanvasElement | null>(null);
  const refsRef = useRef<Reference[] | null>(null);
  const timerRef = useRef<number | null>(null);
  const frames = useRef(0);

  const [status, setStatus] = useState("Loading champion icons...");
  const [ready, setReady] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [tick, setTick] = useState({ ms: 0, count: 0 });
  // What the reader is actually looking at. Without this a live mirror that
  // reads nothing is indistinguishable from a live mirror that is framed
  // wrong, and the second is far more likely: a shared WINDOW carries its own
  // chrome, and the slot fractions are measured against the phone screen
  // alone.
  const [shot, setShot] = useState<{ url: string; rect: string } | null>(null);
  const [dragging, setDragging] = useState(false);
  // Held in a ref: the board re-renders on every fill, and a changing callback
  // in readCanvas's deps would tear down the live mirror's interval each time.
  const onScanRef = useRef(onScan);
  useEffect(() => { onScanRef.current = onScan; }, [onScan]);

  // The icons are the reference set: 141 champion portraits, normalised once
  // and reused every frame. Normalising inside the match loop would redo all
  // of them for every slot at every candidate position.
  const loadIcons = useCallback(async () => {
    setStatus("Loading champion icons...");
    const rows = Object.values(roster());
    const out: Reference[] = [];
    let failed = 0;
    // Our own copy first. The CDN original takes about 1.2s each from
    // Europe, and 141 of those sequentially is nearly three minutes -- the
    // reader never finished loading, which looked exactly like it was broken.
    // Loaded in parallel now too, since same-origin has no six-per-host wall.
    const settled = await Promise.allSettled(rows.map((r) => {
      const url = (r as { iconLocal?: string }).iconLocal || r.icon;
      return url ? loadReference(r.name, url, false) : Promise.reject(new Error("no icon"));
    }));
    for (const s of settled) {
      if (s.status === "fulfilled") out.push(s.value);
      else failed += 1;
    }
    refsRef.current = out;
    setReady(out.length > 0);
    setStatus(`${out.length} champion icons ready${failed ? `, ${failed} failed` : ""}. `
      + "Drop in a screenshot of champion select, or share a live mirror.");
  }, []);

  /**
   * Read one known champion-select frame and report what it finds.
   *
   * The reader has a lot of moving parts -- icon CORS, canvas pixel access,
   * the normalise maths, the slot fractions -- and when a live mirror produces
   * nothing it is not obvious which of them failed. This exercises every one
   * of them against a frame whose answer is known, so "the reader is broken"
   * and "the mirror is framed wrong" stop looking the same.
   */
  const selfTest = useCallback(async () => {
    if (!refsRef.current?.length) return;
    setStatus("Running the sample frame...");
    try {
      const img = new Image();
      img.src = "/_testframe.jpg";
      await img.decode();
      const c = document.createElement("canvas");
      c.width = img.naturalWidth;
      c.height = img.naturalHeight;
      const ctx = c.getContext("2d", { willReadFrequently: true })!;
      ctx.drawImage(img, 0, 0);
      const t0 = performance.now();
      const result = scanFrame(
        ctx, patchRef.current!.getContext("2d", { willReadFrequently: true })!,
        refsRef.current,
      );
      setTick({ ms: Math.round(performance.now() - t0), count: 1 });
        const found = [...result.bans, ...result.allies, ...result.enemies];
      setStatus(`Sample frame (${img.naturalWidth}x${img.naturalHeight}): read `
        + `${found.length} champions -- ${found.join(", ") || "none"}.`);
    } catch (err) {
      setStatus(`Sample frame failed: ${(err as Error).message}`);
    }
  }, []);

  /**
   * Read one already-drawn frame: trim the letterboxing, scan, report.
   *
   * Shared by the live mirror and the screenshot, because they differ only in
   * where the pixels came from. The trim matters for both -- a mirror window
   * carries its own chrome, and a screenshot of a PC mirror carries the
   * desktop around it.
   */
  const readCanvas = useCallback((ctx: CanvasRenderingContext2D, label: string) => {
    const frame = ctx.canvas;
    const rect = contentRect(ctx);
    let readCtx = ctx;
    // Only crop for REAL letterboxing. The 98% threshold this started with
    // fired on a native 2340x1080 screenshot, trimming 67px of the game's own
    // dark edge and shifting every slot fraction with it; a phone sitting in a
    // desktop share leaves far more border than that, so the bar is 92%.
    if (rect.w > 32 && rect.h > 32
        && (rect.w < frame.width * 0.92 || rect.h < frame.height * 0.92)) {
      const crop = document.createElement("canvas");
      crop.width = rect.w;
      crop.height = rect.h;
      const cctx = crop.getContext("2d", { willReadFrequently: true })!;
      cctx.drawImage(frame, rect.x, rect.y, rect.w, rect.h, 0, 0, rect.w, rect.h);
      readCtx = cctx;
    }
    const t0 = performance.now();
    const result = scanFrame(readCtx, patchRef.current!.getContext("2d", { willReadFrequently: true })!,
                             refsRef.current!);
    setTick((prev) => ({ ms: Math.round(performance.now() - t0), count: prev.count + 1 }));
    onScanRef.current?.(result);

    const thumb = document.createElement("canvas");
    thumb.width = 150;
    thumb.height = Math.max(1, Math.round(150 * readCtx.canvas.height / readCtx.canvas.width));
    thumb.getContext("2d")!.drawImage(readCtx.canvas, 0, 0, thumb.width, thumb.height);
    setShot({
      url: thumb.toDataURL("image/jpeg", 0.6),
      rect: `${readCtx.canvas.width}x${readCtx.canvas.height}`
        + (readCtx === ctx ? ` (${label})` : ` trimmed from ${frame.width}x${frame.height}`),
    });
    return result;
  }, []);

  /**
   * A screenshot, from anywhere: a file, a drag, or the clipboard.
   *
   * This is the whole no-setup path. On the phone it is the gallery picker,
   * on a desktop it is Ctrl+V straight from the snipping tool, and neither
   * needs a cable, a mirror or an install.
   */
  const readShot = useCallback(async (file: Blob | null | undefined) => {
    if (!file) return;
    if (!refsRef.current?.length) {
      setStatus("Still loading the champion icons; try again in a moment.");
      return;
    }
    setStatus("Reading the screenshot...");
    try {
      const bitmap = await createImageBitmap(file);
      const c = document.createElement("canvas");
      c.width = bitmap.width;
      c.height = bitmap.height;
      const ctx = c.getContext("2d", { willReadFrequently: true })!;
      ctx.drawImage(bitmap, 0, 0);
      bitmap.close();
      const result = readCanvas(ctx, "screenshot");
      const found = [...result.bans, ...result.allies, ...result.enemies];
      setStatus(found.length
        ? `Read ${found.length} champions off the screenshot.`
        : "Nothing recognised in that screenshot. It has to be champion select, "
          + "full screen, with the phone's own screenshot rather than a photo of the screen.");
    } catch (err) {
      setStatus(`Could not read that image: ${(err as Error).message}`);
    }
  }, [readCanvas]);

  // Ctrl+V anywhere on the page. A screenshot is on the clipboard far more
  // often than it is in a folder someone wants to go find.
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const item = [...(e.clipboardData?.items ?? [])].find((i) => i.type.startsWith("image/"));
      if (item) {
        e.preventDefault();
        void readShot(item.getAsFile());
      }
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [readShot]);

  const stop = useCallback(() => {
    if (timerRef.current) window.clearInterval(timerRef.current);
    timerRef.current = null;
    const v = videoRef.current;
    const stream = v?.srcObject as MediaStream | null;
    stream?.getTracks().forEach((t) => t.stop());
    if (v) v.srcObject = null;
    setSharing(false);
    setStatus("Stopped.");
  }, []);

  const share = useCallback(async () => {
    if (!refsRef.current?.length) return;
    try {
      // Share the mirror WINDOW rather than the whole screen: the slot
      // positions are fractions of the phone's screen, and a whole desktop
      // puts that screen in the middle of a landscape frame with black bars
      // on either side. contentRect below trims those when it can, but not
      // needing to is better.
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: { frameRate: 4 }, audio: false,
      });
      const v = videoRef.current!;
      v.srcObject = stream;
      await v.play();
      stream.getVideoTracks()[0].addEventListener("ended", stop);
      setSharing(true);
      setStatus("Reading. Open champion select on your phone.");

      timerRef.current = window.setInterval(() => {
        const frame = frameRef.current;
        if (!frame || !patchRef.current || !v.videoWidth) return;
        frame.width = v.videoWidth;
        frame.height = v.videoHeight;
        const ctx = frame.getContext("2d", { willReadFrequently: true })!;
        ctx.drawImage(v, 0, 0);
        readCanvas(ctx, "whole share");
        frames.current += 1;
      }, 600);
    } catch (err) {
      setStatus(`Share cancelled or unavailable: ${(err as Error).message}`);
    }
  }, [stop, readCanvas]);

  // The reader cannot read without its reference icons, and nothing else on
  // the page works until they are in. So it starts itself.
  useEffect(() => { void loadIcons(); }, [loadIcons]);

  useEffect(() => () => stop(), [stop]);

  return (
    <div className="space-y-4">
      {/* The no-setup path, and the only one that works on a phone: a
          screenshot, from the gallery, the clipboard or a drag. */}
      <label
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          void readShot(e.dataTransfer.files?.[0]);
        }}
        className={`flex cursor-pointer flex-col items-center gap-1 rounded-2xl border-2 border-dashed p-6 text-center transition ${
          dragging ? "border-accent bg-accent/10" : "border-white/20 hover:border-accent/60"
        }`}
      >
        <input
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => { void readShot(e.target.files?.[0]); e.target.value = ""; }}
        />
        <span className="text-sm font-semibold text-text">
          {ready ? "Drop a champion select screenshot" : "Loading champion icons..."}
        </span>
        <span className="text-xs text-muted">
          or tap to pick one, or paste with Ctrl+V. On your phone, screenshot the draft
          and choose it here: nothing to install, iPhone included.
        </span>
      </label>

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-faint">
          Already mirroring?
        </span>
        <button
          onClick={share}
          disabled={!ready || sharing}
          className="glass rounded-lg border border-gold/40 px-3 py-2 text-sm font-semibold disabled:opacity-40"
        >
          Read a live mirror
        </button>
        {sharing && (
          <button onClick={stop} className="glass rounded-lg border border-red-500/50 px-3 py-2 text-sm font-semibold">
            Stop
          </button>
        )}
        <button
          onClick={selfTest}
          disabled={!ready}
          className="glass rounded-lg border border-white/20 px-3 py-2 text-sm disabled:opacity-40"
        >
          Test on a sample frame
        </button>
      </div>

      <p className="text-sm text-muted">{status}</p>

      {sharing && (
        <p className="text-xs text-faint">
          {tick.count} frames read, {tick.ms}ms each, {READER.PATCH}px patches.
        </p>
      )}

      {shot && (
        <div className="flex items-start gap-3 rounded-xl border border-white/10 p-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={shot.url} alt="what the reader sees" className="rounded border border-white/15" />
          <div className="text-xs text-faint">
            <div className="font-bold text-muted">What the reader sees</div>
            <div className="mt-1">{shot.rect}</div>
            <div className="mt-2 max-w-xs">
              The phone screen should fill this box edge to edge. If you can see the
              mirror app&apos;s toolbar or desktop around it, share just the mirror
              window instead.
            </div>
          </div>
        </div>
      )}

      {/* The capture pipeline. The video is the stream, the first canvas is
          the frame being read, the second is the 64px scratch every patch is
          scaled into before comparison. */}
      <video ref={videoRef} className="hidden" playsInline muted />
      <canvas ref={frameRef} className="hidden" />
      <canvas ref={patchRef} width={READER.PATCH} height={READER.PATCH} className="hidden" />
    </div>
  );
}
